import logging
from uuid import uuid4

from pydantic import Field, ValidationError

from app.adapters.commerce import AdapterContext, AdapterError, CommerceAdapterRegistry
from app.modules.market_intelligence.database_market_metric_provider import (
    DatabaseMarketMetricProvider,
    DatabaseMarketMetricResult,
    MarketMetricSelectionError,
)
from app.modules.market_intelligence.schemas import (
    DataSourceMode,
    MarketDataRequest,
    MarketMetric,
    MetricStatus,
    NonEmptyStr,
    EvidenceReference,
    NormalizedProduct,
)
from app.tools.support.contracts import ToolError, ToolRequest, ToolResponse
from app.tools.support.market_sample_metrics import (
    MarketSampleMetricsError,
    MarketSampleMetricsResult,
    build_market_sample_metrics,
)


logger = logging.getLogger(__name__)


class MarketDataToolParameters(MarketDataRequest):
    """MarketDataTool 对外参数。"""

    schema_version: NonEmptyStr = "1.0"
    task_id: NonEmptyStr
    data_source_mode: DataSourceMode
    tool_call_id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    products: list[NormalizedProduct] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class MarketDataTool:
    name = "MarketDataTool"
    schema_version = "1.0"

    FULL_MARKET_METRIC_CODES = {
        "market_size",
        "gmv",
        "growth",
        "price_distribution",
        "brand_concentration",
        "product_concentration",
    }

    def __init__(
        self,
        registry: CommerceAdapterRegistry,
        market_metric_provider: DatabaseMarketMetricProvider | None = None,
    ) -> None:
        self.registry = registry
        self.market_metric_provider = market_metric_provider

    def execute(self, tool_request: ToolRequest) -> ToolResponse:
        try:
            return self._execute(tool_request)
        except Exception:
            logger.exception(
                "MarketDataTool failed unexpectedly stage=execute "
                "task_id=%s trace_id=%s",
                tool_request.task_id,
                tool_request.trace_id,
            )
            return self._error_response(
                request=tool_request,
                code="MARKET_DATA_INTERNAL_ERROR",
                message="Market data processing failed unexpectedly.",
                source=self.name,
            )

    def _execute(self, tool_request: ToolRequest) -> ToolResponse:
        identity_error = self._validate_tool_identity(tool_request)
        if identity_error is not None:
            return self._error_response(
                request=tool_request,
                code="INVALID_ARGUMENT",
                message=identity_error,
                source=self.name,
            )
        
        # 1. 校验 Tool 参数
        try:
            parameters = MarketDataToolParameters.model_validate(tool_request.parameters)
        except ValidationError as exc:
            return self._error_response(
                request=tool_request,
                code="INVALID_ARGUMENT",
                message=self._error_summary(exc),
            )

        platform = parameters.platform
        data_source_mode = parameters.data_source_mode.value

        if parameters.schema_version != self.schema_version:
            return self._error_response(
                request=tool_request,
                code="SCHEMA_VERSION_UNSUPPORTED",
                message=(
                    "Unsupported MarketDataTool schema version: "
                    f"{parameters.schema_version}."
                ),
                source=f"{platform}:{data_source_mode}",
            )

        request = MarketDataRequest(
            platform=parameters.platform,
            market=parameters.market,
            category=parameters.category,
            keyword=parameters.keyword,
            market_metric_batch_id=parameters.market_metric_batch_id,
            market_metric_product_match=parameters.market_metric_product_match,
            start_time=parameters.start_time,
            end_time=parameters.end_time,
        )
        context = AdapterContext(
            tenant_id=tool_request.tenant_id,
            user_id=tool_request.user_id,
            trace_id=tool_request.trace_id,
            task_id=parameters.task_id,
            tool_call_id=parameters.tool_call_id,
        )
        database_result, database_warnings = self._database_metrics(
            request=request,
            context=context,
            data_source_mode=parameters.data_source_mode,
        )

        # 2. 根据 platform + data_source_mode 选择 Adapter
        try:
            adapter = self.registry.get(platform=platform, data_source_mode=data_source_mode)
        except (KeyError, TypeError, ValueError):
            if database_result is not None:
                return self._database_only_response(
                    request=tool_request,
                    platform=platform,
                    data_source_mode=data_source_mode,
                    result=database_result,
                    warnings=[*database_warnings, "SUPPLEMENTAL_MARKET_DATA_UNAVAILABLE"],
                )
            return self._error_response(
                request=tool_request,
                code="UNSUPPORTED_DATA_SOURCE",
                message=f"Unsupported market data source: {platform}/{data_source_mode}.",
                source=f"{platform}:{data_source_mode}",
            )

        # 3. Adapter 不支持聚合市场指标时，退回到明确标注的商品样本统计
        capabilities = adapter.capabilities()

        if not capabilities.supports_market_metrics:
            try:
                sample_result = build_market_sample_metrics(
                    platform=parameters.platform,
                    market=parameters.market,
                    category=parameters.category,
                    keyword=parameters.keyword,
                    data_source_mode=parameters.data_source_mode,
                    requested_start_time=parameters.start_time,
                    requested_end_time=parameters.end_time,
                    products=parameters.products,
                    evidence_refs=parameters.evidence_refs,
                )
            except MarketSampleMetricsError as exc:
                if database_result is not None:
                    return self._database_only_response(
                        request=tool_request,
                        platform=platform,
                        data_source_mode=data_source_mode,
                        result=database_result,
                        warnings=[
                            *database_warnings,
                            f"SUPPLEMENTAL_MARKET_DATA_FAILED:{exc}",
                        ],
                    )
                return self._error_response(
                    request=tool_request,
                    code="INVALID_ARGUMENT",
                    message=str(exc),
                    source=f"{platform}:{data_source_mode}",
                )

            response = self._sample_fallback_response(
                request=tool_request,
                platform=platform,
                data_source_mode=data_source_mode,
                adapter_version=capabilities.adapter_version,
                sample_result=sample_result,
            )
            return self._merge_database_metrics(
                response,
                database_result,
                database_warnings,
            )

        # 6. 调 Adapter
        try:
            result = adapter.get_market_metrics(request, context)
        except AdapterError as exc:
            if database_result is not None:
                return self._database_only_response(
                    request=tool_request,
                    platform=platform,
                    data_source_mode=data_source_mode,
                    result=database_result,
                    warnings=[*database_warnings, f"SUPPLEMENTAL_MARKET_DATA_FAILED:{exc.code}"],
                )
            return self._adapter_error_response(
                request=tool_request,
                platform=platform,
                data_source_mode=data_source_mode,
                error=exc,
            )
        except Exception:
            logger.exception(
                "MarketDataTool failed unexpectedly stage=get_market_metrics "
                "task_id=%s trace_id=%s source=%s",
                tool_request.task_id,
                tool_request.trace_id,
                f"{platform}:{data_source_mode}",
            )
            if database_result is not None:
                return self._database_only_response(
                    request=tool_request,
                    platform=platform,
                    data_source_mode=data_source_mode,
                    result=database_result,
                    warnings=[*database_warnings, "SUPPLEMENTAL_MARKET_DATA_FAILED"],
                )
            return self._error_response(
                request=tool_request,
                code="MARKET_DATA_INTERNAL_ERROR",
                message="Market data retrieval failed because of an internal error.",
                source=f"{platform}:{data_source_mode}",
                retryable=True,
            )

        # 7. Tool 层判断是否属于降级市场数据
        degraded = result.degraded or self._has_incomplete_market_data(result.data)
        # 8. AdapterResult → ToolResponse
        response = ToolResponse(
            success=True,
            data={
                "schema_version": self.schema_version,
                "collection_run_id": result.run.id,
                "status": result.run.status.value,
                "stop_reason": result.run.stop_reason,
                "adapter_version": result.run.adapter_version,
                "metrics": [metric.model_dump(mode="json") for metric in result.data],
                "evidence_refs": [e.model_dump(mode="json") for e in result.evidence_refs],
                "warnings": list(result.warnings),
            },
            error=None,
            source=f"{platform}:{data_source_mode}",
            trace_id=tool_request.trace_id,
            degraded=degraded,
        )
        return self._merge_database_metrics(
            response,
            database_result,
            database_warnings,
        )

    def _database_metrics(
        self,
        *,
        request: MarketDataRequest,
        context: AdapterContext,
        data_source_mode: DataSourceMode,
    ) -> tuple[DatabaseMarketMetricResult | None, list[str]]:
        if self.market_metric_provider is None:
            return None, []
        try:
            result = self.market_metric_provider.get_metrics(
                request=request,
                context=context,
                data_source_mode=data_source_mode,
            )
        except MarketMetricSelectionError as exc:
            logger.warning(
                "Selected market metric batch rejected task_id=%s trace_id=%s "
                "batch_id=%s code=%s",
                context.task_id,
                context.trace_id,
                request.market_metric_batch_id,
                exc.code,
            )
            return None, [f"SELECTED_MARKET_METRIC_BATCH_INVALID:{exc.code}"]
        except Exception:
            logger.exception(
                "Database market metric lookup failed task_id=%s trace_id=%s",
                context.task_id,
                context.trace_id,
            )
            return None, ["DATABASE_MARKET_METRIC_LOOKUP_FAILED"]
        return (result if result.metrics else None), list(result.warnings)

    def _merge_database_metrics(
        self,
        response: ToolResponse,
        database_result: DatabaseMarketMetricResult | None,
        database_warnings: list[str],
    ) -> ToolResponse:
        if database_result is None:
            if not database_warnings:
                return response
            data = dict(response.data)
            data["warnings"] = self._merge_strings(
                list(data.get("warnings", [])),
                database_warnings,
            )
            return response.model_copy(update={"data": data})

        fallback_metrics = [
            MarketMetric.model_validate(item)
            for item in response.data.get("metrics", [])
        ]
        database_codes = {item.metric_code for item in database_result.metrics}
        fallback_metrics = [
            item for item in fallback_metrics if item.metric_code not in database_codes
        ]
        metrics = [
            *database_result.metrics,
            *fallback_metrics,
        ]
        fallback_evidence_ids = {
            evidence_id
            for metric in fallback_metrics
            for evidence_id in metric.evidence_ids
        }
        fallback_evidence = [
            EvidenceReference.model_validate(item)
            for item in response.data.get("evidence_refs", [])
            if item.get("evidence_id") in fallback_evidence_ids
        ]
        evidence = self._merge_evidence(database_result.evidence_refs, fallback_evidence)
        data = dict(response.data)
        data.update(
            {
                "source_market_metric_batch_ids": database_result.batch_ids,
                "metrics": [item.model_dump(mode="json") for item in metrics],
                "evidence_refs": [item.model_dump(mode="json") for item in evidence],
                "warnings": self._merge_strings(
                    list(data.get("warnings", [])),
                    [*database_warnings, "DATABASE_MARKET_METRICS_APPLIED"],
                ),
            }
        )
        return response.model_copy(
            update={
                "data": data,
                "source": f"{response.source}+database",
                "degraded": self._has_incomplete_market_data(metrics),
            }
        )

    def _database_only_response(
        self,
        *,
        request: ToolRequest,
        platform: str,
        data_source_mode: str,
        result: DatabaseMarketMetricResult,
        warnings: list[str],
    ) -> ToolResponse:
        degraded = self._has_incomplete_market_data(result.metrics)
        return ToolResponse(
            success=True,
            data={
                "schema_version": self.schema_version,
                "collection_run_id": result.batch_ids[0],
                "source_market_metric_batch_ids": result.batch_ids,
                "status": "PARTIAL" if degraded else "COMPLETED",
                "stop_reason": "SUPPLEMENTAL_MARKET_DATA_UNAVAILABLE",
                "adapter_version": "database-market-metric-provider:1.0",
                "metrics": [item.model_dump(mode="json") for item in result.metrics],
                "evidence_refs": [
                    item.model_dump(mode="json") for item in result.evidence_refs
                ],
                "warnings": self._merge_strings(
                    warnings,
                    ["DATABASE_MARKET_METRICS_APPLIED"],
                ),
            },
            error=None,
            source=f"{platform}:{data_source_mode}+database",
            trace_id=request.trace_id,
            degraded=degraded,
        )

    @staticmethod
    def _merge_evidence(
        primary: list[EvidenceReference],
        secondary: list[EvidenceReference],
    ) -> list[EvidenceReference]:
        merged: dict[str, EvidenceReference] = {}
        for item in [*primary, *secondary]:
            merged.setdefault(item.evidence_id, item)
        return list(merged.values())

    @staticmethod
    def _merge_strings(primary: list[str], secondary: list[str]) -> list[str]:
        return list(dict.fromkeys([*primary, *secondary]))

    def _sample_fallback_response(
        self, *, request: ToolRequest, platform: str, data_source_mode: str,
        adapter_version: str, sample_result: MarketSampleMetricsResult,
    ) -> ToolResponse:
        return ToolResponse(
            success=True,
            data={
                "schema_version": self.schema_version,
                "collection_run_id": str(uuid4()),
                "source_collection_run_ids": sample_result.source_collection_run_ids,
                "status": "COMPLETED",
                "stop_reason": "AGGREGATE_MARKET_DATA_MISSING",
                "adapter_version": adapter_version,
                "metrics": [metric.model_dump(mode="json") for metric in sample_result.metrics],
                "evidence_refs": [e.model_dump(mode="json") for e in sample_result.evidence_refs],
                "warnings": sample_result.warnings,
            },
            error=None,
            source=f"{platform}:{data_source_mode}",
            trace_id=request.trace_id,
            degraded=True,
        )

    @staticmethod
    def _validate_tool_identity(request: ToolRequest) -> str | None:
        for field_name in ("tenant_id", "user_id", "trace_id"):
            value = getattr(request, field_name, None)
            if not isinstance(value, str) or not value.strip():
                return f"{field_name} is required"
        return None

    def _has_incomplete_market_data(self, metrics: list[MarketMetric]) -> bool:
        """
        全市场核心指标不完整时，
        Tool 层视为降级结果。

        sample 指标仍可以正常返回。
        """

        metrics_by_code = {metric.metric_code: metric for metric in metrics}
        for metric_code in self.FULL_MARKET_METRIC_CODES:
            metric = metrics_by_code.get(metric_code)
            if metric is None or metric.status is not MetricStatus.AVAILABLE:
                return True

        return False

    def _adapter_error_response(
        self, *, request: ToolRequest, platform: str,
        data_source_mode: str, error: AdapterError,
    ) -> ToolResponse:
        data = {"schema_version": self.schema_version}

        if error.collection_run_id is not None:
            data["collection_run_id"] = error.collection_run_id

        return ToolResponse(
            success=False,
            data=data,
            error=ToolError(code=error.code, message=str(error), retryable=error.retryable),
            source=f"{platform}:{data_source_mode}",
            trace_id=request.trace_id,
            degraded=False,
        )

    def _error_response(
        self, *, request: ToolRequest, code: str, message: str,
        source: str | None = None, retryable: bool = False,
    ) -> ToolResponse:
        return ToolResponse(
            success=False,
            data={"schema_version": self.schema_version},
            error=ToolError(code=code, message=message, retryable=retryable),
            source=source or self.name,
            trace_id=request.trace_id,
            degraded=False,
        )

    @staticmethod
    def _error_summary(exc: ValidationError) -> str:
        messages = []

        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"])
            messages.append(f"{location}: {error['msg']}")

        return "; ".join(messages)
