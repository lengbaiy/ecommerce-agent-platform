import logging

from pydantic import ConfigDict, Field

from app.llm import LLMClientError, LLMMessage, StructuredLLMClient
from app.modules.market_intelligence.dataset_availability import DatasetAvailability
from app.modules.market_intelligence.schemas import (
    MarketMetricBatch,
    MarketMetricProductDecision,
    MarketMetricProductMatch,
    MarketMetricProductMatchMethod,
)
from app.modules.market_intelligence.schemas.common import MarketIntelligenceModel, NonEmptyStr
from app.prompts.market_intelligence import (
    PRODUCT_MATCH_PROMPT_VERSION,
    build_product_match_prompt,
)


logger = logging.getLogger(__name__)


class LLMProductMatchOutput(MarketIntelligenceModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    decision: MarketMetricProductDecision
    confidence: float = Field(ge=0, le=1)
    requested_normalized_name: NonEmptyStr
    batch_normalized_name: NonEmptyStr
    reason: NonEmptyStr


class MarketMetricProductMatcher:
    """使用 Manifest 别名和 LLM 判断宏观指标批次的商品一致性。"""

    def __init__(
        self,
        availability: DatasetAvailability,
        llm_client: StructuredLLMClient | None,
        *,
        model: str | None,
        confidence_threshold: float = 0.85,
    ) -> None:
        self.availability = availability
        self.llm_client = llm_client
        self.model = model
        self.confidence_threshold = confidence_threshold

    def match(
        self,
        *,
        requested_category: str,
        requested_keyword: str,
        batch: MarketMetricBatch,
    ) -> MarketMetricProductMatch:
        requested = self.availability.canonicalize_product(
            requested_keyword,
        )
        candidate = self.availability.canonicalize_product(
            batch.keyword,
        )
        if requested is not None and candidate is not None:
            same = self._selector(requested.keyword) == self._selector(candidate.keyword)
            return self._result(
                batch=batch,
                requested_product=requested_keyword,
                decision=(
                    MarketMetricProductDecision.SAME_PRODUCT
                    if same
                    else MarketMetricProductDecision.DIFFERENT_PRODUCT
                ),
                confidence=1.0,
                requested_normalized_name=requested.keyword,
                batch_normalized_name=candidate.keyword,
                reason=(
                    "任务商品与批次商品命中同一个标准商品及其别名。"
                    if same
                    else "任务商品与批次商品分别命中不同的标准商品。"
                ),
                method=MarketMetricProductMatchMethod.DETERMINISTIC_ALIAS,
            )

        requested_normalized = self._selector(requested_keyword)
        batch_normalized = self._selector(batch.keyword)
        if requested_normalized == batch_normalized:
            return self._result(
                batch=batch,
                requested_product=requested_keyword,
                decision=MarketMetricProductDecision.SAME_PRODUCT,
                confidence=1.0,
                requested_normalized_name=requested_normalized,
                batch_normalized_name=batch_normalized,
                reason="任务商品与批次商品的标准化名称完全一致。",
                method=MarketMetricProductMatchMethod.DETERMINISTIC_EXACT,
            )

        if self.llm_client is None:
            return self._unavailable(batch, requested_keyword, "商品语义判断服务当前不可用。")

        system_prompt, user_prompt = build_product_match_prompt(
            {
                "requested_product": requested_keyword,
                "batch_product": batch.keyword,
                "requested_category": requested_category,
                "batch_category": batch.category,
            }
        )
        try:
            output = self.llm_client.generate_structured(
                messages=(
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ),
                response_model=LLMProductMatchOutput,
            )
        except LLMClientError as exc:
            logger.warning(
                "Market metric product match failed batch_id=%s code=%s provider=%s",
                batch.id,
                exc.code,
                exc.provider,
            )
            return self._unavailable(batch, requested_keyword, "商品语义判断服务调用失败。")

        decision = output.decision
        reason = output.reason
        if (
            decision is not MarketMetricProductDecision.UNCERTAIN
            and output.confidence < self.confidence_threshold
        ):
            decision = MarketMetricProductDecision.UNCERTAIN
            reason = f"{reason} 判断置信度低于 {self.confidence_threshold:.0%}。"
        return self._result(
            batch=batch,
            requested_product=requested_keyword,
            decision=decision,
            confidence=output.confidence,
            requested_normalized_name=output.requested_normalized_name,
            batch_normalized_name=output.batch_normalized_name,
            reason=reason,
            method=MarketMetricProductMatchMethod.LLM,
        )

    def accepted(self, result: MarketMetricProductMatch) -> bool:
        return (
            result.decision is MarketMetricProductDecision.SAME_PRODUCT
            and result.confidence >= self.confidence_threshold
        )

    def _unavailable(
        self,
        batch: MarketMetricBatch,
        requested_product: str,
        reason: str,
    ) -> MarketMetricProductMatch:
        return self._result(
            batch=batch,
            requested_product=requested_product,
            decision=MarketMetricProductDecision.UNCERTAIN,
            confidence=0,
            requested_normalized_name=self._selector(requested_product),
            batch_normalized_name=self._selector(batch.keyword),
            reason=reason,
            method=MarketMetricProductMatchMethod.UNAVAILABLE,
        )

    def _result(
        self,
        *,
        batch: MarketMetricBatch,
        requested_product: str,
        decision: MarketMetricProductDecision,
        confidence: float,
        requested_normalized_name: str,
        batch_normalized_name: str,
        reason: str,
        method: MarketMetricProductMatchMethod,
    ) -> MarketMetricProductMatch:
        return MarketMetricProductMatch(
            batch_id=batch.id,
            decision=decision,
            confidence=confidence,
            requested_product=requested_product,
            batch_product=batch.keyword,
            requested_normalized_name=requested_normalized_name,
            batch_normalized_name=batch_normalized_name,
            reason=reason,
            method=method,
            provider=(self.llm_client.provider if method is MarketMetricProductMatchMethod.LLM and self.llm_client else None),
            model=(self.model if method is MarketMetricProductMatchMethod.LLM else None),
            prompt_version=PRODUCT_MATCH_PROMPT_VERSION,
        )

    @staticmethod
    def _selector(value: str) -> str:
        return " ".join(value.casefold().replace("_", " ").split())


__all__ = ["MarketMetricProductMatcher"]
