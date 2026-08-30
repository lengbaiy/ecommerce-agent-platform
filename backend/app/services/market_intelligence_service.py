from dataclasses import dataclass

from app.graph.market_intelligence_graph import MarketIntelligenceGraph
from app.modules.market_intelligence.schemas.report import MarketIntelligenceReport
from app.modules.market_intelligence.schemas.request import (
    MarketIntelligenceContext,
    MarketIntelligenceRequest,
)
from app.modules.market_intelligence.state import GraphError, build_initial_state


@dataclass(frozen=True)
class MarketIntelligenceExecution:
    report: MarketIntelligenceReport
    retry_count: int


class MarketIntelligenceExecutionError(RuntimeError):
    """Expose structured Graph failure details to API and task layers."""

    def __init__(self, error: GraphError, retry_count: int = 0) -> None:
        super().__init__(error.message)
        self.error = error
        self.code = error.code
        self.step = error.step
        self.retryable = error.retryable
        self.retry_count = retry_count

    @property
    def cancelled(self) -> bool:
        return self.code == "TASK_CANCELLED"


class MarketIntelligenceService:
    """Application entry point for one market intelligence execution."""

    def __init__(self, graph: MarketIntelligenceGraph) -> None:
        self.graph = graph

    def execute(
        self,
        request: MarketIntelligenceRequest,
        context: MarketIntelligenceContext,
    ) -> MarketIntelligenceReport:
        return self.execute_with_metadata(request, context).report

    def execute_with_metadata(
        self,
        request: MarketIntelligenceRequest,
        context: MarketIntelligenceContext,
    ) -> MarketIntelligenceExecution:
        # Revalidate the public boundary before creating mutable Graph state.
        request = MarketIntelligenceRequest.model_validate(request)
        context = MarketIntelligenceContext.model_validate(context)
        result = self.graph.run(
            build_initial_state(context=context, request=request)
        )

        if error := result["error"]:
            raise MarketIntelligenceExecutionError(error, result["retry_count"])

        report = result["final_report"]
        if report is None:
            raise RuntimeError("Market intelligence graph completed without a report")
        if report.task_id != context.task_id:
            raise RuntimeError("Market intelligence report task_id does not match context")
        return MarketIntelligenceExecution(
            report=report,
            retry_count=result["retry_count"],
        )
