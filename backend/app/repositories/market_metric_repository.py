from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import MarketMetricBatchRecord, MarketMetricObservationRecord
from app.modules.market_intelligence.schemas import (
    MarketMetricBatch,
    MarketMetricBatchStatus,
    MarketMetricGrowthType,
    MarketMetricObservation,
    MarketMetricRecord,
    MarketMetricSourceType,
    MarketMetricValueKind,
    MetricStatus,
)


class MarketMetricConflictError(RuntimeError):
    pass


class MarketMetricNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class MarketMetricOverviewStats:
    approved_batch_count: int
    available_metric_count: int


class MarketMetricRepository(Protocol):
    def scope_version_exists(self, batch: MarketMetricBatch) -> bool: ...

    def create_batch(
        self,
        batch: MarketMetricBatch,
        direct_observations: list[MarketMetricObservation],
        derived_observations: Sequence[MarketMetricObservation] = (),
    ) -> MarketMetricBatch: ...

    def add_derived_observations(
        self,
        batch_id: str,
        tenant_id: str,
        observations: Sequence[MarketMetricObservation],
    ) -> None: ...

    def get_batch(self, batch_id: str, tenant_id: str) -> MarketMetricBatch: ...

    def list_batches(
        self,
        *,
        tenant_id: str,
        status: MarketMetricBatchStatus | None = None,
        platform: str | None = None,
        market: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketMetricBatch]: ...

    def count_batches(
        self,
        *,
        tenant_id: str,
        status: MarketMetricBatchStatus | None = None,
        platform: str | None = None,
        market: str | None = None,
    ) -> int: ...

    def overview_stats(
        self,
        *,
        tenant_id: str,
        market: str,
    ) -> MarketMetricOverviewStats: ...

    def list_batch_observations(
        self,
        *,
        batch_id: str,
        tenant_id: str,
    ) -> list[MarketMetricObservation]: ...

    def list_direct_history(
        self,
        *,
        tenant_id: str,
        platform: str,
        market: str,
        category: str,
        keyword: str,
        metric_codes: tuple[str, ...] = (),
        period_end_before: datetime | None = None,
        limit: int = 200,
    ) -> list[MarketMetricRecord]: ...

    def list_approved(
        self,
        *,
        tenant_id: str,
        platform: str,
        market: str,
        category: str,
        keyword: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        metric_codes: tuple[str, ...] = (),
        limit: int = 200,
    ) -> list[MarketMetricRecord]: ...

    def update_batch_status(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        status: MarketMetricBatchStatus,
        reviewed_by: str,
        reviewed_at: datetime,
        review_note: str | None = None,
        review_codes: Sequence[str] = (),
    ) -> MarketMetricBatch: ...


class SQLAlchemyMarketMetricRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def scope_version_exists(self, batch: MarketMetricBatch) -> bool:
        with self.session_factory() as session:
            statement = select(MarketMetricBatchRecord.id).where(
                *self._scope_conditions(batch),
                MarketMetricBatchRecord.period_start == batch.period_start,
                MarketMetricBatchRecord.period_end == batch.period_end,
                MarketMetricBatchRecord.source_name == batch.source_name,
                MarketMetricBatchRecord.data_version == batch.data_version,
            )
            return session.scalar(statement.limit(1)) is not None

    def create_batch(
        self,
        batch: MarketMetricBatch,
        direct_observations: list[MarketMetricObservation],
        derived_observations: Sequence[MarketMetricObservation] = (),
    ) -> MarketMetricBatch:
        self._validate_observations(
            batch,
            direct_observations,
            expected_kind=MarketMetricValueKind.DIRECT,
        )
        if derived_observations:
            self._validate_observations(
                batch,
                derived_observations,
                expected_kind=MarketMetricValueKind.DERIVED,
            )
        codes = {item.metric_code for item in direct_observations}
        if codes.intersection(item.metric_code for item in derived_observations):
            raise ValueError("direct and derived metric codes must be unique")
        try:
            with self.session_factory() as session:
                with session.begin():
                    if derived_observations:
                        self._validate_source_observations(
                            session,
                            batch,
                            derived_observations,
                            current_direct_ids={item.id for item in direct_observations},
                        )
                    session.add(self._to_batch_record(batch))
                    session.add_all(
                        self._to_observation_record(item)
                        for item in [*direct_observations, *derived_observations]
                    )
        except IntegrityError as exc:
            raise MarketMetricConflictError(
                "market metric batch or metric_code already exists"
            ) from exc
        return batch

    def add_derived_observations(
        self,
        batch_id: str,
        tenant_id: str,
        observations: Sequence[MarketMetricObservation],
    ) -> None:
        if not observations:
            return
        try:
            with self.session_factory() as session:
                with session.begin():
                    target = self._get_batch_record(session, batch_id, tenant_id)
                    batch = self._to_batch(target)
                    self._validate_observations(
                        batch,
                        observations,
                        expected_kind=MarketMetricValueKind.DERIVED,
                    )
                    self._validate_source_observations(
                        session,
                        batch,
                        observations,
                        current_direct_ids=set(),
                    )
                    session.add_all(
                        self._to_observation_record(item)
                        for item in observations
                    )
        except IntegrityError as exc:
            raise MarketMetricConflictError(
                "derived market metric already exists in this batch"
            ) from exc

    def get_batch(self, batch_id: str, tenant_id: str) -> MarketMetricBatch:
        with self.session_factory() as session:
            return self._to_batch(self._get_batch_record(session, batch_id, tenant_id))

    def list_batches(
        self,
        *,
        tenant_id: str,
        status: MarketMetricBatchStatus | None = None,
        platform: str | None = None,
        market: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketMetricBatch]:
        if limit < 1 or offset < 0:
            raise ValueError("invalid market metric batch pagination")
        conditions = [MarketMetricBatchRecord.tenant_id == tenant_id]
        if status is not None:
            conditions.append(MarketMetricBatchRecord.status == status.value)
        if platform is not None:
            conditions.append(MarketMetricBatchRecord.platform == platform.casefold())
        if market is not None:
            conditions.append(MarketMetricBatchRecord.market == market.upper())
        statement = (
            select(MarketMetricBatchRecord)
            .where(*conditions)
            .order_by(
                MarketMetricBatchRecord.created_at.desc(),
                MarketMetricBatchRecord.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        with self.session_factory() as session:
            return [self._to_batch(item) for item in session.scalars(statement)]

    def count_batches(
        self,
        *,
        tenant_id: str,
        status: MarketMetricBatchStatus | None = None,
        platform: str | None = None,
        market: str | None = None,
    ) -> int:
        conditions = [MarketMetricBatchRecord.tenant_id == tenant_id]
        if status is not None:
            conditions.append(MarketMetricBatchRecord.status == status.value)
        if platform is not None:
            conditions.append(MarketMetricBatchRecord.platform == platform.casefold())
        if market is not None:
            conditions.append(MarketMetricBatchRecord.market == market.upper())
        statement = select(func.count(MarketMetricBatchRecord.id)).where(*conditions)
        with self.session_factory() as session:
            return int(session.scalar(statement) or 0)

    def overview_stats(
        self,
        *,
        tenant_id: str,
        market: str,
    ) -> MarketMetricOverviewStats:
        conditions = (
            MarketMetricBatchRecord.tenant_id == tenant_id,
            MarketMetricBatchRecord.market == market.upper(),
            MarketMetricBatchRecord.status == MarketMetricBatchStatus.APPROVED.value,
        )
        with self.session_factory() as session:
            batch_count = session.scalar(
                select(func.count(MarketMetricBatchRecord.id)).where(*conditions)
            )
            metric_count = session.scalar(
                select(func.count(MarketMetricObservationRecord.id))
                .join(
                    MarketMetricBatchRecord,
                    MarketMetricBatchRecord.id == MarketMetricObservationRecord.batch_id,
                )
                .where(
                    *conditions,
                    MarketMetricObservationRecord.status == MetricStatus.AVAILABLE.value,
                )
            )
        return MarketMetricOverviewStats(
            approved_batch_count=int(batch_count or 0),
            available_metric_count=int(metric_count or 0),
        )

    def list_batch_observations(
        self,
        *,
        batch_id: str,
        tenant_id: str,
    ) -> list[MarketMetricObservation]:
        statement = (
            select(MarketMetricObservationRecord)
            .join(
                MarketMetricBatchRecord,
                MarketMetricBatchRecord.id == MarketMetricObservationRecord.batch_id,
            )
            .where(
                MarketMetricObservationRecord.batch_id == batch_id,
                MarketMetricObservationRecord.tenant_id == tenant_id,
                MarketMetricBatchRecord.tenant_id == tenant_id,
            )
            .order_by(
                MarketMetricObservationRecord.value_kind.asc(),
                MarketMetricObservationRecord.metric_code.asc(),
            )
        )
        with self.session_factory() as session:
            if session.scalar(
                select(MarketMetricBatchRecord.id).where(
                    MarketMetricBatchRecord.id == batch_id,
                    MarketMetricBatchRecord.tenant_id == tenant_id,
                )
            ) is None:
                raise MarketMetricNotFoundError("market metric batch not found")
            return [self._to_observation(item) for item in session.scalars(statement)]

    def list_direct_history(
        self,
        *,
        tenant_id: str,
        platform: str,
        market: str,
        category: str,
        keyword: str,
        metric_codes: tuple[str, ...] = (),
        period_end_before: datetime | None = None,
        limit: int = 200,
    ) -> list[MarketMetricRecord]:
        conditions = [
            MarketMetricBatchRecord.tenant_id == tenant_id,
            MarketMetricBatchRecord.platform == platform.casefold(),
            MarketMetricBatchRecord.market == market.upper(),
            MarketMetricBatchRecord.category == category.casefold(),
            MarketMetricBatchRecord.keyword == keyword.casefold(),
            MarketMetricBatchRecord.status == MarketMetricBatchStatus.APPROVED.value,
            MarketMetricObservationRecord.value_kind == MarketMetricValueKind.DIRECT.value,
        ]
        if metric_codes:
            conditions.append(
                MarketMetricObservationRecord.metric_code.in_(
                    code.casefold() for code in metric_codes
                )
            )
        if period_end_before is not None:
            conditions.append(MarketMetricBatchRecord.period_end < period_end_before)
        return self._list_records(conditions, limit)

    def list_approved(
        self,
        *,
        tenant_id: str,
        platform: str,
        market: str,
        category: str,
        keyword: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        metric_codes: tuple[str, ...] = (),
        limit: int = 200,
    ) -> list[MarketMetricRecord]:
        if (period_start is None) != (period_end is None):
            raise ValueError("period_start and period_end must be provided together")
        conditions = [
            MarketMetricBatchRecord.tenant_id == tenant_id,
            MarketMetricBatchRecord.platform == platform.casefold(),
            MarketMetricBatchRecord.market == market.upper(),
            MarketMetricBatchRecord.category == category.casefold(),
            MarketMetricBatchRecord.keyword == keyword.casefold(),
            MarketMetricBatchRecord.status == MarketMetricBatchStatus.APPROVED.value,
        ]
        if period_start is not None and period_end is not None:
            conditions.extend(
                (
                    MarketMetricBatchRecord.period_start == period_start,
                    MarketMetricBatchRecord.period_end == period_end,
                )
            )
        if metric_codes:
            conditions.append(
                MarketMetricObservationRecord.metric_code.in_(
                    code.casefold() for code in metric_codes
                )
            )
        return self._list_records(conditions, limit)

    def update_batch_status(
        self,
        *,
        batch_id: str,
        tenant_id: str,
        status: MarketMetricBatchStatus,
        reviewed_by: str,
        reviewed_at: datetime,
        review_note: str | None = None,
        review_codes: Sequence[str] = (),
    ) -> MarketMetricBatch:
        with self.session_factory() as session:
            with session.begin():
                record = self._get_batch_record(
                    session,
                    batch_id,
                    tenant_id,
                    for_update=True,
                )
                record.status = status.value
                record.reviewed_by = reviewed_by
                record.reviewed_at = reviewed_at
                record.review_note = review_note
                record.review_codes = list(review_codes)
                record.updated_at = reviewed_at
                session.flush()
                return self._to_batch(record)

    def _list_records(self, conditions: list, limit: int) -> list[MarketMetricRecord]:
        if limit < 1:
            raise ValueError("limit must be greater than 0")
        statement = (
            select(MarketMetricBatchRecord, MarketMetricObservationRecord)
            .join(
                MarketMetricObservationRecord,
                MarketMetricObservationRecord.batch_id == MarketMetricBatchRecord.id,
            )
            .where(*conditions)
            .order_by(
                MarketMetricBatchRecord.period_end.desc(),
                MarketMetricBatchRecord.created_at.desc(),
                MarketMetricObservationRecord.metric_code.asc(),
            )
            .limit(limit)
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
            return [
                MarketMetricRecord(
                    batch=self._to_batch(batch),
                    observation=self._to_observation(observation),
                )
                for batch, observation in rows
            ]

    @staticmethod
    def _scope_conditions(batch: MarketMetricBatch) -> tuple:
        return (
            MarketMetricBatchRecord.tenant_id == batch.tenant_id,
            MarketMetricBatchRecord.platform == batch.platform,
            MarketMetricBatchRecord.market == batch.market,
            MarketMetricBatchRecord.category == batch.category,
            MarketMetricBatchRecord.keyword == batch.keyword,
        )

    @staticmethod
    def _get_batch_record(
        session: Session,
        batch_id: str,
        tenant_id: str,
        *,
        for_update: bool = False,
    ) -> MarketMetricBatchRecord:
        statement = select(MarketMetricBatchRecord).where(
            MarketMetricBatchRecord.id == batch_id,
            MarketMetricBatchRecord.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        record = session.scalar(statement)
        if record is None:
            raise MarketMetricNotFoundError("market metric batch not found")
        return record

    @staticmethod
    def _validate_observations(
        batch: MarketMetricBatch,
        observations: Sequence[MarketMetricObservation],
        *,
        expected_kind: MarketMetricValueKind,
    ) -> None:
        if not observations:
            raise ValueError("market metric batch must contain observations")
        codes: set[str] = set()
        ids: set[str] = set()
        for item in observations:
            if item.batch_id != batch.id or item.tenant_id != batch.tenant_id:
                raise ValueError("observation must belong to the target batch and tenant")
            if item.trace_id != batch.trace_id:
                raise ValueError("observation trace_id must match batch trace_id")
            if item.value_kind is not expected_kind:
                raise ValueError(f"observation value_kind must be {expected_kind.value}")
            if item.metric_code in codes or item.id in ids:
                raise ValueError("observation ids and metric codes must be unique")
            codes.add(item.metric_code)
            ids.add(item.id)

    @staticmethod
    def _validate_source_observations(
        session: Session,
        batch: MarketMetricBatch,
        observations: list[MarketMetricObservation],
        *,
        current_direct_ids: set[str],
    ) -> None:
        source_ids = {
            source_id
            for item in observations
            for source_id in item.source_observation_ids
        }
        persisted_source_ids = source_ids - current_direct_ids
        statement = (
            select(
                MarketMetricObservationRecord.id,
                MarketMetricObservationRecord.value_kind,
                MarketMetricObservationRecord.status,
                MarketMetricBatchRecord,
            )
            .join(
                MarketMetricBatchRecord,
                MarketMetricBatchRecord.id == MarketMetricObservationRecord.batch_id,
            )
            .where(
                MarketMetricObservationRecord.id.in_(persisted_source_ids),
                MarketMetricObservationRecord.tenant_id == batch.tenant_id,
            )
        )
        rows = session.execute(statement).all()
        if {source_id for source_id, _, _, _ in rows} != persisted_source_ids:
            raise ValueError("derived metric contains unknown source observations")
        for _, value_kind, status, source_batch in rows:
            if value_kind != MarketMetricValueKind.DIRECT.value:
                raise ValueError("derived metric sources must be direct observations")
            if status == MetricStatus.UNAVAILABLE.value:
                raise ValueError("derived metric sources must contain usable values")
            if (
                source_batch.platform,
                source_batch.market,
                source_batch.category,
                source_batch.keyword,
            ) != (batch.platform, batch.market, batch.category, batch.keyword):
                raise ValueError("derived metric sources must use the same market scope")
            if (
                source_batch.id != batch.id
                and source_batch.status != MarketMetricBatchStatus.APPROVED.value
            ):
                raise ValueError("historical source observations must be approved")

    @staticmethod
    def _to_batch_record(batch: MarketMetricBatch) -> MarketMetricBatchRecord:
        return MarketMetricBatchRecord(
            id=batch.id,
            tenant_id=batch.tenant_id,
            trace_id=batch.trace_id,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
            platform=batch.platform,
            market=batch.market,
            category=batch.category,
            keyword=batch.keyword,
            period_start=batch.period_start,
            period_end=batch.period_end,
            source_name=batch.source_name,
            source_type=batch.source_type.value,
            source_description=batch.source_description,
            source_timestamp=batch.source_timestamp,
            methodology=batch.methodology,
            license_or_authorization=batch.license_or_authorization,
            data_version=batch.data_version,
            original_file_ref=batch.original_file_ref,
            original_file_sha256=batch.original_file_sha256,
            status=batch.status.value,
            uploaded_by=batch.uploaded_by,
            reviewed_by=batch.reviewed_by,
            reviewed_at=batch.reviewed_at,
            review_note=batch.review_note,
            review_codes=list(batch.review_codes),
        )

    @staticmethod
    def _to_observation_record(
        item: MarketMetricObservation,
    ) -> MarketMetricObservationRecord:
        return MarketMetricObservationRecord(
            id=item.id,
            tenant_id=item.tenant_id,
            trace_id=item.trace_id,
            created_at=item.created_at,
            batch_id=item.batch_id,
            metric_code=item.metric_code,
            value_kind=item.value_kind.value,
            value=item.value,
            unit=item.unit,
            currency=item.currency,
            status=item.status.value,
            reason_code=item.reason_code,
            methodology=item.methodology,
            source_timestamp=item.source_timestamp,
            growth_type=item.growth_type.value if item.growth_type else None,
            comparison_period_start=item.comparison_period_start,
            comparison_period_end=item.comparison_period_end,
            formula_code=item.formula_code,
            formula_version=item.formula_version,
            source_observation_ids=list(item.source_observation_ids),
            calculated_at=item.calculated_at,
        )

    @staticmethod
    def _to_batch(record: MarketMetricBatchRecord) -> MarketMetricBatch:
        return MarketMetricBatch(
            id=record.id,
            tenant_id=record.tenant_id,
            trace_id=record.trace_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            platform=record.platform,
            market=record.market,
            category=record.category,
            keyword=record.keyword,
            period_start=record.period_start,
            period_end=record.period_end,
            source_name=record.source_name,
            source_type=MarketMetricSourceType(record.source_type),
            source_description=record.source_description,
            source_timestamp=record.source_timestamp,
            methodology=record.methodology,
            license_or_authorization=record.license_or_authorization,
            data_version=record.data_version,
            original_file_ref=record.original_file_ref,
            original_file_sha256=record.original_file_sha256,
            status=MarketMetricBatchStatus(record.status),
            uploaded_by=record.uploaded_by,
            reviewed_by=record.reviewed_by,
            reviewed_at=record.reviewed_at,
            review_note=record.review_note,
            review_codes=list(record.review_codes or []),
        )

    @staticmethod
    def _to_observation(
        record: MarketMetricObservationRecord,
    ) -> MarketMetricObservation:
        return MarketMetricObservation(
            id=record.id,
            tenant_id=record.tenant_id,
            trace_id=record.trace_id,
            created_at=record.created_at,
            batch_id=record.batch_id,
            metric_code=record.metric_code,
            value_kind=MarketMetricValueKind(record.value_kind),
            value=record.value,
            unit=record.unit,
            currency=record.currency,
            status=MetricStatus(record.status),
            reason_code=record.reason_code,
            methodology=record.methodology,
            source_timestamp=record.source_timestamp,
            growth_type=(
                MarketMetricGrowthType(record.growth_type)
                if record.growth_type
                else None
            ),
            comparison_period_start=record.comparison_period_start,
            comparison_period_end=record.comparison_period_end,
            formula_code=record.formula_code,
            formula_version=record.formula_version,
            source_observation_ids=list(record.source_observation_ids),
            calculated_at=record.calculated_at,
        )


__all__ = [
    "MarketMetricConflictError",
    "MarketMetricNotFoundError",
    "MarketMetricOverviewStats",
    "MarketMetricRepository",
    "SQLAlchemyMarketMetricRepository",
]
