from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import Field, StringConstraints, model_validator

from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    DataSourceMode,
    MarketIntelligenceModel,
    NonEmptyStr,
    NonNegativeInt,
)
from app.modules.market_intelligence.schemas.market_metric import MarketMetricProductMatch


class ProductSort(StrEnum):
    DEFAULT = "default"
    SALES_DESC = "sales_desc"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


class CollectionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EvidenceType(StrEnum):
    PRODUCT = "product"
    REVIEW = "review"
    MARKET_METRIC = "market_metric"
    PROFIT_INPUT = "profit_input"
    DATASET = "dataset"
    API_RESPONSE = "api_response"


class DataLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class DatasetSourceType(StrEnum):
    SYNTHETIC = "synthetic"
    AUTHORIZED_EXPORT = "authorized_export"
    ANONYMIZED_SNAPSHOT = "anonymized_snapshot"


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{64}$")]


class DatasetManifest(MarketIntelligenceModel):
    dataset_id: NonEmptyStr
    dataset_version: NonEmptyStr
    schema_version: NonEmptyStr
    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    aliases: list[NonEmptyStr] = Field(default_factory=list)
    source_type: DatasetSourceType
    source_description: NonEmptyStr
    generated_at: datetime                  # fixed data 生成的时间
    source_timestamp: datetime              # 数据来源快照时间
    expires_at: datetime | None = None      # 数据过期时间
    dataset_start_time: datetime | None = None # 这份数据覆盖哪个时间段
    dataset_end_time: datetime | None = None
    license_or_authorization: NonEmptyStr
    checksums: dict[NonEmptyStr, Sha256]

    @model_validator(mode="after")
    def validate_manifest(self) -> "DatasetManifest":
        if not self.checksums:
            raise ValueError("checksums must contain at least one dataset file")
        normalized_aliases = [" ".join(alias.casefold().split()) for alias in self.aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError("aliases must not contain duplicates")
        if self.expires_at is not None:
            try:
                invalid_range = self.expires_at <= self.generated_at
            except TypeError as exc:
                raise ValueError(
                    "generated_at and expires_at must use compatible timezones"
                ) from exc
            if invalid_range:
                raise ValueError("expires_at must be later than generated_at")
        return self


class ProductSearchRequest(MarketIntelligenceModel):
    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    product_limit: int = Field(ge=1, le=50)
    sort_by: ProductSort = ProductSort.DEFAULT


class ReviewSearchRequest(MarketIntelligenceModel):
    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    product_ids: list[NonEmptyStr] = Field(min_length=1)
    review_limit_per_product: int = Field(ge=1,)

class MarketDataRequest(MarketIntelligenceModel):
    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    market_metric_batch_id: NonEmptyStr | None = None
    market_metric_product_match: MarketMetricProductMatch | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "MarketDataRequest":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError(
                "start_time must not be later than end_time"
            )

        return self


class AdapterCapabilities(MarketIntelligenceModel):
    platform: NonEmptyStr
    data_source_mode: DataSourceMode
    supports_products: bool
    supports_reviews: bool
    supports_market_metrics: bool
    max_products: int = Field(ge=1)
    max_reviews_per_product: NonNegativeInt
    adapter_version: NonEmptyStr
    schema_version: NonEmptyStr = "1.0"


class CollectionRun(MarketIntelligenceModel):
    id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    task_id: NonEmptyStr
    trace_id: NonEmptyStr
    tenant_id: NonEmptyStr
    keyword: NonEmptyStr
    requested_count: NonNegativeInt
    actual_count: NonNegativeInt = 0
    status: CollectionStatus = CollectionStatus.PENDING
    stop_reason: NonEmptyStr | None = None
    adapter_version: NonEmptyStr
    parser_version: NonEmptyStr | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class EvidenceReference(MarketIntelligenceModel):
    evidence_id: NonEmptyStr
    evidence_type: EvidenceType
    data_level: DataLevel
    data_source: NonEmptyStr
    platform: NonEmptyStr
    product_id: NonEmptyStr | None = None
    review_id: NonEmptyStr | None = None
    query_range: dict[str, Any]
    source_timestamp: datetime
    ingest_timestamp: datetime
    tool_call_id: NonEmptyStr
    collection_run_id: NonEmptyStr
    snapshot_ref: NonEmptyStr
    sha256: NonEmptyStr
    data_version: NonEmptyStr
    sample_scope: AnalysisScope
