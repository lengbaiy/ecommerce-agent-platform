from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from math import pow

from app.modules.market_intelligence.schemas import (
    MarketMetricBatch,
    MarketMetricGrowthType,
    MarketMetricObservation,
    MarketMetricRecord,
    MarketMetricValueKind,
    MetricStatus,
)


class MacroMarketMetricCalculator:
    """根据直接观测值生成可追溯、版本化的宏观派生指标。"""

    formula_version = "1.0"
    _precision = Decimal("0.000001")

    def calculate(
        self,
        *,
        batch: MarketMetricBatch,
        direct_observations: list[MarketMetricObservation],
        history: list[MarketMetricRecord],
        calculated_at: datetime,
    ) -> list[MarketMetricObservation]:
        current = {
            item.metric_code: item
            for item in direct_observations
            if item.value_kind is MarketMetricValueKind.DIRECT
            and item.value is not None
            and item.status is not MetricStatus.UNAVAILABLE
        }
        historical = self._history_by_code(history)
        derived: list[MarketMetricObservation] = []

        # 报告中的通用 growth 优先表示整体市场规模增长，缺失时再使用 GMV。
        growth_base = current.get("market_size") or current.get("gmv")
        if growth_base is not None:
            previous = self._previous_period(
                batch,
                growth_base,
                historical.get(growth_base.metric_code, []),
            )
            if previous is not None:
                growth = self._growth(batch, growth_base, previous, calculated_at)
                if growth is not None:
                    derived.append(growth)

            cagr = self._cagr(
                batch,
                growth_base,
                historical.get(growth_base.metric_code, []),
                calculated_at,
            )
            if cagr is not None:
                derived.append(cagr)

        average_price = self._ratio_metric(
            batch=batch,
            numerator=current.get("gmv"),
            denominator=current.get("sales_volume"),
            metric_code="average_transaction_price",
            formula_code="gmv_divided_by_sales_volume",
            unit=(current.get("gmv").unit if current.get("gmv") else None),
            currency=(current.get("gmv").currency if current.get("gmv") else None),
            multiplier=Decimal("1"),
            calculated_at=calculated_at,
        )
        if average_price is not None:
            derived.append(average_price)

        market_share = self._ratio_metric(
            batch=batch,
            numerator=current.get("gmv"),
            denominator=current.get("market_size"),
            metric_code="gmv_market_share",
            formula_code="gmv_divided_by_market_size",
            unit="percent",
            currency=None,
            multiplier=Decimal("100"),
            calculated_at=calculated_at,
        )
        if market_share is not None:
            derived.append(market_share)

        return derived

    @staticmethod
    def _history_by_code(
        history: list[MarketMetricRecord],
    ) -> dict[str, list[MarketMetricRecord]]:
        grouped: dict[str, list[MarketMetricRecord]] = {}
        for record in history:
            item = record.observation
            if (
                item.value_kind is MarketMetricValueKind.DIRECT
                and item.value is not None
                and item.status is not MetricStatus.UNAVAILABLE
            ):
                grouped.setdefault(item.metric_code, []).append(record)
        for records in grouped.values():
            records.sort(key=lambda item: item.batch.period_end, reverse=True)
        return grouped

    def _previous_period(
        self,
        batch: MarketMetricBatch,
        current: MarketMetricObservation,
        history: list[MarketMetricRecord],
    ) -> MarketMetricRecord | None:
        current_days = self._period_days(batch.period_start, batch.period_end)
        period_type = self._period_type(current_days)
        if period_type is None:
            return None
        allowed_gap = {
            MarketMetricGrowthType.YOY: 10,
            MarketMetricGrowthType.QOQ: 7,
            MarketMetricGrowthType.MOM: 3,
        }[period_type]
        for record in history:
            previous = record.observation
            previous_days = self._period_days(
                record.batch.period_start,
                record.batch.period_end,
            )
            gap_days = (batch.period_start - record.batch.period_end).total_seconds() / 86400
            if (
                self._same_unit(current, previous)
                and previous.value != 0
                and abs(previous_days - current_days) <= max(3, current_days * 0.2)
                and 0 <= gap_days <= allowed_gap
            ):
                return record
        return None

    def _growth(
        self,
        batch: MarketMetricBatch,
        current: MarketMetricObservation,
        previous: MarketMetricRecord,
        calculated_at: datetime,
    ) -> MarketMetricObservation | None:
        growth_type = self._period_type(
            self._period_days(batch.period_start, batch.period_end)
        )
        if growth_type is None or current.value is None or previous.observation.value is None:
            return None
        value = ((current.value - previous.observation.value) / abs(previous.observation.value)) * 100
        return self._derived(
            batch=batch,
            metric_code="growth",
            value=self._round(value),
            unit="percent",
            status=self._combined_status(current, previous.observation),
            methodology=(
                f"{growth_type.value} growth calculated from consecutive "
                f"{current.metric_code} observations."
            ),
            source_timestamp=current.source_timestamp,
            source_ids=[previous.observation.id, current.id],
            formula_code=f"{current.metric_code}_{growth_type.value}_growth",
            calculated_at=calculated_at,
            growth_type=growth_type,
            comparison_start=previous.batch.period_start,
            comparison_end=previous.batch.period_end,
        )

    def _cagr(
        self,
        batch: MarketMetricBatch,
        current: MarketMetricObservation,
        history: list[MarketMetricRecord],
        calculated_at: datetime,
    ) -> MarketMetricObservation | None:
        if self._period_type(self._period_days(batch.period_start, batch.period_end)) is not MarketMetricGrowthType.YOY:
            return None
        candidates = [
            record
            for record in history
            if self._same_unit(current, record.observation)
            and record.observation.value is not None
            and record.observation.value > 0
        ]
        if not candidates or current.value is None or current.value <= 0:
            return None
        earliest = min(candidates, key=lambda item: item.batch.period_end)
        years = (batch.period_end - earliest.batch.period_end).total_seconds() / (365.2425 * 86400)
        if years < 1.5:
            return None
        try:
            factor = pow(float(current.value / earliest.observation.value), 1 / years)
        except (OverflowError, ValueError):
            return None
        value = (Decimal(str(factor)) - 1) * 100
        return self._derived(
            batch=batch,
            metric_code="cagr",
            value=self._round(value),
            unit="percent",
            status=self._combined_status(current, earliest.observation),
            methodology=f"CAGR calculated from {current.metric_code} over {years:.2f} years.",
            source_timestamp=current.source_timestamp,
            source_ids=[earliest.observation.id, current.id],
            formula_code=f"{current.metric_code}_cagr",
            calculated_at=calculated_at,
            growth_type=MarketMetricGrowthType.CAGR,
            comparison_start=earliest.batch.period_start,
            comparison_end=earliest.batch.period_end,
        )

    def _ratio_metric(
        self,
        *,
        batch: MarketMetricBatch,
        numerator: MarketMetricObservation | None,
        denominator: MarketMetricObservation | None,
        metric_code: str,
        formula_code: str,
        unit: str | None,
        currency: str | None,
        multiplier: Decimal,
        calculated_at: datetime,
    ) -> MarketMetricObservation | None:
        if (
            numerator is None
            or denominator is None
            or numerator.value is None
            or denominator.value is None
            or denominator.value <= 0
        ):
            return None
        value = (numerator.value / denominator.value) * multiplier
        return self._derived(
            batch=batch,
            metric_code=metric_code,
            value=self._round(value),
            unit=unit,
            currency=currency,
            status=self._combined_status(numerator, denominator),
            methodology=f"Calculated as {numerator.metric_code} divided by {denominator.metric_code}.",
            source_timestamp=numerator.source_timestamp,
            source_ids=[numerator.id, denominator.id],
            formula_code=formula_code,
            calculated_at=calculated_at,
        )

    def _derived(
        self,
        *,
        batch: MarketMetricBatch,
        metric_code: str,
        value: Decimal,
        unit: str | None,
        status: MetricStatus,
        methodology: str,
        source_timestamp: datetime,
        source_ids: list[str],
        formula_code: str,
        calculated_at: datetime,
        currency: str | None = None,
        growth_type: MarketMetricGrowthType | None = None,
        comparison_start: datetime | None = None,
        comparison_end: datetime | None = None,
    ) -> MarketMetricObservation:
        return MarketMetricObservation(
            tenant_id=batch.tenant_id,
            trace_id=batch.trace_id,
            created_at=calculated_at,
            batch_id=batch.id,
            metric_code=metric_code,
            value_kind=MarketMetricValueKind.DERIVED,
            value=value,
            unit=unit,
            currency=currency,
            status=status,
            methodology=methodology,
            source_timestamp=source_timestamp,
            growth_type=growth_type,
            comparison_period_start=comparison_start,
            comparison_period_end=comparison_end,
            formula_code=formula_code,
            formula_version=self.formula_version,
            source_observation_ids=source_ids,
            calculated_at=calculated_at,
        )

    @staticmethod
    def _period_days(start: datetime, end: datetime) -> float:
        return ((end - start).total_seconds() / 86400) + 1

    @staticmethod
    def _period_type(days: float) -> MarketMetricGrowthType | None:
        if 300 <= days <= 370:
            return MarketMetricGrowthType.YOY
        if 70 <= days <= 110:
            return MarketMetricGrowthType.QOQ
        if 20 <= days <= 40:
            return MarketMetricGrowthType.MOM
        return None

    @staticmethod
    def _same_unit(
        left: MarketMetricObservation,
        right: MarketMetricObservation,
    ) -> bool:
        return left.unit == right.unit and left.currency == right.currency

    @staticmethod
    def _combined_status(
        *items: MarketMetricObservation,
    ) -> MetricStatus:
        priority = {
            MetricStatus.CONFLICT: 4,
            MetricStatus.STALE: 3,
            MetricStatus.PARTIAL: 2,
            MetricStatus.AVAILABLE: 1,
            MetricStatus.UNAVAILABLE: 0,
        }
        return max((item.status for item in items), key=priority.__getitem__)

    def _round(self, value: Decimal) -> Decimal:
        return value.quantize(self._precision, rounding=ROUND_HALF_UP)


__all__ = ["MacroMarketMetricCalculator"]
