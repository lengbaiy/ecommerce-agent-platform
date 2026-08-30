from statistics import fmean

from app.domain import AgentResult, EvidenceRef
from app.modules.market_intelligence.schemas.report import (
    MarketIntelligenceReport,
    MarketIntelligenceResultPayload,
)


def market_intelligence_report_to_agent_result(
    report: MarketIntelligenceReport,
) -> AgentResult:
    """把领域报告无损装入通用任务结果。"""

    statements = [
        *report.facts,
        *report.inferences,
        *report.opportunity_signals,
        *report.risk_signals,
        *report.suggested_actions,
    ]
    confidence = fmean(item.confidence for item in statements) if statements else 0.5
    payload = MarketIntelligenceResultPayload(
        market_intelligence_report=report,
    )
    return AgentResult(
        result_type="market_intelligence_report",
        summary=report.entry_assessment.summary,
        facts=[item.text for item in report.facts],
        inferences=[
            item.text
            for item in [
                *report.inferences,
                *report.opportunity_signals,
                *report.risk_signals,
            ]
        ],
        actions=[item.text for item in report.suggested_actions],
        evidence_refs=[
            EvidenceRef(
                id=item.evidence_id,
                grade=item.data_level.value,
                source=item.data_source,
                summary=item.snapshot_ref,
            )
            for item in report.evidence_refs
        ],
        confidence=confidence,
        payload=payload.model_dump(mode="json"),
    )


__all__ = ["market_intelligence_report_to_agent_result"]
