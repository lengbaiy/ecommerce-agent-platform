from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CurrencyCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$"),
]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"))]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"))]
Ratio = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
Margin = Annotated[Decimal, Field(le=Decimal("1"))]


class MarketIntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DataSourceMode(StrEnum):
    FIXED_DATASET = "fixed_dataset"
    OFFICIAL_API = "official_api"


class SalesValueType(StrEnum):
    EXACT = "exact"
    LOWER_BOUND = "lower_bound"
    RANGE = "range"
    UNKNOWN = "unknown"


class DataStatus(StrEnum):
    VALID = "valid"
    DEMO_ONLY = "demo_only"
    STALE = "stale"
    PARTIAL = "partial"


class MetricStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    STALE = "stale"
    CONFLICT = "conflict"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ProfitStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class EntryDecision(StrEnum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnalysisScope(MarketIntelligenceModel):
    market: NonEmptyStr
    platforms: list[NonEmptyStr]
    category: NonEmptyStr
    keyword: NonEmptyStr
    start_time: datetime | None = None
    end_time: datetime | None = None
    requested_product_count: NonNegativeInt
    actual_product_count: NonNegativeInt
    actual_review_count: NonNegativeInt
    data_source_mode: DataSourceMode

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("platforms must contain at least one platform")
        if len(value) != len(set(value)):
            raise ValueError("platforms must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_scope(self) -> "AnalysisScope":
        if self.actual_product_count > self.requested_product_count:
            raise ValueError("actual_product_count cannot exceed requested_product_count")
        if self.start_time is not None and self.end_time is not None:
            try:
                invalid_range = self.start_time > self.end_time
            except TypeError as exc:
                raise ValueError("start_time and end_time must use compatible timezones") from exc
            if invalid_range:
                raise ValueError("start_time cannot be later than end_time")
        return self
