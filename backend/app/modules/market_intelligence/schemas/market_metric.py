from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.modules.market_intelligence.schemas.common import (
    CurrencyCode,
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
)


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-fA-F]{64}$")]
FiniteDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]
SYSTEM_DERIVED_METRIC_CODES = frozenset(
    {"growth", "cagr", "average_transaction_price", "gmv_market_share"}
)
NON_NEGATIVE_DIRECT_METRIC_CODES = frozenset(
    {
        "market_size",
        "gmv",
        "sales_volume",
        "order_count",
        "active_product_count",
        "active_brand_count",
        "category_traffic",
    }
)


class MarketMetricBatchStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISABLED = "disabled"


class MarketMetricValueKind(StrEnum):
    DIRECT = "direct"
    DERIVED = "derived"


class MarketMetricSourceType(StrEnum):
    OFFICIAL_API = "official_api"
    OFFICIAL_REPORT = "official_report"
    LICENSED_PROVIDER = "licensed_provider"
    AUTHORIZED_EXPORT = "authorized_export"
    MANUAL_IMPORT = "manual_import"


class MarketMetricGrowthType(StrEnum):
    YOY = "yoy"
    QOQ = "qoq"
    MOM = "mom"
    CAGR = "cagr"


class MarketMetricApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class MarketMetricProductDecision(StrEnum):
    SAME_PRODUCT = "same_product"
    DIFFERENT_PRODUCT = "different_product"
    UNCERTAIN = "uncertain"


class MarketMetricProductMatchMethod(StrEnum):
    DETERMINISTIC_ALIAS = "deterministic_alias"
    DETERMINISTIC_EXACT = "deterministic_exact"
    LLM = "llm"
    UNAVAILABLE = "unavailable"


