from decimal import Decimal

from pydantic import Field, model_validator

from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    CurrencyCode,
    EntryDecision,
    Margin,
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
    NonNegativeDecimal,
    NonNegativeInt,
    PositiveDecimal,
    ProfitStatus,
    Ratio,
    SalesValueType,
)


class CompetitorItem(MarketIntelligenceModel):
    rank: int = Field(ge=1)
    platform: NonEmptyStr
    market: NonEmptyStr
    product_id: NonEmptyStr
    title: NonEmptyStr
    brand: NonEmptyStr | None = None
    price: NonNegativeDecimal
    currency: CurrencyCode
    sales_display: NonEmptyStr | None = None
    sales_value: NonNegativeInt | None = None
    sales_value_type: SalesValueType = SalesValueType.UNKNOWN
    rating: NonNegativeDecimal | None = None
    review_count: NonNegativeInt | None = None
    shop_name: NonEmptyStr | None = None
    source_ref: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sales_value(self) -> "CompetitorItem":
        if self.sales_value_type is not SalesValueType.UNKNOWN and self.sales_value is None:
            raise ValueError("sales_value is required when sales_value_type is known")
        return self


# class ProfitInput(MarketIntelligenceModel):
#     selling_price: PositiveDecimal
#     product_cost: NonNegativeDecimal
#     platform_fee: NonNegativeDecimal
#     logistics_cost: NonNegativeDecimal
#     advertising_cost: NonNegativeDecimal
#     other_cost: NonNegativeDecimal = Decimal("0")
#     currency: CurrencyCode
#     minimum_margin: Ratio


class ProfitAnalysis(MarketIntelligenceModel):
    status: ProfitStatus
    selling_price: PositiveDecimal | None = None
    total_cost: NonNegativeDecimal | None = None
    profit: Decimal | None = None
    margin: Margin | None = None
    minimum_margin: Ratio | None = None
    meets_minimum_margin: bool | None = None
    breakdown: dict[NonEmptyStr, Decimal] = Field(default_factory=dict)
    currency: CurrencyCode | None = None
    calculation_version: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_result(self) -> "ProfitAnalysis":
        if self.status is ProfitStatus.UNAVAILABLE:
            return self
        required = {
            "selling_price": self.selling_price,
            "total_cost": self.total_cost,
            "profit": self.profit,
            "margin": self.margin,
            "minimum_margin": self.minimum_margin,
            "meets_minimum_margin": self.meets_minimum_margin,
            "currency": self.currency,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"available profit analysis is missing: {', '.join(missing)}")
        if not self.breakdown:
            raise ValueError("available profit analysis must provide breakdown")
        return self


class ReviewTheme(MarketIntelligenceModel):
    theme: NonEmptyStr
    mention_count: NonNegativeInt
    mention_ratio: Ratio
    summary: NonEmptyStr
    representative_review_ids: list[NonEmptyStr] = Field(min_length=1)
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)


class ReviewInsight(MarketIntelligenceModel):
    status: MetricStatus
    sample_scope: AnalysisScope
    sentiment_distribution: dict[NonEmptyStr, Decimal | int] = Field(default_factory=dict)
    themes: list[ReviewTheme] = Field(default_factory=list)
    pain_points: list[ReviewTheme] = Field(default_factory=list)
    unmet_needs: list[ReviewTheme] = Field(default_factory=list)
    representative_review_ids: list[NonEmptyStr] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available_result(self) -> "ReviewInsight":
        if self.status is MetricStatus.AVAILABLE and not self.evidence_ids:
            raise ValueError("available review insight must provide evidence_ids")
        return self


class EntryAssessment(MarketIntelligenceModel):
    decision: EntryDecision
    summary: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    limitation_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_support(self) -> "EntryAssessment":
        if self.decision is EntryDecision.INSUFFICIENT_DATA:
            if not self.limitation_ids:
                raise ValueError("INSUFFICIENT_DATA assessment must provide limitation_ids")
        elif not self.evidence_ids:
            raise ValueError(f"{self.decision.value} assessment must provide evidence_ids")
        return self
