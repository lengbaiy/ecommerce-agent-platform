from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.market_intelligence.macro_market_metric_calculator import (
    MacroMarketMetricCalculator,
)
from app.modules.market_intelligence.schemas import (
    MarketMetricBatch,
    MarketMetricBatchStatus,
    MarketMetricObservation,
    MarketMetricStoredFile,
    MarketMetricUploadContext,
    MarketMetricUploadRequest,
    MarketMetricUploadResult,
    MarketMetricValueKind,
)
from app.repositories.market_metric_repository import (
    MarketMetricConflictError,
    MarketMetricRepository,
)
from app.services.market_metric_approval_service import (
    MarketMetricApprovalService,
)


class MarketMetricUploadConflictError(RuntimeError):
    pass


class MarketMetricUploadService:
    """校验、计算并原子保存一批运营上传的宏观市场指标。"""

    def __init__(
        self,
        repository: MarketMetricRepository,
        calculator: MacroMarketMetricCalculator,
        approval_service: MarketMetricApprovalService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.calculator = calculator
        self.approval_service = approval_service
        self.clock = clock or (lambda: datetime.now(UTC))

    def upload(
        self,
        *,
        context: MarketMetricUploadContext,
        request: MarketMetricUploadRequest,
        stored_file: MarketMetricStoredFile | None = None,
    ) -> MarketMetricUploadResult:
        now = self.clock()
        batch = self._build_batch(context, request, stored_file, now)
        if self.repository.scope_version_exists(batch):
            raise MarketMetricUploadConflictError(
                "the same market scope, source and data version already exists"
            )

        direct = self._build_direct_observations(batch, request, now)
        history = self.repository.list_direct_history(
            tenant_id=batch.tenant_id,
            platform=batch.platform,
            market=batch.market,
            category=batch.category,
            keyword=batch.keyword,
            metric_codes=("gmv", "market_size"),
            period_end_before=batch.period_start,
            limit=500,
        )
        derived = self.calculator.calculate(
            batch=batch,
            direct_observations=direct,
            history=history,
            calculated_at=now,
        )
        approval = self.approval_service.review(
            batch=batch,
            direct_observations=direct,
            derived_observations=derived,
            stored_file=stored_file,
            reviewed_at=now,
        )
        result = MarketMetricUploadResult(
            batch_id=approval.batch.id,
            status=approval.batch.status,
            direct_metric_count=len(direct),
            derived_metric_count=len(derived),
            created_at=approval.batch.created_at,
            approval_codes=approval.codes,
            reviewed_by=approval.batch.reviewed_by,
        )
        try:
            self.repository.create_batch(
                approval.batch,
                direct,
                derived_observations=derived,
            )
        except MarketMetricConflictError as exc:
            raise MarketMetricUploadConflictError(
                "the market metric upload conflicts with an existing batch"
            ) from exc

        return result

    @staticmethod
    def _build_batch(
        context: MarketMetricUploadContext,
        request: MarketMetricUploadRequest,
        stored_file: MarketMetricStoredFile | None,
        now: datetime,
    ) -> MarketMetricBatch:
        source = request.batch
        return MarketMetricBatch(
            tenant_id=context.tenant_id,
            trace_id=context.trace_id,
            created_at=now,
            updated_at=now,
            platform=source.platform,
            market=source.market,
            category=source.category,
            keyword=source.keyword,
            period_start=source.period_start,
            period_end=source.period_end,
            source_name=source.source_name,
            source_type=source.source_type,
            source_description=source.source_description,
            source_timestamp=source.source_timestamp,
            methodology=source.methodology,
            license_or_authorization=source.license_or_authorization,
            data_version=source.data_version,
            original_file_ref=stored_file.file_ref if stored_file else None,
            original_file_sha256=stored_file.sha256 if stored_file else None,
            status=MarketMetricBatchStatus.PENDING_REVIEW,
            uploaded_by=context.user_id,
        )

    @staticmethod
    def _build_direct_observations(
        batch: MarketMetricBatch,
        request: MarketMetricUploadRequest,
        now: datetime,
    ) -> list[MarketMetricObservation]:
        return [
            MarketMetricObservation(
                tenant_id=batch.tenant_id,
                trace_id=batch.trace_id,
                created_at=now,
                batch_id=batch.id,
                metric_code=item.metric_code,
                value_kind=MarketMetricValueKind.DIRECT,
                value=item.value,
                unit=item.unit,
                currency=item.currency,
                status=item.status,
                reason_code=item.reason_code,
                methodology=item.methodology or batch.methodology,
                source_timestamp=item.source_timestamp or batch.source_timestamp,
                growth_type=item.growth_type,
                comparison_period_start=item.comparison_period_start,
                comparison_period_end=item.comparison_period_end,
            )
            for item in request.metrics
        ]


__all__ = [
    "MarketMetricUploadConflictError",
    "MarketMetricUploadService",
]
