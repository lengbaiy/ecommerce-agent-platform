from enum import StrEnum

from pydantic import ConfigDict
from typing_extensions import TypedDict

from app.modules.market_intelligence.schemas.adapter import EvidenceReference
from app.modules.market_intelligence.schemas.analysis import (
    CompetitorItem,
)
from app.modules.market_intelligence.schemas.common import (
    MarketIntelligenceModel,
    NonEmptyStr,
    NonNegativeInt,
)
from app.modules.market_intelligence.schemas.report import (
    DataLimitation,
    MarketIntelligenceReport,
    Statement,
)
from app.modules.market_intelligence.schemas.request import (
    MarketIntelligenceContext,
    MarketIntelligenceRequest,
)
from app.tools.support.contracts import ToolResponse


class GraphStep(StrEnum):
    VALIDATE_INPUT = "validate_input"
    SEARCH_PRODUCTS = "search_products"
    BUILD_COMPETITOR_MATRIX = "build_competitor_matrix"
    BUILD_MARKET_SNAPSHOT = "build_market_snapshot"
    ANALYZE_REVIEWS = "analyze_reviews"
    CALCULATE_PROFIT = "calculate_profit"
    SYNTHESIZE_REPORT = "synthesize_report"
    VALIDATE_EVIDENCE = "validate_evidence"
    PERSIST_RESULT = "persist_result"


class GraphError(MarketIntelligenceModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    step: GraphStep
    code: NonEmptyStr
    message: NonEmptyStr
    retryable: bool


class MarketIntelligenceState(TypedDict):
    """市场情报 Graph 的完整可检查点状态。"""

    # 可信上下文和业务输入。
    context: MarketIntelligenceContext
    request: MarketIntelligenceRequest

    # 当前 Graph 节点。
    current_step: GraphStep

    # 四个 Tool 的完整响应，保留错误、来源、追踪和降级信息。
    product_result: ToolResponse | None
    competitor_matrix: list[CompetitorItem]
    market_result: ToolResponse | None
    review_result: ToolResponse | None
    profit_result: ToolResponse | None

    # 报告综合过程中产生的结构化结论。
    facts: list[Statement]
    inferences: list[Statement]
    opportunity_signals: list[Statement]
    risk_signals: list[Statement]
    suggested_actions: list[Statement]

    # 证据与数据限制。
    evidence_refs: list[EvidenceReference]
    data_limitations: list[DataLimitation]

    # 执行控制、错误和降级状态。
    retry_count: NonNegativeInt
    retry_counts: dict[GraphStep, NonNegativeInt]
    degraded_flags: list[NonEmptyStr]
    error: GraphError | None

    # 最终输出与检查点版本。
    final_report: MarketIntelligenceReport | None
    state_version: NonNegativeInt


def build_initial_state(
    *,
    context: MarketIntelligenceContext,
    request: MarketIntelligenceRequest,
) -> MarketIntelligenceState:
    """创建字段完整、可直接交给 LangGraph 的初始状态。"""

    return MarketIntelligenceState(
        context=context,
        request=request,
        current_step=GraphStep.VALIDATE_INPUT,
        product_result=None,
        competitor_matrix=[],
        market_result=None,
        review_result=None,
        profit_result=None,
        facts=[],
        inferences=[],
        opportunity_signals=[],
        risk_signals=[],
        suggested_actions=[],
        evidence_refs=[],
        data_limitations=[],
        retry_count=0,
        retry_counts={step: 0 for step in GraphStep},
        degraded_flags=[],
        error=None,
        final_report=None,
        state_version=1,
    )
