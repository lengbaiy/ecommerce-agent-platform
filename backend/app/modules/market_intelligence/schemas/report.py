from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.modules.market_intelligence.schemas.adapter import EvidenceReference
from app.modules.market_intelligence.schemas.analysis import (
    CompetitorItem,
    EntryAssessment,
    ProfitAnalysis,
    ReviewInsight,
)
from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    MarketIntelligenceModel,
    MetricStatus,
    NonEmptyStr,
)
from app.modules.market_intelligence.schemas.facts import MarketMetric


class ReportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class LimitationStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    STALE = "stale"
    CONFLICT = "conflict"


class Statement(MarketIntelligenceModel):
    """带置信度、证据和限制引用的报告结论。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    statement_id: NonEmptyStr
    text: NonEmptyStr
    confidence: float = Field(ge=0, le=1)
    critical: bool = False
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    affected_by_limitations: list[NonEmptyStr] = Field(default_factory=list)


class DataLimitation(MarketIntelligenceModel):
    """缺失、部分、过期或冲突数据对报告造成的影响。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    limitation_id: NonEmptyStr
    field: NonEmptyStr
    status: LimitationStatus
    reason_code: NonEmptyStr
    message: NonEmptyStr
    affected_conclusions: list[NonEmptyStr] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)


class MarketSnapshot(MarketIntelligenceModel):
    """市场指标及其统一样本范围。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    status: MetricStatus
    scope: AnalysisScope
    metrics: list[MarketMetric] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "MarketSnapshot":
        available_metrics = [
            metric
            for metric in self.metrics
            if metric.status is MetricStatus.AVAILABLE
        ]
        if self.status is MetricStatus.AVAILABLE and not available_metrics:
            raise ValueError(
                "available market snapshot must contain an available metric"
            )
        if self.status is MetricStatus.UNAVAILABLE and available_metrics:
            raise ValueError(
                "unavailable market snapshot must not contain available metrics"
            )
        return self


class MarketIntelligenceReport(MarketIntelligenceModel):
    """市场情报模块稳定、版本化且可追溯的最终输出。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["1.0"] = "1.0"
    report_id: NonEmptyStr
    task_id: NonEmptyStr
    status: ReportStatus
    scope: AnalysisScope
    market_snapshot: MarketSnapshot
    competitor_matrix: list[CompetitorItem] = Field(default_factory=list)
    review_insights: ReviewInsight
    profit_analysis: ProfitAnalysis
    entry_assessment: EntryAssessment
    facts: list[Statement] = Field(default_factory=list)
    inferences: list[Statement] = Field(default_factory=list)
    opportunity_signals: list[Statement] = Field(default_factory=list)
    risk_signals: list[Statement] = Field(default_factory=list)
    suggested_actions: list[Statement] = Field(default_factory=list)
    data_limitations: list[DataLimitation] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_references(self) -> "MarketIntelligenceReport":
        statements = [
            *self.facts,
            *self.inferences,
            *self.opportunity_signals,
            *self.risk_signals,
            *self.suggested_actions,
        ]
        statement_ids = [statement.statement_id for statement in statements]
        limitation_ids = [
            limitation.limitation_id for limitation in self.data_limitations
        ]
        evidence_ids = [
            evidence.evidence_id for evidence in self.evidence_refs
        ]

        self._require_unique(statement_ids, "statement_id")
        self._require_unique(limitation_ids, "limitation_id")
        self._require_unique(evidence_ids, "evidence_id")

        known_statements = set(statement_ids)
        known_limitations = set(limitation_ids)
        known_evidence = set(evidence_ids)

        evidence_required = [
            *self.facts,
            *self.inferences,
            *self.opportunity_signals,
            *self.risk_signals,
        ]
        for statement in evidence_required:
            if not statement.evidence_ids:
                raise ValueError(
                    f"statement {statement.statement_id} must provide evidence_ids"
                )

        for statement in statements:
            self._require_known_references(
                statement.evidence_ids,
                known_evidence,
                f"statement {statement.statement_id} evidence_ids",
            )
            self._require_known_references(
                statement.affected_by_limitations,
                known_limitations,
                f"statement {statement.statement_id} affected_by_limitations",
            )

        for limitation in self.data_limitations:
            self._require_known_references(
                limitation.evidence_ids,
                known_evidence,
                f"limitation {limitation.limitation_id} evidence_ids",
            )
            self._require_known_references(
                limitation.affected_conclusions,
                known_statements,
                f"limitation {limitation.limitation_id} affected_conclusions",
            )

        self._require_known_references(
            self.entry_assessment.evidence_ids,
            known_evidence,
            "entry_assessment evidence_ids",
        )
        self._require_known_references(
            self.entry_assessment.limitation_ids,
            known_limitations,
            "entry_assessment limitation_ids",
        )
        self._require_known_references(
            self.market_snapshot.evidence_ids,
            known_evidence,
            "market_snapshot evidence_ids",
        )

        if self.status is ReportStatus.DEGRADED and not self.data_limitations:
            raise ValueError("degraded report must provide at least one data limitation")
        return self

    @staticmethod
    def _require_unique(values: list[str], field_name: str) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} values must be unique")

    @staticmethod
    def _require_known_references(
        values: list[str],
        known_values: set[str],
        field_name: str,
    ) -> None:
        unknown = sorted(set(values) - known_values)
        if unknown:
            raise ValueError(f"{field_name} contain unknown references: {', '.join(unknown)}")


class MarketIntelligenceResultPayload(MarketIntelligenceModel):
    """完整报告在通用 AgentResult.payload 中的稳定位置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    market_intelligence_report: MarketIntelligenceReport