class FrozenMarketMetricModel(MarketIntelligenceModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class MarketMetricProductMatch(FrozenMarketMetricModel):
    """宏观指标批次与任务商品的一致性判断。"""

    batch_id: NonEmptyStr
    decision: MarketMetricProductDecision
    confidence: float = Field(ge=0, le=1)
    requested_product: NonEmptyStr
    batch_product: NonEmptyStr
    requested_normalized_name: NonEmptyStr
    batch_normalized_name: NonEmptyStr
    reason: NonEmptyStr
    method: MarketMetricProductMatchMethod
    provider: NonEmptyStr | None = None
    model: NonEmptyStr | None = None
    prompt_version: NonEmptyStr


class DirectMarketMetricInput(FrozenMarketMetricModel):
    """运营人员可提交的数据源直接观测值。"""

    metric_code: NonEmptyStr
    value: FiniteDecimal
    unit: NonEmptyStr
    currency: CurrencyCode | None = None
    status: MetricStatus = MetricStatus.AVAILABLE
    reason_code: NonEmptyStr | None = None
    methodology: NonEmptyStr | None = None
    source_timestamp: datetime | None = None
    growth_type: MarketMetricGrowthType | None = None
    comparison_period_start: datetime | None = None
    comparison_period_end: datetime | None = None

    @field_validator("metric_code")
    @classmethod
    def normalize_metric_code(cls, value: str) -> str:
        return value.casefold()

    @model_validator(mode="after")
    def validate_direct_metric(self) -> "DirectMarketMetricInput":
        if self.metric_code in SYSTEM_DERIVED_METRIC_CODES:
            raise ValueError(
                "system-derived metric_code cannot be submitted as a direct metric"
            )
        if self.metric_code in NON_NEGATIVE_DIRECT_METRIC_CODES and self.value < 0:
            raise ValueError("market totals and counts must not be negative")
        if self.status in {MetricStatus.UNAVAILABLE, MetricStatus.CONFLICT}:
            raise ValueError("uploaded direct metric must contain an observed value")
        if self.currency is not None and self.unit.upper() != self.currency:
            raise ValueError("monetary metric unit must match currency")
        _validate_optional_period(
            self.comparison_period_start,
            self.comparison_period_end,
            "comparison period",
        )
        return self


class MarketMetricBatchCreate(FrozenMarketMetricModel):
    """一次上传共享的市场范围、统计周期和来源信息。"""

    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    period_start: datetime
    period_end: datetime
    source_name: NonEmptyStr
    source_type: MarketMetricSourceType
    source_description: NonEmptyStr | None = None
    source_timestamp: datetime
    methodology: NonEmptyStr
    license_or_authorization: NonEmptyStr
    data_version: NonEmptyStr

    @field_validator("platform", "category", "keyword")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        return value.casefold()

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_period(self) -> "MarketMetricBatchCreate":
        _validate_period(self.period_start, self.period_end, "period")
        return self


class MarketMetricStoredFile(FrozenMarketMetricModel):
    """文件存储组件生成的引用和内容摘要，不由运营人员手工填写。"""

    file_ref: NonEmptyStr
    sha256: Sha256


class MarketMetricUploadContext(FrozenMarketMetricModel):
    tenant_id: NonEmptyStr
    trace_id: NonEmptyStr
    user_id: NonEmptyStr


class MarketMetricUploadRequest(FrozenMarketMetricModel):
    schema_version: Literal["1.0"] = "1.0"
    batch: MarketMetricBatchCreate
    metrics: list[DirectMarketMetricInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> "MarketMetricUploadRequest":
        codes = [item.metric_code.casefold() for item in self.metrics]
        if len(codes) != len(set(codes)):
            raise ValueError("metric_code must be unique within one upload batch")
        return self


class MarketMetricBatch(FrozenMarketMetricModel):
    id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    tenant_id: NonEmptyStr
    trace_id: NonEmptyStr
    created_at: datetime
    updated_at: datetime
    platform: NonEmptyStr
    market: NonEmptyStr
    category: NonEmptyStr
    keyword: NonEmptyStr
    period_start: datetime
    period_end: datetime
    source_name: NonEmptyStr
    source_type: MarketMetricSourceType
    source_description: NonEmptyStr | None = None
    source_timestamp: datetime
    methodology: NonEmptyStr
    license_or_authorization: NonEmptyStr
    data_version: NonEmptyStr
    original_file_ref: NonEmptyStr | None = None
    original_file_sha256: Sha256 | None = None
    status: MarketMetricBatchStatus = MarketMetricBatchStatus.PENDING_REVIEW
    uploaded_by: NonEmptyStr
    reviewed_by: NonEmptyStr | None = None
    reviewed_at: datetime | None = None
    review_note: NonEmptyStr | None = None
    review_codes: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("platform", "category", "keyword")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        return value.casefold()

    @field_validator("market")
    @classmethod
    def normalize_market(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_batch(self) -> "MarketMetricBatch":
        _validate_period(self.period_start, self.period_end, "period")
        if bool(self.original_file_ref) != bool(self.original_file_sha256):
            raise ValueError("original file reference and sha256 must be provided together")
        if (self.reviewed_by is None) != (self.reviewed_at is None):
            raise ValueError("reviewed_by and reviewed_at must be provided together")
        if self.status is MarketMetricBatchStatus.PENDING_REVIEW:
            if self.reviewed_by is not None or self.review_codes:
                raise ValueError("pending batch must not contain review metadata")
        elif self.reviewed_by is None:
            raise ValueError("reviewed batch must contain reviewer and review time")
        if self.status is MarketMetricBatchStatus.APPROVED and self.review_codes:
            raise ValueError("approved batch must not contain rejection codes")
        if self.status is MarketMetricBatchStatus.REJECTED and not self.review_codes:
            raise ValueError("rejected batch must contain rejection codes")
        return self


class MarketMetricBatchCandidate(FrozenMarketMetricModel):
    batch: MarketMetricBatch
    product_match: MarketMetricProductMatch


class MarketMetricBatchCandidateList(FrozenMarketMetricModel):
    items: list[MarketMetricBatchCandidate] = Field(default_factory=list)


class MarketMetricObservation(FrozenMarketMetricModel):
    id: NonEmptyStr = Field(default_factory=lambda: str(uuid4()))
    tenant_id: NonEmptyStr
    trace_id: NonEmptyStr
    created_at: datetime
    batch_id: NonEmptyStr
    metric_code: NonEmptyStr
    value_kind: MarketMetricValueKind
    value: FiniteDecimal | None = None
    unit: NonEmptyStr | None = None
    currency: CurrencyCode | None = None
    status: MetricStatus
    reason_code: NonEmptyStr | None = None
    methodology: NonEmptyStr
    source_timestamp: datetime
    growth_type: MarketMetricGrowthType | None = None
    comparison_period_start: datetime | None = None
    comparison_period_end: datetime | None = None
    formula_code: NonEmptyStr | None = None
    formula_version: NonEmptyStr | None = None
    source_observation_ids: list[NonEmptyStr] = Field(default_factory=list)
    calculated_at: datetime | None = None

    @field_validator("metric_code")
    @classmethod
    def normalize_metric_code(cls, value: str) -> str:
        return value.casefold()

    @model_validator(mode="after")
    def validate_observation(self) -> "MarketMetricObservation":
        if self.status is MetricStatus.UNAVAILABLE and self.value is not None:
            raise ValueError("unavailable metric must not provide value")
        if self.status is not MetricStatus.UNAVAILABLE and self.value is None:
            raise ValueError("usable metric must provide value")
        if self.currency is not None and self.unit is not None and self.unit.upper() != self.currency:
            raise ValueError("monetary metric unit must match currency")
        if self.value_kind is MarketMetricValueKind.DIRECT:
            if self.formula_code or self.formula_version or self.source_observation_ids or self.calculated_at:
                raise ValueError("direct metric must not contain derivation metadata")
        elif not all(
            (self.formula_code, self.formula_version, self.source_observation_ids, self.calculated_at)
        ):
            raise ValueError("derived metric must contain formula and source observations")
        if len(self.source_observation_ids) != len(set(self.source_observation_ids)):
            raise ValueError("source observation ids must be unique")
        if self.id in self.source_observation_ids:
            raise ValueError("metric must not derive from itself")
        _validate_optional_period(
            self.comparison_period_start,
            self.comparison_period_end,
            "comparison period",
        )
        return self


class MarketMetricRecord(FrozenMarketMetricModel):
    batch: MarketMetricBatch
    observation: MarketMetricObservation

    @model_validator(mode="after")
    def validate_ownership(self) -> "MarketMetricRecord":
        if self.observation.batch_id != self.batch.id:
            raise ValueError("observation batch_id must match batch id")
        if self.observation.tenant_id != self.batch.tenant_id:
            raise ValueError("observation tenant_id must match batch tenant_id")
        if self.observation.trace_id != self.batch.trace_id:
            raise ValueError("observation trace_id must match batch trace_id")
        return self


class MarketMetricUploadResult(FrozenMarketMetricModel):
    schema_version: Literal["1.0"] = "1.0"
    batch_id: NonEmptyStr
    status: MarketMetricBatchStatus
    direct_metric_count: int = Field(ge=0)
    derived_metric_count: int = Field(ge=0)
    created_at: datetime
    approval_codes: list[NonEmptyStr] = Field(default_factory=list)
    reviewed_by: NonEmptyStr | None = None


class MarketMetricApprovalOutcome(FrozenMarketMetricModel):
    decision: MarketMetricApprovalDecision
    batch: MarketMetricBatch
    codes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision(self) -> "MarketMetricApprovalOutcome":
        expected_status = MarketMetricBatchStatus(self.decision.value)
        if self.batch.status is not expected_status:
            raise ValueError("approval decision must match batch status")
        if self.decision is MarketMetricApprovalDecision.REJECTED and not self.codes:
            raise ValueError("rejected approval must provide reason codes")
        if self.decision is MarketMetricApprovalDecision.APPROVED and self.codes:
            raise ValueError("approved approval must not provide rejection codes")
        return self


class MarketMetricBatchList(FrozenMarketMetricModel):
    items: list[MarketMetricBatch] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class MarketMetricBatchDetail(FrozenMarketMetricModel):
    batch: MarketMetricBatch
    direct_observations: list[MarketMetricObservation] = Field(default_factory=list)
    derived_observations: list[MarketMetricObservation] = Field(default_factory=list)


def _validate_period(start: datetime, end: datetime, label: str) -> None:
    try:
        invalid = end < start
    except TypeError as exc:
        raise ValueError(f"{label} timestamps must use compatible timezones") from exc
    if invalid:
        raise ValueError(f"{label} end must not precede start")


def _validate_optional_period(
    start: datetime | None,
    end: datetime | None,
    label: str,
) -> None:
    if (start is None) != (end is None):
        raise ValueError(f"{label} start and end must be provided together")
    if start is not None and end is not None:
        _validate_period(start, end, label)


__all__ = [
    "DirectMarketMetricInput",
    "MarketMetricBatch",
    "MarketMetricBatchCreate",
    "MarketMetricBatchDetail",
    "MarketMetricBatchList",
    "MarketMetricBatchStatus",
    "MarketMetricApprovalDecision",
    "MarketMetricApprovalOutcome",
    "MarketMetricGrowthType",
    "MarketMetricObservation",
    "MarketMetricRecord",
    "MarketMetricSourceType",
    "MarketMetricStoredFile",
    "MarketMetricUploadContext",
    "MarketMetricUploadRequest",
    "MarketMetricUploadResult",
    "MarketMetricValueKind",
]
