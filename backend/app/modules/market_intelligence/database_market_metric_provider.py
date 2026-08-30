import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.adapters.commerce import AdapterContext
from app.modules.market_intelligence.schemas import (
    AnalysisScope,
    DataLevel,
    DataSourceMode,
    EvidenceReference,
    EvidenceType,
    MarketDataRequest,
    MarketMetric,
    MarketMetricBatchStatus,
    MarketMetricProductDecision,
    MarketMetricRecord,
    MarketMetricSourceType,
    MetricStatus,
)
from app.repositories.market_metric_repository import MarketMetricRepository


@dataclass(frozen=True)
class DatabaseMarketMetricResult:
    metrics: list[MarketMetric]
    evidence_refs: list[EvidenceReference]
    batch_ids: list[str]
    warnings: list[str] = field(default_factory=list)


class MarketMetricSelectionError(ValueError):
    """用户选择的宏观指标批次在执行时已不可用。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DatabaseMarketMetricProvider:
    """读取已审核宏观指标，并将数据库观测转换成 Agent 公共契约。"""

    def __init__(self, repository: MarketMetricRepository) -> None:
        self.repository = repository

    def get_metrics(
        self,
        *,
        request: MarketDataRequest,
        context: AdapterContext,
        data_source_mode: DataSourceMode,
    ) -> DatabaseMarketMetricResult:
        if (request.start_time is None) != (request.end_time is None):
            raise ValueError("market metric start_time and end_time must be provided together")
        records = (
            self._selected_batch_records(request=request, context=context)
            if request.market_metric_batch_id
            else self.repository.list_approved(
                tenant_id=context.tenant_id,
                platform=request.platform,
                market=request.market,
                category=request.category,
                keyword=request.keyword,
                period_start=request.start_time,
                period_end=request.end_time,
                limit=500,
            )
        )
        if not records:
            return DatabaseMarketMetricResult(metrics=[], evidence_refs=[], batch_ids=[])

        warnings: list[str] = []
        grouped: dict[str, list[MarketMetricRecord]] = {}
        for record in records:
            grouped.setdefault(record.observation.metric_code, []).append(record)

        metrics: list[MarketMetric] = []
        evidence: list[EvidenceReference] = []
        selected: list[MarketMetricRecord] = []
        for metric_code in sorted(grouped):
            latest_period = self._latest_period(grouped[metric_code])
            candidates = self._latest_version_per_source(latest_period)
            selected.extend(candidates)
            candidate_evidence = [
                self._evidence(record, context, data_source_mode)
                for record in candidates
            ]
            evidence.extend(candidate_evidence)
            metric, warning = self._metric(
                candidates,
                candidate_evidence,
                data_source_mode,
            )
            metrics.append(metric)
            if warning:
                warnings.append(warning)

        return DatabaseMarketMetricResult(
            metrics=metrics,
            evidence_refs=evidence,
            batch_ids=sorted({record.batch.id for record in selected}),
            warnings=warnings,
        )

    def _selected_batch_records(
        self,
        *,
        request: MarketDataRequest,
        context: AdapterContext,
    ) -> list[MarketMetricRecord]:
        batch_id = request.market_metric_batch_id
        if batch_id is None:
            return []
        try:
            batch = self.repository.get_batch(batch_id, context.tenant_id)
        except KeyError as exc:
            raise MarketMetricSelectionError(
                "BATCH_NOT_FOUND",
                "所选宏观市场数据批次不存在或不属于当前租户。",
            ) from exc
        if batch.status is not MarketMetricBatchStatus.APPROVED:
            raise MarketMetricSelectionError(
                "BATCH_NOT_APPROVED",
                "所选宏观市场数据批次当前未通过审核。",
            )
        if batch.platform.casefold() != request.platform.casefold():
            raise MarketMetricSelectionError(
                "PLATFORM_MISMATCH",
                "所选宏观市场数据批次与分析平台不一致。",
            )
        if batch.market.upper() != request.market.upper():
            raise MarketMetricSelectionError(
                "MARKET_MISMATCH",
                "所选宏观市场数据批次与目标市场不一致。",
            )
        product_match = request.market_metric_product_match
        if product_match is None:
            raise MarketMetricSelectionError(
                "PRODUCT_MATCH_MISSING",
                "所选宏观市场数据批次没有冻结的商品一致性判断。",
            )
        if (
            product_match.batch_id != batch.id
            or product_match.decision is not MarketMetricProductDecision.SAME_PRODUCT
            or product_match.confidence < 0.85
            or product_match.requested_product.casefold() != request.keyword.casefold()
            or product_match.batch_product.casefold() != batch.keyword.casefold()
        ):
            raise MarketMetricSelectionError(
                "PRODUCT_MATCH_INVALID",
                "所选宏观市场数据批次缺少有效的商品一致性确认。",
            )
        observations = self.repository.list_batch_observations(
            batch_id=batch.id,
            tenant_id=context.tenant_id,
        )
        return [
            MarketMetricRecord(batch=batch, observation=item)
            for item in observations
        ]

    @staticmethod
    def _latest_period(records: list[MarketMetricRecord]) -> list[MarketMetricRecord]:
        latest_end = max(record.batch.period_end for record in records)
        latest_start = max(
            record.batch.period_start
            for record in records
            if record.batch.period_end == latest_end
        )
        return [
            record
            for record in records
            if record.batch.period_start == latest_start
            and record.batch.period_end == latest_end
        ]

    @staticmethod
    def _latest_version_per_source(
        records: list[MarketMetricRecord],
    ) -> list[MarketMetricRecord]:
        by_source: dict[str, MarketMetricRecord] = {}
        for record in records:
            key = record.batch.source_name.casefold()
            current = by_source.get(key)
            if current is None or (
                record.batch.created_at,
                record.batch.data_version,
            ) > (
                current.batch.created_at,
                current.batch.data_version,
            ):
                by_source[key] = record
        return sorted(
            by_source.values(),
            key=lambda item: (
                item.batch.source_name.casefold(),
                item.batch.data_version,
            ),
        )

    def _metric(
        self,
        candidates: list[MarketMetricRecord],
        evidence: list[EvidenceReference],
        data_source_mode: DataSourceMode,
    ) -> tuple[MarketMetric, str | None]:
        first = candidates[0]
        values = {
            (
                self._comparable_value(record.observation.value),
                record.observation.unit,
                record.observation.currency,
            )
            for record in candidates
        }
        scope = self._scope(first, data_source_mode)
        evidence_ids = [item.evidence_id for item in evidence]
        if len(values) > 1:
            return (
                MarketMetric(
                    metric_code=first.observation.metric_code,
                    value=None,
                    unit=None,
                    status=MetricStatus.CONFLICT,
                    reason_code="APPROVED_MARKET_METRIC_CONFLICT",
                    scope=scope,
                    methodology="Approved sources provide conflicting values for this metric.",
                    evidence_ids=evidence_ids,
                    source_timestamp=self._latest_source_timestamp(candidates),
                ),
                f"MARKET_METRIC_CONFLICT:{first.observation.metric_code}",
            )

        status = self._combined_status(candidates)
        return (
            MarketMetric(
                metric_code=first.observation.metric_code,
                value=first.observation.value,
                unit=first.observation.unit,
                status=status,
                reason_code=first.observation.reason_code,
                scope=scope,
                methodology=first.observation.methodology,
                evidence_ids=evidence_ids,
                source_timestamp=self._latest_source_timestamp(candidates),
            ),
            None,
        )

    @staticmethod
    def _comparable_value(value: Decimal | None) -> str | None:
        return format(value.normalize(), "f") if value is not None else None

    @staticmethod
    def _combined_status(records: list[MarketMetricRecord]) -> MetricStatus:
        priority = {
            MetricStatus.CONFLICT: 4,
            MetricStatus.STALE: 3,
            MetricStatus.PARTIAL: 2,
            MetricStatus.AVAILABLE: 1,
            MetricStatus.UNAVAILABLE: 0,
        }
        return max(
            (record.observation.status for record in records),
            key=priority.__getitem__,
        )

    @staticmethod
    def _latest_source_timestamp(records: list[MarketMetricRecord]) -> datetime:
        def utc_value(value: datetime) -> datetime:
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

        return max(
            (record.observation.source_timestamp for record in records),
            key=utc_value,
        )

    @staticmethod
    def _scope(
        record: MarketMetricRecord,
        data_source_mode: DataSourceMode,
    ) -> AnalysisScope:
        batch = record.batch
        return AnalysisScope(
            market=batch.market,
            platforms=[batch.platform],
            category=batch.category,
            keyword=batch.keyword,
            start_time=batch.period_start,
            end_time=batch.period_end,
            requested_product_count=0,
            actual_product_count=0,
            actual_review_count=0,
            data_source_mode=data_source_mode,
        )

    def _evidence(
        self,
        record: MarketMetricRecord,
        context: AdapterContext,
        data_source_mode: DataSourceMode,
    ) -> EvidenceReference:
        batch = record.batch
        item = record.observation
        payload = {
            "batch_id": batch.id,
            "observation_id": item.id,
            "metric_code": item.metric_code,
            "value": str(item.value) if item.value is not None else None,
            "unit": item.unit,
            "status": item.status.value,
            "methodology": item.methodology,
            "source_timestamp": item.source_timestamp.isoformat(),
            "source_name": batch.source_name,
            "formula_code": item.formula_code,
            "formula_version": item.formula_version,
            "source_observation_ids": item.source_observation_ids,
            "data_version": batch.data_version,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return EvidenceReference(
            evidence_id=f"market-metric-{item.id}",
            evidence_type=EvidenceType.MARKET_METRIC,
            data_level=self._data_level(batch.source_type),
            data_source=batch.source_name,
            platform=batch.platform,
            query_range={
                "market": batch.market,
                "category": batch.category,
                "keyword": batch.keyword,
                "period_start": batch.period_start.isoformat(),
                "period_end": batch.period_end.isoformat(),
                "metric_code": item.metric_code,
                "batch_id": batch.id,
                "observation_id": item.id,
            },
            source_timestamp=item.source_timestamp,
            ingest_timestamp=batch.created_at,
            tool_call_id=context.tool_call_id,
            collection_run_id=batch.id,
            snapshot_ref=(
                batch.original_file_ref
                or f"database:market_metric_observation:{item.id}"
            ),
            sha256=digest,
            data_version=batch.data_version,
            sample_scope=self._scope(record, data_source_mode),
        )

    @staticmethod
    def _data_level(source_type: MarketMetricSourceType) -> DataLevel:
        return {
            MarketMetricSourceType.OFFICIAL_API: DataLevel.A,
            MarketMetricSourceType.OFFICIAL_REPORT: DataLevel.A,
            MarketMetricSourceType.AUTHORIZED_EXPORT: DataLevel.B,
            MarketMetricSourceType.LICENSED_PROVIDER: DataLevel.B,
            MarketMetricSourceType.MANUAL_IMPORT: DataLevel.C,
        }[source_type]


__all__ = [
    "DatabaseMarketMetricProvider",
    "DatabaseMarketMetricResult",
    "MarketMetricSelectionError",
]
