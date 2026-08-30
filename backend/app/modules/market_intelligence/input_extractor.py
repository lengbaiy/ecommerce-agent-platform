import logging
import re
from decimal import Decimal

from pydantic import ConfigDict, Field, ValidationError

from app.core.security import Principal
from app.domain import (
    DataSourceOption,
    DatasetMatch,
    PreviewWarning,
    PreviewWarningSeverity,
    TaskCreate,
    TaskError,
    TaskPreviewRequest,
    TaskPreviewResponse,
)
from app.llm import LLMClientError, LLMMessage, StructuredLLMClient
from app.modules.market_intelligence.dataset_availability import DatasetAvailability
from app.modules.market_intelligence.market_metric_product_matcher import (
    MarketMetricProductMatcher,
)
from app.modules.market_intelligence.data_source_availability import (
    MarketDataSourceAvailability,
)
from app.modules.market_intelligence.schemas import (
    DataSourceMode,
    MarketIntelligenceBusinessContext,
    MarketIntelligenceRequest,
    MarketMetricBatchStatus,
    ProductSort,
    ProfitCalculatorParameters,
)
from app.modules.market_intelligence.schemas.common import MarketIntelligenceModel
from app.modules.market_intelligence.schemas.request import CollectionOptions
from app.modules.task_center.input_dispatcher import TaskInputValidationError
from app.prompts.market_intelligence import build_input_extraction_prompt
from app.repositories.market_metric_repository import MarketMetricRepository


logger = logging.getLogger(__name__)


