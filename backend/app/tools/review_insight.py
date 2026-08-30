from collections import Counter
from collections.abc import Callable
import logging
from uuid import uuid4

from pydantic import Field, ValidationError

from app.adapters.commerce.adapter_registry import (
    CommerceAdapterRegistry,
)
from app.adapters.commerce.commerce_adapter_base import (
    AdapterContext,
    AdapterError,
)
from app.modules.market_intelligence.schemas.adapter import (
    AdapterCapabilities,
    CollectionRun,
    CollectionStatus,
    EvidenceReference,
    ReviewSearchRequest,
)
from app.modules.market_intelligence.schemas.common import (
    DataSourceMode,
    MetricStatus,
    NonEmptyStr,
)
from app.modules.market_intelligence.schemas.facts import NormalizedReview
from app.repositories.collection_repository import CollectionRepository
from app.tools.support.contracts import (
    ToolError,
    ToolRequest,
    ToolResponse,
)
from app.tools.support.review_analyzer import (
    ReviewAnalysisProgress,
    ReviewAnalyzer,
)
from app.tools.support.llm_review_analyzer import LLMReviewAnalyzer


logger = logging.getLogger(__name__)
ProgressPublisher = Callable[[ToolRequest, str, str], None]


class ReviewInsightToolParameters(
    ReviewSearchRequest
):
    schema_version: NonEmptyStr = "1.0"
    task_id: NonEmptyStr
    tool_call_id: NonEmptyStr = Field(
        default_factory=lambda: str(uuid4())
    )
    data_source_mode: DataSourceMode


