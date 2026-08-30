import logging
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, Field, StringConstraints, ValidationError

from app.adapters.commerce import (
    AdapterContext,
    AdapterError,
    CommerceAdapterRegistry,
)
from app.adapters.commerce.commerce_adapter_base import AdapterResult
from app.repositories.collection_repository import CollectionRepository
from app.modules.market_intelligence.schemas import (
    AdapterCapabilities,
    CollectionRun,
    CollectionStatus,
    DataSourceMode,
    EvidenceReference,
    EvidenceType,
    NormalizedProduct,
    ProductSearchRequest,
)
from app.tools.support.contracts import ToolError, ToolRequest, ToolResponse


logger = logging.getLogger(__name__)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProductSearchToolParameters(ProductSearchRequest):
    schema_version: NonEmptyStr = "1.0"
    task_id: NonEmptyStr
    data_source_mode: DataSourceMode
    tool_call_id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))


class ProductSearchTool:
    name = "product_search"
    schema_version = "1.0"

    def __init__(
        self,
        adapter_registry: CommerceAdapterRegistry,
        repository: CollectionRepository,
        *,
        max_product_limit: int = 50,
    ) -> None:
        if not 1 <= max_product_limit <= 50:
            raise ValueError("max_product_limit must be between 1 and 50")
        self.adapter_registry = adapter_registry
        self.repository = repository
        self.max_product_limit = max_product_limit

    def execute(self, request: ToolRequest) -> ToolResponse:
        identity_error = self._validate_tool_identity(request)
        if identity_error is not None:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=identity_error,
                source=self.name,
            )
        try:
            parameters = ProductSearchToolParameters.model_validate(request.parameters)
        except ValidationError as exc:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=self._error_summary(exc),
                source=self.name,
            )

        source = (
            f"{parameters.platform.lower()}:"
            f"{parameters.data_source_mode.value}"
        )
        if parameters.schema_version != self.schema_version:
            return self._error_response(
                request=request,
                code="SCHEMA_VERSION_UNSUPPORTED",
                message=(
                    "Unsupported ProductSearchTool schema version: "
                    f"{parameters.schema_version}."
                ),
                source=source,
            )
        if parameters.product_limit > self.max_product_limit:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=(
                    "product_limit exceeds server maximum "
                    f"{self.max_product_limit}."
                ),
                source=source,
            )

        try:
            adapter = self.adapter_registry.get(
                parameters.platform,
                parameters.data_source_mode.value,
            )
        except KeyError:
            return self._error_response(
                request=request,
                code="UNSUPPORTED_DATA_SOURCE",
                message=(
                    "No commerce adapter is registered for "
                    f"{parameters.platform}/{parameters.data_source_mode.value}."
                ),
                source=source,
            )

        try:
            capabilities = AdapterCapabilities.model_validate(
                self._model_payload(adapter.capabilities())
            )
        except AdapterError as exc:
            return self._error_response(
                request=request,
                code=exc.code,
                message=str(exc),
                source=source,
                retryable=exc.retryable,
            )
        except (AttributeError, TypeError, ValidationError):
            return self._error_response(
                request=request,
                code="SCHEMA_VALIDATION_FAILED",
                message="Adapter returned invalid capabilities.",
                source=source,
            )
        except Exception:
            return self._error_response(
                request=request,
                code="COLLECTION_INTERNAL_ERROR",
                message="Adapter capability discovery failed.",
                source=source,
            )
        if not capabilities.supports_products:
            return self._error_response(
                request=request,
                code="UNSUPPORTED_DATA_SOURCE",
                message="The selected adapter does not support product search.",
                source=source,
            )
        if capabilities.platform.casefold() != parameters.platform.casefold():
            return self._error_response(
                request=request,
                code="SCHEMA_VALIDATION_FAILED",
                message="Adapter capabilities contain an unexpected platform.",
                source=source,
            )
        if capabilities.data_source_mode is not parameters.data_source_mode:
            return self._error_response(
                request=request,
                code="SCHEMA_VALIDATION_FAILED",
                message="Adapter capabilities contain an unexpected data source mode.",
                source=source,
            )
        if parameters.product_limit > capabilities.max_products:
            return self._error_response(
                request=request,
                code="INVALID_ARGUMENT",
                message=(
                    "product_limit exceeds adapter maximum "
                    f"{capabilities.max_products}."
                ),
                source=source,
            )

        adapter_request = ProductSearchRequest(
            platform=parameters.platform,
            market=parameters.market,
            category=parameters.category,
            keyword=parameters.keyword,
            product_limit=parameters.product_limit,
            sort_by=parameters.sort_by,
        )
        adapter_context = AdapterContext(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            trace_id=request.trace_id,
            task_id=parameters.task_id,
            tool_call_id=parameters.tool_call_id,
        )
        try:
            adapter_result = adapter.search_products(adapter_request, adapter_context)
            run, products, evidence_refs, warnings, degraded = self._validate_adapter_result(
                adapter_result,
                adapter_context,
                adapter_request,
            )
        except AdapterError as exc:
            return self._error_response(
                request=request,
                code=exc.code,
                message=str(exc),
                source=source,
                retryable=exc.retryable,
                run=exc.run if isinstance(exc.run, CollectionRun) else None,
            )
        except Exception:
            return self._error_response(
                request=request,
                code="COLLECTION_INTERNAL_ERROR",
                message="Product search failed because of an internal error.",
                source=source,
            )

        # Adapter 返回的数据完成校验后，再统一持久化到数据库
        try:
            self.repository.save_product_collection(
                run=run,
                products=products,
                evidence_refs=evidence_refs,
            )
        except Exception:
            logger.exception(
                "Product search persistence failed task_id=%s trace_id=%s run_id=%s",
                parameters.task_id,
                request.trace_id,
                run.id,
            )
            return self._error_response(
                request=request,
                code="COLLECTION_INTERNAL_ERROR",
                message="Product search result persistence failed.",
                source=source,
                run=run,
            )

        return ToolResponse(
            success=True,
            data=self._success_data(
                run=run,
                products=products,
                evidence_refs=evidence_refs,
                warnings=warnings,
            ),
            error=None,
            source=source,
            trace_id=request.trace_id,
            degraded=degraded,
        )

    def _validate_adapter_result(
        self,
        result: AdapterResult[list[NormalizedProduct]],
        context: AdapterContext,
        request: ProductSearchRequest,
    ) -> tuple[
        CollectionRun,
        list[NormalizedProduct],
        list[EvidenceReference],
        list[str],
        bool,
    ]:
        try:
            run = CollectionRun.model_validate(self._model_payload(result.run))
        except (AttributeError, TypeError, ValidationError) as exc:
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                f"Adapter returned an invalid collection run: {self._error_summary(exc)}.",
            ) from exc
        try:
            products = [
                NormalizedProduct.model_validate(self._model_payload(product))
                for product in result.data
            ]
            evidence_refs = [
                EvidenceReference.model_validate(self._model_payload(evidence))
                for evidence in result.evidence_refs
            ]
            warnings = list(result.warnings)
            degraded = result.degraded
        except (AttributeError, TypeError, ValidationError) as exc:
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                f"Adapter returned invalid product data: {self._error_summary(exc)}.",
                collection_run_id=run.id,
                run=run,
            ) from exc

        if not all(isinstance(item, str) for item in warnings):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter warnings must contain strings.",
                collection_run_id=run.id,
                run=run,
            )
        if not isinstance(degraded, bool):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter degraded flag must be boolean.",
                collection_run_id=run.id,
                run=run,
            )

        if (
            run.task_id != context.task_id
            or run.trace_id != context.trace_id
            or run.tenant_id != context.tenant_id
        ):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter collection run does not match the Tool context.",
                collection_run_id=run.id,
                run=run,
            )
        if (
            run.keyword != request.keyword
            or run.requested_count != request.product_limit
        ):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter collection run does not match the product request.",
                collection_run_id=run.id,
                run=run,
            )
        if run.actual_count != len(products):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter product count does not match the collection run.",
                collection_run_id=run.id,
                run=run,
            )
        if run.status not in {CollectionStatus.COMPLETED, CollectionStatus.PARTIAL}:
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Successful AdapterResult has an invalid collection status.",
                collection_run_id=run.id,
                run=run,
            )
        if degraded is not (run.status is CollectionStatus.PARTIAL):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter degraded flag does not match the collection status.",
                collection_run_id=run.id,
                run=run,
            )

        product_keys = {(item.platform, item.product_id) for item in products}
        if len(product_keys) != len(products):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter returned duplicate products.",
                collection_run_id=run.id,
                run=run,
            )
        if any(
            item.platform.casefold() != request.platform.casefold()
            or item.market.casefold() != request.market.casefold()
            for item in products
        ):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Adapter product scope does not match the product request.",
                collection_run_id=run.id,
                run=run,
            )
        evidence_keys = {
            (item.platform, item.product_id)
            for item in evidence_refs
            if item.product_id is not None
        }
        if product_keys != evidence_keys:
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Product evidence does not cover the returned product set.",
                collection_run_id=run.id,
                run=run,
            )
        if any(item.collection_run_id != run.id for item in evidence_refs):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Product evidence references an unexpected collection run.",
                collection_run_id=run.id,
                run=run,
            )
        if any(
            item.evidence_type is not EvidenceType.PRODUCT
            or item.tool_call_id != context.tool_call_id
            for item in evidence_refs
        ):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Product evidence does not match the Tool call.",
                collection_run_id=run.id,
                run=run,
            )
        if any(item.collection_run_id != run.id for item in products):
            raise AdapterError(
                "SCHEMA_VALIDATION_FAILED",
                "Product data references an unexpected collection run.",
                collection_run_id=run.id,
                run=run,
            )
        return run, products, evidence_refs, warnings, degraded

    def _success_data(
        self,
        *,
        run: CollectionRun,
        products: list[NormalizedProduct],
        evidence_refs: list[EvidenceReference],
        warnings: list[str],
    ) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "collection_run_id": run.id,
            "keyword": run.keyword,
            "requested_count": run.requested_count,
            "actual_count": run.actual_count,
            "status": run.status.value,
            "stop_reason": run.stop_reason,
            "adapter_version": run.adapter_version,
            "parser_version": run.parser_version,
            "products": [item.model_dump(mode="json") for item in products],
            "evidence_refs": [
                item.model_dump(mode="json") for item in evidence_refs
            ],
            "source_snapshots": self._source_snapshots(evidence_refs),
            "warnings": list(warnings),
        }

    @staticmethod
    def _source_snapshots(
        evidence_refs: list[EvidenceReference],
    ) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for evidence in evidence_refs:
            dataset_id = str(
                evidence.query_range.get("dataset_id") or ""
            )
            key = (
                dataset_id,
                evidence.platform,
                evidence.data_version,
                evidence.sha256,
            )
            if key in seen:
                continue
            seen.add(key)
            snapshots.append(
                {
                    "dataset_id": dataset_id,
                    "platform": evidence.platform,
                    "source": evidence.data_source,
                    "source_timestamp": evidence.source_timestamp,
                    "sha256": evidence.sha256,
                    "data_version": evidence.data_version,
                    "data_level": evidence.data_level.value,
                }
            )

        return snapshots

    def _error_response(
        self,
        *,
        request: ToolRequest,
        code: str,
        message: str,
        source: str,
        retryable: bool = False,
        run: CollectionRun | None = None,
    ) -> ToolResponse:
        data: dict[str, Any] = {"schema_version": self.schema_version}
        if run is not None:
            if run.status is not CollectionStatus.FAILED:
                run = run.model_copy(
                    update={
                        "status": CollectionStatus.FAILED,
                        "stop_reason": code,
                    }
                )
            data.update(
                {
                    "collection_run_id": run.id,
                    "keyword": run.keyword,
                    "requested_count": run.requested_count,
                    "actual_count": run.actual_count,
                    "status": run.status.value,
                    "stop_reason": run.stop_reason,
                    "adapter_version": run.adapter_version,
                    "parser_version": run.parser_version,
                }
            )
        return ToolResponse(
            success=False,
            data=data,
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
            ),
            source=source,
            trace_id=request.trace_id,
            degraded=False,
        )

    @staticmethod
    def _validate_tool_identity(request: ToolRequest) -> str | None:
        for field_name in ("tenant_id", "user_id", "trace_id"):
            value = getattr(request, field_name, None)
            if not isinstance(value, str) or not value.strip():
                return f"{field_name} is required"
        return None

    @staticmethod
    def _model_payload(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="python")
        return value

    @staticmethod
    def _error_summary(error: Exception) -> str:
        if isinstance(error, ValidationError):
            first = error.errors()[0]
            location = ".".join(str(item) for item in first.get("loc", ()))
            message = str(first.get("msg", "validation failed"))
            return f"{location}: {message}" if location else message
        return str(error) or error.__class__.__name__