class MarketInputExtraction(MarketIntelligenceModel):
    """LLM 输出模型；所有业务默认值由确定性代码补充。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    product_name: str | None = None
    market: str | None = None
    platform: str | None = None
    category: str | None = None
    keyword: str | None = None
    product_limit: int | None = Field(default=None, ge=1, le=50)
    review_limit_per_product: int | None = Field(default=None, ge=1, le=50)
    price: Decimal | None = Field(default=None, gt=0)
    product_cost: Decimal | None = Field(default=None, ge=0)
    platform_fee: Decimal | None = Field(default=None, ge=0)
    logistics_cost: Decimal | None = Field(default=None, ge=0)
    advertising_cost: Decimal | None = Field(default=None, ge=0)
    minimum_margin: Decimal | None = Field(default=None, ge=0, le=1)
    currency: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    ambiguities: list[str] = Field(default_factory=list)


class MarketIntelligenceInputExtractor:
    def __init__(
        self,
        availability: DatasetAvailability,
        llm_client: StructuredLLMClient | None = None,
        data_sources: MarketDataSourceAvailability | None = None,
        market_metric_repository: MarketMetricRepository | None = None,
        market_metric_product_matcher: MarketMetricProductMatcher | None = None,
    ) -> None:
        self.availability = availability
        self.llm_client = llm_client
        self.data_sources = data_sources
        self.market_metric_repository = market_metric_repository
        self.market_metric_product_matcher = market_metric_product_matcher

    def preview(
        self,
        payload: TaskPreviewRequest,
        principal: Principal | None = None,
    ) -> TaskPreviewResponse:
        draft, warnings = self._extract(payload.user_query)
        canonical = self.availability.canonicalize_product(
            payload.user_query,
            draft.product_name,
            draft.category,
            draft.keyword,
        )
        if canonical:
            category = canonical.category
            keyword = canonical.keyword
            confidence = max(draft.confidence, 0.95)
        else:
            keyword = draft.keyword or draft.product_name
            category = draft.category or draft.product_name
            confidence = draft.confidence

        market = self._market(draft.market) or (
            canonical.market if canonical else self.availability.default_market()
        )
        platform = self._platform(draft.platform) or (
            canonical.platform if canonical else self.availability.default_platform()
        )
        if draft.market is None and market:
            warnings.append(self._default_warning("market", market))
        if draft.platform is None and platform:
            warnings.append(self._default_warning("platforms", platform))

        missing_fields = [
            field
            for field, value in (
                ("market", market),
                ("platforms", platform),
                ("category", category),
                ("keyword", keyword),
            )
            if not value
        ]
        normalized_input = None
        dataset_matches = []
        data_source_options: list[DataSourceOption] = []
        if not missing_fields:
            profit_constraints = self._profit_constraints(draft, warnings)
            normalized_input = MarketIntelligenceRequest(
                market=market,
                category=category,
                keyword=keyword,
                platforms=[platform],
                data_source_mode=DataSourceMode.FIXED_DATASET,
                collection=CollectionOptions(
                    product_limit=draft.product_limit or 20,
                    review_limit_per_product=draft.review_limit_per_product or 20,
                    sort_by=ProductSort.DEFAULT,
                ),
                profit_constraints=profit_constraints,
            )
            dataset_matches = self.availability.match(
                normalized_input,
                user_query=payload.user_query,
            )
            data_source_options = self._data_source_options(
                normalized_input,
                dataset_matches,
                principal.tenant_id if principal else None,
            )
            if not any(option.available for option in data_source_options):
                warnings.append(
                    PreviewWarning(
                        code="DATA_SOURCE_NOT_AVAILABLE",
                        message="当前商品、市场和平台没有可用的数据来源。",
                        field="normalized_input",
                    )
                )

        return TaskPreviewResponse(
            intent=payload.intent,
            confidence=confidence,
            normalized_input=normalized_input,
            missing_fields=missing_fields,
            ambiguities=self._reconcile_ambiguities(
                draft.ambiguities,
                keyword=keyword,
            ),
            dataset_matches=dataset_matches,
            data_source_options=data_source_options,
            warnings=warnings,
        )

    def validate_task(self, payload: TaskCreate) -> None:
        try:
            context = MarketIntelligenceBusinessContext.model_validate(
                payload.business_context
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            field = ".".join(str(item) for item in first.get("loc", ()))
            raise TaskInputValidationError(
                TaskError(
                    code="MARKET_INPUT_INVALID",
                    message=str(first.get("msg", "Market task input is invalid.")),
                    step="validate_input",
                    details={"field": field},
                )
            ) from exc

        request = context.market_intelligence_request
        request = self._validate_market_metric_selection(payload, context, request)
        if request.data_source_mode is DataSourceMode.OFFICIAL_API:
            if self.data_sources is not None and self.data_sources.is_supported(
                request,
                payload.tenant_id,
            ):
                return
            raise TaskInputValidationError(
                TaskError(
                    code="UNSUPPORTED_DATA_SOURCE",
                    message="所选官方平台 API 尚未接入或当前账号未授权。",
                    step="validate_input",
                    details={
                        "platform": request.platforms[0],
                        "market": request.market,
                        "data_source_mode": request.data_source_mode.value,
                    },
                )
            )
        adapter_available = (
            self.data_sources is None or self.data_sources.is_supported(request)
        )
        if not adapter_available or not self.availability.is_supported(request):
            raise TaskInputValidationError(
                TaskError(
                    code="DATASET_NOT_AVAILABLE",
                    message="没有固定数据集匹配该市场分析请求。",
                    step="validate_input",
                    details={
                        "platform": request.platforms[0],
                        "market": request.market,
                        "category": request.category,
                        "keyword": request.keyword,
                    },
                )
            )

    def _validate_market_metric_selection(
        self,
        payload: TaskCreate,
        context: MarketIntelligenceBusinessContext,
        request: MarketIntelligenceRequest,
    ) -> MarketIntelligenceRequest:
        if request.market_metric_batch_id is None:
            if request.market_metric_product_match is None:
                return request
            request = request.model_copy(update={"market_metric_product_match": None})
            payload.business_context = context.model_copy(
                update={"market_intelligence_request": request}
            ).model_dump(mode="json")
            return request
        if (
            payload.tenant_id is None
            or self.market_metric_repository is None
            or self.market_metric_product_matcher is None
        ):
            raise self._market_metric_validation_error(
                "MARKET_METRIC_PRODUCT_MATCH_UNAVAILABLE",
                "当前无法验证所选宏观市场数据的商品一致性。",
            )
        try:
            batch = self.market_metric_repository.get_batch(
                request.market_metric_batch_id,
                payload.tenant_id,
            )
        except KeyError as exc:
            raise self._market_metric_validation_error(
                "MARKET_METRIC_BATCH_NOT_FOUND",
                "所选宏观市场数据批次不存在或不属于当前租户。",
            ) from exc
        if batch.status is not MarketMetricBatchStatus.APPROVED:
            raise self._market_metric_validation_error(
                "MARKET_METRIC_BATCH_NOT_APPROVED",
                "所选宏观市场数据批次当前未通过审核。",
            )
        if (
            batch.platform.casefold() != request.platforms[0].casefold()
            or batch.market.upper() != request.market.upper()
        ):
            raise self._market_metric_validation_error(
                "MARKET_METRIC_SCOPE_MISMATCH",
                "所选宏观市场数据批次与当前平台或市场不一致。",
            )
        product_match = self.market_metric_product_matcher.match(
            requested_category=request.category,
            requested_keyword=request.keyword,
            batch=batch,
        )
        if not self.market_metric_product_matcher.accepted(product_match):
            raise self._market_metric_validation_error(
                "MARKET_METRIC_PRODUCT_MISMATCH",
                "所选宏观市场数据与本次分析商品不一致或无法确认一致。",
                details={
                    "decision": product_match.decision.value,
                    "confidence": product_match.confidence,
                    "reason": product_match.reason,
                    "batch_id": batch.id,
                },
            )
        request = request.model_copy(
            update={"market_metric_product_match": product_match}
        )
        payload.business_context = context.model_copy(
            update={"market_intelligence_request": request}
        ).model_dump(mode="json")
        return request

    @staticmethod
    def _market_metric_validation_error(
        code: str,
        message: str,
        *,
        details: dict | None = None,
    ) -> TaskInputValidationError:
        return TaskInputValidationError(
            TaskError(
                code=code,
                message=message,
                step="validate_input",
                details=details or {},
            )
        )

    def _data_source_options(
        self,
        request: MarketIntelligenceRequest,
        dataset_matches: list[DatasetMatch],
        tenant_id: str | None,
    ) -> list[DataSourceOption]:
        if self.data_sources is not None:
            return self.data_sources.options(request, dataset_matches, tenant_id)
        supported = any(item.supported for item in dataset_matches)
        platform = request.platforms[0]
        return [
            DataSourceOption(
                platform=platform,
                market=request.market,
                data_source_mode=DataSourceMode.FIXED_DATASET.value,
                label=f"{platform} {request.market} · 固定数据集",
                available=supported,
                supports_products=supported,
                supports_reviews=supported,
                supports_market_metrics=supported,
                unavailable_reason=(
                    None if supported else "当前商品、市场或平台没有可用固定数据集"
                ),
            )
        ]

    @staticmethod
    def _reconcile_ambiguities(
        ambiguities: list[str],
        *,
        keyword: str | None,
    ) -> list[str]:
        """移除已被确定性标准化解决的关键词缺失提示。"""

        if not keyword:
            return ambiguities
        missing_terms = (
            "未提供",
            "没有提供",
            "缺少",
            "未明确",
            "未指定",
            "not provided",
            "missing",
            "unspecified",
        )
        keyword_terms = ("搜索关键词", "关键词", "搜索词", "keyword", "search term")
        return [
            item
            for item in ambiguities
            if not (
                any(term in item.casefold() for term in missing_terms)
                and any(term in item.casefold() for term in keyword_terms)
            )
        ]

    def _extract(self, user_query: str) -> tuple[MarketInputExtraction, list[PreviewWarning]]:
        warnings: list[PreviewWarning] = []
        if self.llm_client is not None:
            system_prompt, user_prompt = build_input_extraction_prompt(user_query)
            try:
                draft = self.llm_client.generate_structured(
                    messages=[
                        LLMMessage(role="system", content=system_prompt),
                        LLMMessage(role="user", content=user_prompt),
                    ],
                    response_model=MarketInputExtraction,
                )
                return draft.model_copy(
                    update={
                        "market": draft.market or self._fallback_market(user_query),
                        "platform": draft.platform or self._fallback_platform(user_query),
                    }
                ), warnings
            except LLMClientError as exc:
                logger.warning(
                    "Market input extraction fell back to deterministic rules: "
                    "code=%s provider=%s retryable=%s",
                    exc.code,
                    exc.provider,
                    exc.retryable,
                )
                warnings.append(
                    PreviewWarning(
                        code="INPUT_EXTRACTION_FALLBACK",
                        message="LLM 输入提取不可用，已使用确定性规则。",
                        severity=PreviewWarningSeverity.INFO,
                        field="user_query",
                    )
                )

        product_name = self._fallback_product_name(user_query)
        confidence = 0.8 if self.availability.canonicalize_product(user_query) else 0.45
        return MarketInputExtraction(
            product_name=product_name,
            market=self._fallback_market(user_query),
            platform=self._fallback_platform(user_query),
            confidence=confidence,
        ), warnings

    @staticmethod
    def _fallback_product_name(user_query: str) -> str | None:
        query = " ".join(user_query.strip().split())
        patterns = (
            r"(?:分析|评估|研究|调研)(?:一下)?(?P<product>.+?)(?:是否|值不值得|有没有|市场|，|,|。|目标|$)",
            r"(?:想分析|想做|看看)(?P<product>.+?)(?:是否|值不值得|市场|，|,|。|目标|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                product = match.group("product").strip(" 的在于")
                if product:
                    return product
        return None

    @staticmethod
    def _market(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        return "US" if normalized in {"us", "usa", "united states", "美国"} else value

    @staticmethod
    def _fallback_market(user_query: str) -> str | None:
        query = user_query.casefold()
        markets = {
            "US": ("美国", "united states", " usa ", " us "),
            "UK": ("英国", "united kingdom", " uk "),
            "DE": ("德国", "germany"),
            "JP": ("日本", "japan"),
        }
        padded = f" {query} "
        for market, aliases in markets.items():
            if any(alias in padded for alias in aliases):
                return market
        return None

    @staticmethod
    def _platform(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        return "amazon" if normalized in {"amazon", "亚马逊"} else normalized

    @staticmethod
    def _fallback_platform(user_query: str) -> str | None:
        query = user_query.casefold()
        platforms = {
            "amazon": ("amazon", "亚马逊"),
            "taobao": ("taobao", "淘宝"),
            "tiktok": ("tiktok", "抖音"),
        }
        for platform, aliases in platforms.items():
            if any(alias in query for alias in aliases):
                return platform
        return None

    @staticmethod
    def _default_warning(field: str, value: str) -> PreviewWarning:
        return PreviewWarning(
            code="DEFAULT_VALUE_APPLIED",
            message=f"未明确提供 {field}，已使用默认值 {value}。",
            severity=PreviewWarningSeverity.INFO,
            field=field,
        )

    @staticmethod
    def _profit_constraints(
        draft: MarketInputExtraction,
        warnings: list[PreviewWarning],
    ) -> ProfitCalculatorParameters | None:
        values = (
            draft.price,
            draft.product_cost,
            draft.platform_fee,
            draft.logistics_cost,
            draft.advertising_cost,
            draft.minimum_margin,
        )
        if all(value is not None for value in values):
            return ProfitCalculatorParameters(
                price=draft.price,
                product_cost=draft.product_cost,
                platform_fee=draft.platform_fee,
                logistics_cost=draft.logistics_cost,
                advertising_cost=draft.advertising_cost,
                minimum_margin=draft.minimum_margin,
                currency=draft.currency or "USD",
            )
        if any(value is not None for value in values):
            warnings.append(
                PreviewWarning(
                    code="PROFIT_INPUT_INCOMPLETE",
                    message="利润参数不完整，本次任务将生成降级利润报告。",
                    field="profit_constraints",
                )
            )
        # 利润测算是可选能力，完全未提供时无需提示或影响主分析状态。
        return None


__all__ = ["MarketInputExtraction", "MarketIntelligenceInputExtractor"]