class ReviewInsightTool:
    name = "ReviewInsightTool"
    schema_version = "1.0"

    def __init__(
        self,
        *,
        adapter_registry: CommerceAdapterRegistry,
        repository: CollectionRepository,
        analyzer: ReviewAnalyzer,
        max_reviews_per_product: int = 50,
        progress_publisher: ProgressPublisher | None = None,
    ) -> None:
        if max_reviews_per_product < 1:
            raise ValueError(
                "max_reviews_per_product must be positive"
            )

        self.adapter_registry = adapter_registry
        self.repository = repository
        self.analyzer = analyzer
        self.max_reviews_per_product = (
            max_reviews_per_product
        )
        self.progress_publisher = progress_publisher

    def execute(self, request: ToolRequest) -> ToolResponse:
        try:
            return self._execute(request)
        except Exception:
            self._log_unexpected_exception(
                stage="execute",
                request=request,
                source=self.name,
            )
            return self._error_response(
                request=request,
                source=self.name,
                code="REVIEW_ANALYSIS_FAILED",
                message="Review insight processing failed unexpectedly.",
            )

    def _execute(self, request: ToolRequest) -> ToolResponse:
        identity_error = self._validate_tool_identity(request)

        if identity_error is not None:
            return self._error_response(
                request=request,
                source=self.name,
                code="INVALID_ARGUMENT",
                message=identity_error,
            )

        try:
            parameters = ReviewInsightToolParameters.model_validate(request.parameters)
        except ValidationError as exc:
            return self._error_response(
                request=request,
                source=self.name,
                code="INVALID_ARGUMENT",
                message=self._error_summary(exc),
            )

        source = (
            f"{parameters.platform.lower()}:"
            f"{parameters.data_source_mode.value}"
        )

        if parameters.schema_version != self.schema_version:
            return self._error_response(
                request=request,
                source=source,
                code="SCHEMA_VERSION_UNSUPPORTED",
                message=(
                    "Unsupported ReviewInsightTool schema version: "
                    f"{parameters.schema_version}."
                ),
            )

        if parameters.review_limit_per_product > self.max_reviews_per_product:
            return self._error_response(
                request=request,
                source=source,
                code="INVALID_ARGUMENT",
                message=(
                    "review_limit_per_product exceeds "
                    "configured maximum "
                    f"{self.max_reviews_per_product}."
                ),
            )

        adapter = self._get_adapter(
            request=request,
            parameters=parameters,
            source=source,
        )

        if isinstance(adapter, ToolResponse):
            return adapter

        capabilities = self._get_capabilities(
            request=request,
            adapter=adapter,
            source=source,
        )

        if isinstance(capabilities,ToolResponse):
            return capabilities

        capability_error = (
            self._validate_capabilities(
                request=request,
                parameters=parameters,
                capabilities=capabilities,
                source=source,
            )
        )

        if capability_error is not None:
            return capability_error

        adapter_request = ReviewSearchRequest(
            platform=parameters.platform,
            market=parameters.market,
            category=parameters.category,
            keyword=parameters.keyword,
            product_ids=parameters.product_ids,
            review_limit_per_product=(
                parameters.review_limit_per_product
            ),
        )

        adapter_context = AdapterContext(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            trace_id=request.trace_id,
            task_id=parameters.task_id,
            tool_call_id=parameters.tool_call_id,
        )

        try:
            result = adapter.search_reviews(
                adapter_request,
                adapter_context,
            )
        except AdapterError as exc:
            return self._adapter_error_response(
                request=request,
                source=source,
                error=exc,
            )
        except Exception:
            self._log_unexpected_exception(
                stage="collect_reviews",
                request=request,
                source=source,
            )
            return self._error_response(
                request=request,
                source=source,
                code="COLLECTION_INTERNAL_ERROR",
                message=(
                    "Review collection failed unexpectedly."
                ),
                retryable=True,
            )

        try:
            run = CollectionRun.model_validate(self._model_payload(result.run))
            reviews = [
                NormalizedReview.model_validate(self._model_payload(review))
                for review in result.data
            ]
            evidence_refs = [
                EvidenceReference.model_validate(self._model_payload(evidence))
                for evidence in result.evidence_refs
            ]
            warnings = list(result.warnings)
            self._validate_adapter_result(
                request=request,
                parameters=parameters,
                run=run,
                reviews=reviews,
                evidence_refs=evidence_refs,
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            return self._error_response(
                request=request,
                source=source,
                code="SCHEMA_VALIDATION_FAILED",
                message=(
                    "Adapter returned invalid review data: "
                    f"{exc}"
                ),
            )

        # AdapterResult 完整校验后统一持久化
        try:
            self.repository.save_review_collection(
                run=run,
                reviews=reviews,
                evidence_refs=evidence_refs,
            )
        except Exception:
            self._log_unexpected_exception(
                stage="persist_review_collection",
                request=request,
                source=source,
            )
            return self._error_response(
                request=request,
                source=source,
                code="COLLECTION_INTERNAL_ERROR",
                message=(
                    "Failed to persist review collection."
                ),
                retryable=True,
            )

        sample_scope = (
            evidence_refs[0].sample_scope
        )

        try:
            progress_callback = self._progress_callback(request)
            if progress_callback is None:
                review_insight = self.analyzer.analyze(
                    reviews=reviews,
                    evidence_refs=evidence_refs,
                    sample_scope=sample_scope,
                )
            else:
                review_insight = self.analyzer.analyze(
                    reviews=reviews,
                    evidence_refs=evidence_refs,
                    sample_scope=sample_scope,
                    progress_callback=progress_callback,
                )
        except Exception:
            self._log_unexpected_exception(
                stage="analyze_reviews",
                request=request,
                source=source,
            )
            return self._error_response(
                request=request,
                source=source,
                code="REVIEW_ANALYSIS_FAILED",
                message=(
                    "Review analysis failed unexpectedly."
                ),
            )

        degraded = (
            result.degraded
            or run.status
            is CollectionStatus.PARTIAL
            or review_insight.status
            in {
                MetricStatus.PARTIAL,
                MetricStatus.STALE,
            }
        )

        return ToolResponse(
            success=True,
            source=source,
            trace_id=request.trace_id,
            degraded=degraded,
            data={
                "schema_version": self.schema_version,
                "collection_run_id": run.id,
                "status": run.status.value,
                "warnings": warnings,
                "reviews": [review.model_dump(mode="json")for review in reviews],
                "review_insight": review_insight.model_dump(mode="json"),
                "evidence_refs": [evidence.model_dump(mode="json") for evidence in evidence_refs],
            },
        )

    def _progress_callback(
        self,
        request: ToolRequest,
    ) -> Callable[[ReviewAnalysisProgress], None] | None:
        if self.progress_publisher is None:
            return None

        def publish(progress: ReviewAnalysisProgress) -> None:
            summary = (
                f"Tool {self.name} completed LLM batch "
                f"{progress.completed_batches}/{progress.total_batches}; "
                f"analyzed {progress.analyzed_reviews}/"
                f"{progress.selected_reviews} selected reviews "
                f"from {progress.collected_reviews} collected reviews."
            )
            try:
                self.progress_publisher(request, self.name, summary)
            except Exception:
                self._log_unexpected_exception(
                    stage="publish_analysis_progress",
                    request=request,
                    source=self.name,
                )

        return publish

    @staticmethod
    def _log_unexpected_exception(
        *,
        stage: str,
        request: ToolRequest,
        source: str,
    ) -> None:
        logger.exception(
            "ReviewInsightTool failed unexpectedly stage=%s task_id=%s "
            "trace_id=%s source=%s",
            stage,
            request.task_id,
            request.trace_id,
            source,
        )

    def _get_adapter(
        self,
        *,
        request: ToolRequest,
        parameters: ReviewInsightToolParameters,
        source: str,
    ):
        try:
            return self.adapter_registry.get(
                parameters.platform,
                parameters.data_source_mode.value,
            )
        except KeyError:
            return self._error_response(
                request=request,
                source=source,
                code="UNSUPPORTED_DATA_SOURCE",
                message=(
                    f"No commerce adapter is registered for {source}."
                ),
            )

    def _get_capabilities(
        self,
        *,
        request: ToolRequest,
        adapter,
        source: str,
    ):
        try:
            return AdapterCapabilities.model_validate(
                self._model_payload(adapter.capabilities())
            )
        except AdapterError as exc:
            return self._adapter_error_response(
                request=request,
                source=source,
                error=exc,
            )
        except (
            AttributeError,
            TypeError,
            ValidationError,
        ):
            return self._error_response(
                request=request,
                source=source,
                code="SCHEMA_VALIDATION_FAILED",
                message=("Adapter returned invalid capabilities."),
            )

    def _validate_capabilities(
        self,
        *,
        request: ToolRequest,
        parameters: ReviewInsightToolParameters,
        capabilities: AdapterCapabilities,
        source: str,
    ) -> ToolResponse | None:
        if not capabilities.supports_reviews:
            return self._error_response(
                request=request,
                source=source,
                code="UNSUPPORTED_OPERATION",
                message=(f"Adapter {source} does not support review search."),
            )

        if (
            parameters.review_limit_per_product
            > capabilities.max_reviews_per_product
        ):
            return self._error_response(
                request=request,
                source=source,
                code="INVALID_ARGUMENT",
                message=(
                    "review_limit_per_product exceeds adapter maximum "
                    f"{capabilities.max_reviews_per_product}."
                ),
            )

        return None

    @staticmethod
    def _validate_adapter_result(
        *,
        request: ToolRequest,
        parameters: ReviewInsightToolParameters,
        run: CollectionRun,
        reviews: list[NormalizedReview],
        evidence_refs: list[EvidenceReference],
    ) -> None:
        if run.tenant_id != request.tenant_id:
            raise ValueError("run.tenant_id does not match request")
        if run.trace_id != request.trace_id:
            raise ValueError("run.trace_id does not match request")
        if run.task_id != parameters.task_id:
            raise ValueError("run.task_id does not match parameters")

        expected_requested_count = (
            len(set(parameters.product_ids)) * parameters.review_limit_per_product
        )

        if run.requested_count != expected_requested_count:
            raise ValueError("run.requested_count is inconsistent")
        if run.actual_count != len(reviews):
            raise ValueError("run.actual_count does not match reviews")
        if not reviews:
            raise ValueError("successful review result must not be empty")

        requested_product_ids = set(parameters.product_ids)
        review_ids = [review.review_id for review in reviews]

        if len(review_ids) != len(set(review_ids)):
            raise ValueError("duplicate review_id returned by adapter")

        review_counts = Counter(review.product_id for review in reviews)

        for review in reviews:
            if review.collection_run_id != run.id:
                raise ValueError("review.collection_run_id must match run.id")
            if review.product_id not in requested_product_ids:
                raise ValueError("adapter returned review for unrequested product")
            if review.platform.casefold() != parameters.platform.casefold():
                raise ValueError("review.platform does not match request")

        for product_id, count in (review_counts.items()):
            if count > parameters.review_limit_per_product:
                raise ValueError(f"adapter returned too many reviews for {product_id}")

        if len(evidence_refs) != len(reviews):
            raise ValueError("review count and evidence count must match")

        for review, evidence in zip(
            reviews,
            evidence_refs,
            strict=True,
        ):
            if evidence.collection_run_id != run.id:
                raise ValueError("evidence.collection_run_id must match run.id")
            if evidence.review_id != review.review_id:
                raise ValueError("evidence.review_id must match review.review_id")
            if evidence.product_id != review.product_id:
                raise ValueError("evidence.product_id must match review.product_id")
            if evidence.tool_call_id != parameters.tool_call_id:
                raise ValueError("evidence.tool_call_id must match tool_call_id")

            snapshot_ref = getattr(review, "source_snapshot_ref", None)

            if snapshot_ref is not None and evidence.snapshot_ref != snapshot_ref:
                raise ValueError("evidence.snapshot_ref must match review.source_snapshot_ref")

        sample_scope = evidence_refs[0].sample_scope

        if sample_scope.actual_review_count != len(reviews):
            raise ValueError("sample_scope.actual_review_count does not match reviews")

        for evidence in evidence_refs:
            if evidence.sample_scope != sample_scope:
                raise ValueError("evidence sample_scope values must match")

    @staticmethod
    def _validate_tool_identity(request: ToolRequest) -> str | None:
        values = {
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "trace_id": request.trace_id,
        }
        for field_name, value in values.items():
            if not isinstance(value, str) or not value.strip():
                return f"{field_name} is required."

        return None

    @staticmethod
    def _model_payload(value):
        if hasattr(value, "model_dump"):
            return value.model_dump()

        return value

    @staticmethod
    def _error_summary(
        error: ValidationError,
    ) -> str:
        messages = []

        for item in error.errors():
            location = ".".join(str(part) for part in item["loc"])
            messages.append(f"{location}: {item['msg']}")
        return "; ".join(messages)

    @classmethod
    def _adapter_error_response(
        cls,
        *,
        request: ToolRequest,
        source: str,
        error: AdapterError,
    ) -> ToolResponse:
        return cls._error_response(
            request=request,
            source=source,
            code=error.code,
            message=str(error),
            retryable=error.retryable,
            collection_run_id=(
                error.collection_run_id
            ),
        )

    @staticmethod
    def _error_response(
        *,
        request: ToolRequest,
        source: str,
        code: str,
        message: str,
        retryable: bool = False,
        collection_run_id: str | None = None,
    ) -> ToolResponse:
        data = {"schema_version": ReviewInsightTool.schema_version}

        if collection_run_id is not None:
            data["collection_run_id"] = collection_run_id

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
        )
