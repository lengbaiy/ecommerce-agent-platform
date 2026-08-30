from datetime import datetime, timedelta
from decimal import Decimal

from app.modules.market_intelligence.schemas import (
    MarketMetricApprovalDecision,
    MarketMetricApprovalOutcome,
    MarketMetricBatch,
    MarketMetricBatchStatus,
    MarketMetricObservation,
    MarketMetricSourceType,
    MarketMetricStoredFile,
    MetricStatus,
)


class MarketMetricApprovalService:
    """使用确定性规则审核宏观指标上传批次。"""

    reviewer_id = "system:market-metric-validator"
    policy_version = "1.0"
    growth_tolerance = Decimal("0.5")
    core_metric_codes = frozenset({"market_size", "gmv"})

    def review(
        self,
        *,
        batch: MarketMetricBatch,
        direct_observations: list[MarketMetricObservation],
        derived_observations: list[MarketMetricObservation],
        stored_file: MarketMetricStoredFile | None,
        reviewed_at: datetime,
    ) -> MarketMetricApprovalOutcome:
        codes = self._rejection_codes(
            batch=batch,
            direct=direct_observations,
            derived=derived_observations,
            stored_file=stored_file,
            reviewed_at=reviewed_at,
        )
        decision = (
            MarketMetricApprovalDecision.REJECTED
            if codes
            else MarketMetricApprovalDecision.APPROVED
        )
        status = (
            MarketMetricBatchStatus.REJECTED
            if codes
            else MarketMetricBatchStatus.APPROVED
        )
        note = (
            f"Automatic review policy {self.policy_version}: "
            + (", ".join(codes) if codes else "approved")
        )
        reviewed_batch = MarketMetricBatch.model_validate(
            {
                **batch.model_dump(),
                "status": status,
                "updated_at": reviewed_at,
                "reviewed_by": self.reviewer_id,
                "reviewed_at": reviewed_at,
                "review_note": note,
                "review_codes": codes,
            }
        )
        return MarketMetricApprovalOutcome(
            decision=decision,
            batch=reviewed_batch,
            codes=codes,
        )

    def _rejection_codes(
        self,
        *,
        batch: MarketMetricBatch,
        direct: list[MarketMetricObservation],
        derived: list[MarketMetricObservation],
        stored_file: MarketMetricStoredFile | None,
        reviewed_at: datetime,
    ) -> list[str]:
        codes: list[str] = []
        if not self.core_metric_codes.intersection(item.metric_code for item in direct):
            codes.append("CORE_MARKET_METRIC_MISSING")
        if any(item.status is not MetricStatus.AVAILABLE for item in direct):
            codes.append("DIRECT_METRIC_NOT_AVAILABLE")
        try:
            if batch.source_timestamp > reviewed_at + timedelta(days=1):
                codes.append("SOURCE_TIMESTAMP_IN_FUTURE")
            if batch.source_timestamp < batch.period_end:
                codes.append("SOURCE_PRECEDES_PERIOD_END")
        except TypeError:
            codes.append("TIMESTAMP_TIMEZONE_MISMATCH")
        if (
            batch.source_type is not MarketMetricSourceType.OFFICIAL_API
            and stored_file is None
        ):
            codes.append("SOURCE_FILE_MISSING")
        if self._reported_growth_conflicts(direct, derived):
            codes.append("REPORTED_GROWTH_CONFLICT")
        return codes

    def _reported_growth_conflicts(
        self,
        direct: list[MarketMetricObservation],
        derived: list[MarketMetricObservation],
    ) -> bool:
        direct_by_code = {item.metric_code: item for item in direct}
        calculated = next(
            (item for item in derived if item.metric_code == "growth"),
            None,
        )
        if calculated is None or calculated.value is None:
            return False
        base = (
            "gmv"
            if calculated.formula_code and calculated.formula_code.startswith("gmv_")
            else "market"
        )
        reported = direct_by_code.get(f"reported_{base}_growth")
        if reported is None:
            reported = direct_by_code.get("reported_growth")
        return bool(
            reported
            and reported.value is not None
            and abs(reported.value - calculated.value) > self.growth_tolerance
        )


__all__ = ["MarketMetricApprovalService"]
