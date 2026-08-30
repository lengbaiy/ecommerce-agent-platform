from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import Field, model_validator

from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    CurrencyCode,
    DataSourceMode,
    DataStatus,
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
    NonNegativeDecimal,
    NonNegativeInt,
    SalesValueType,
    Sentiment,
)


class NormalizedProduct(MarketIntelligenceModel):
    snapshot_id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    collection_run_id: NonEmptyStr
    platform: NonEmptyStr
    market: NonEmptyStr
    product_id: NonEmptyStr
    title: NonEmptyStr
    brand: NonEmptyStr | None = None
    category: NonEmptyStr | None = None
    price: NonNegativeDecimal
    currency: CurrencyCode
    sales_display: NonEmptyStr | None = None
    sales_value: NonNegativeInt | None = None
    sales_value_type: SalesValueType = SalesValueType.UNKNOWN
    shop_name: NonEmptyStr | None = None
    rating: NonNegativeDecimal | None = None
    review_count: NonNegativeInt | None = None
    source_ref: NonEmptyStr
    source_url: NonEmptyStr | None = None
    source_snapshot_ref: NonEmptyStr
    source_timestamp: datetime
    ingest_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: DataSourceMode
    data_status: DataStatus

    @model_validator(mode="after")
    def validate_sales_value(self) -> "NormalizedProduct":
        if self.sales_value_type is not SalesValueType.UNKNOWN and self.sales_value is None:
            raise ValueError("sales_value is required when sales_value_type is known")
        return self


class NormalizedReview(MarketIntelligenceModel):
    review_id: NonEmptyStr
    collection_run_id: NonEmptyStr
    platform: NonEmptyStr
    market: NonEmptyStr
    product_id: NonEmptyStr
    content: NonEmptyStr
    rating: NonNegativeDecimal | None = None
    review_time: datetime | None = None
    verified_purchase: bool | None = None
    helpful_count: NonNegativeInt | None = None
    sentiment: Sentiment | None = None
    themes: list[NonEmptyStr] = Field(default_factory=list)
    source_ref: NonEmptyStr
    source_snapshot_ref: NonEmptyStr
    source_timestamp: datetime
    ingest_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_status: DataStatus


class MarketMetric(MarketIntelligenceModel):
    metric_code: NonEmptyStr
    value: Decimal | int | float | dict[str, Any] | list[Any] | None = None
    unit: NonEmptyStr | None = None
    status: MetricStatus
    reason_code: NonEmptyStr | None = None
    scope: AnalysisScope
    methodology: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    source_timestamp: datetime | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "MarketMetric":
        if self.status is MetricStatus.AVAILABLE:
            if self.value is None:
                raise ValueError("available market metric must provide value")
            if not self.evidence_ids:
                raise ValueError("available market metric must provide evidence_ids")
        if self.status is MetricStatus.UNAVAILABLE and self.value is not None:
            raise ValueError("unavailable market metric must not provide value")
        return self
