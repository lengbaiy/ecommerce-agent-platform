from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event, Thread
from time import monotonic
from typing import Any, Protocol, cast
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from app.agents.market_intelligence_reporter import (
    LLMMarketIntelligenceReporter,
    ReportSynthesisError,
    ReportSynthesizer,
)
from app.modules.market_intelligence.schemas.adapter import (
    DataLevel,
    EvidenceReference,
    EvidenceType,
)
from app.modules.market_intelligence.schemas.analysis import (
    CompetitorItem,
    EntryAssessment,
    ProfitAnalysis,
    ReviewInsight,
)
from app.modules.market_intelligence.schemas.common import (
    AnalysisScope,
    EntryDecision,
    MetricStatus,
    ProfitStatus,
)
from app.modules.market_intelligence.schemas.facts import (
    MarketMetric,
    NormalizedProduct,
)
from app.modules.market_intelligence.schemas.report import (
    DataLimitation,
    LimitationStatus,
    MarketIntelligenceReport,
    MarketSnapshot,
    ReportStatus,
)
from app.modules.market_intelligence.state import (
    GraphError,
    GraphStep,
    MarketIntelligenceState,
)
from app.tools.market_data import MarketDataTool
from app.tools.product_search import ProductSearchTool
from app.tools.profit_calculator import ProfitCalculatorTool
from app.tools.review_insight import ReviewInsightTool
from app.tools.support.contracts import ToolError, ToolRequest, ToolResponse


logger = logging.getLogger(__name__)
METRIC_STATUS_LABELS = {
    MetricStatus.AVAILABLE: "可用",
    MetricStatus.UNAVAILABLE: "不可用",
    MetricStatus.PARTIAL: "部分可用",
    MetricStatus.STALE: "数据过期",
    MetricStatus.CONFLICT: "数据冲突",
}


class CancellationPort(Protocol):
    def is_cancelled(self, task_id: str) -> bool: ...

    def heartbeat(self, task_id: str) -> None: ...


class CheckpointPort(Protocol):
    def load(self, task_id: str) -> MarketIntelligenceState | None: ...

    def save(self, state: MarketIntelligenceState) -> None: ...


class ReportPersistencePort(Protocol):
    def save(
        self,
        report: MarketIntelligenceReport,
        state: MarketIntelligenceState,
    ) -> None: ...


class ToolExecutionPort(Protocol):
    def load(self, idempotency_key: str) -> ToolResponse | None: ...

    def start(self, request: ToolRequest, tool_name: str) -> None: ...

    def finish(self, request: ToolRequest, response: ToolResponse) -> None: ...

    def progress(
        self,
        request: ToolRequest,
        tool_name: str,
        summary: str,
    ) -> None: ...


class StepExecutionPort(Protocol):
    def start(self, state: MarketIntelligenceState, step: GraphStep) -> str | None: ...

    def finish(
        self,
        execution_id: str | None,
        state: MarketIntelligenceState,
    ) -> None: ...


class NoopCancellationPort:
    def is_cancelled(self, task_id: str) -> bool:
        return False

    def heartbeat(self, task_id: str) -> None:
        return None


class NoopCheckpointPort:
    def load(self, task_id: str) -> MarketIntelligenceState | None:
        return None

    def save(self, state: MarketIntelligenceState) -> None:
        return None


class NoopReportPersistencePort:
    def save(
        self,
        report: MarketIntelligenceReport,
        state: MarketIntelligenceState,
    ) -> None:
        return None


class NoopToolExecutionPort:
    def load(self, idempotency_key: str) -> ToolResponse | None:
        return None

    def start(self, request: ToolRequest, tool_name: str) -> None:
        return None

    def finish(self, request: ToolRequest, response: ToolResponse) -> None:
        return None

    def progress(
        self,
        request: ToolRequest,
        tool_name: str,
        summary: str,
    ) -> None:
        return None


class _PeriodicLeaseHeartbeat:
    """Renews a worker lease while a synchronous graph node is running."""

    def __init__(
        self,
        *,
        task_id: str,
        heartbeat: Callable[[str], None],
        interval_seconds: float,
    ) -> None:
        self.task_id = task_id
        self.heartbeat = heartbeat
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def __enter__(self) -> "_PeriodicLeaseHeartbeat":
        self._thread = Thread(
            target=self._run,
            name=f"lease-heartbeat-{self.task_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.heartbeat(self.task_id)
            except Exception:
                logger.exception(
                    "Task lease heartbeat failed task_id=%s",
                    self.task_id,
                )


class NoopStepExecutionPort:
    def start(self, state: MarketIntelligenceState, step: GraphStep) -> str | None:
        return None

    def finish(self, execution_id: str | None, state: MarketIntelligenceState) -> None:
        return None


class MarketIntelligenceGraph:
    """编排市场、商品、评论、利润和证据化报告。"""

    def __init__(
        self,
        *,
        product_search_tool: ProductSearchTool,
        market_data_tool: MarketDataTool,
        review_insight_tool: ReviewInsightTool,
        profit_calculator_tool: ProfitCalculatorTool,
        report_synthesizer: ReportSynthesizer,
        cancellation_port: CancellationPort | None = None,
        checkpoint_port: CheckpointPort | None = None,
        report_persistence_port: ReportPersistencePort | None = None,
        tool_execution_port: ToolExecutionPort | None = None,
        step_execution_port: StepExecutionPort | None = None,
        max_retries: int = 2,
        heartbeat_interval_seconds: float = 30,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        self.product_search_tool = product_search_tool
        self.market_data_tool = market_data_tool
        self.review_insight_tool = review_insight_tool
        self.profit_calculator_tool = profit_calculator_tool
        self.report_synthesizer = report_synthesizer
        self.cancellation_port = cancellation_port or NoopCancellationPort()
        self.checkpoint_port = checkpoint_port or NoopCheckpointPort()
        self.report_persistence_port = (
            report_persistence_port or NoopReportPersistencePort()
        )
        self.tool_execution_port = tool_execution_port or NoopToolExecutionPort()
        self.step_execution_port = step_execution_port or NoopStepExecutionPort()
        self.max_retries = max_retries
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.graph = self._build_graph()

    def run(self, state: MarketIntelligenceState) -> MarketIntelligenceState:
        load_checkpoint = getattr(self.checkpoint_port, "load", lambda _task_id: None)
        checkpoint = load_checkpoint(state["context"].task_id)
        if checkpoint is not None:
            if (
                checkpoint["context"] != state["context"]
                or checkpoint["request"] != state["request"]
            ):
                raise ValueError("Checkpoint input does not match the current task")
            if checkpoint["current_step"] is GraphStep.PERSIST_RESULT:
                return checkpoint
            state = checkpoint
        return cast(MarketIntelligenceState, self.graph.invoke(state))

    def _build_graph(self):
        workflow = StateGraph(MarketIntelligenceState)
        handlers: list[tuple[GraphStep, Callable]] = [
            (GraphStep.VALIDATE_INPUT, self._validate_input),
            (GraphStep.SEARCH_PRODUCTS, self._search_products),
            (GraphStep.BUILD_COMPETITOR_MATRIX, self._build_competitor_matrix),
            (GraphStep.BUILD_MARKET_SNAPSHOT, self._build_market_snapshot),
            (GraphStep.ANALYZE_REVIEWS, self._analyze_reviews),
            (GraphStep.CALCULATE_PROFIT, self._calculate_profit),
            (GraphStep.SYNTHESIZE_REPORT, self._synthesize_report),
            (GraphStep.VALIDATE_EVIDENCE, self._validate_evidence),
            (GraphStep.PERSIST_RESULT, self._persist_result),
        ]
        for step, handler in handlers:
            workflow.add_node(step.value, self._node(step, handler))
        workflow.add_conditional_edges(
            START,
            self._entry_route,
            {step.value: step.value for step, _ in handlers},
        )
        for index, (step, _) in enumerate(handlers):
            next_node = END if index == len(handlers) - 1 else handlers[index + 1][0].value
            workflow.add_conditional_edges(
                step.value,
                self._route,
                {"continue": next_node, "stop": END},
            )
        return workflow.compile()

    @staticmethod
    def _entry_route(state: MarketIntelligenceState) -> str:
        steps = list(GraphStep)
        if state["state_version"] <= 1:
            return GraphStep.VALIDATE_INPUT.value
        current = steps.index(state["current_step"])
        return steps[min(current + 1, len(steps) - 1)].value

    @staticmethod
    def _route(state: MarketIntelligenceState) -> str:
        return "stop" if state["error"] is not None else "continue"

    def _node(self, step: GraphStep, handler: Callable):
        def execute(state: MarketIntelligenceState) -> MarketIntelligenceState:
            execution_id = self.step_execution_port.start(state, step)
            try:
                heartbeat = getattr(self.cancellation_port, "heartbeat", lambda _task_id: None)
                heartbeat(state["context"].task_id)
                cancelled = self.cancellation_port.is_cancelled(
                    state["context"].task_id
                )
            except Exception:
                update: dict[str, Any] = {
                    "error": GraphError(
                        step=step,
                        code="CANCELLATION_CHECK_FAILED",
                        message="The task cancellation state could not be read.",
                        retryable=False,
                    )
                }
            else:
                if cancelled:
                    update = {
                        "error": GraphError(
                            step=step,
                            code="TASK_CANCELLED",
                            message="The market intelligence task was cancelled.",
                            retryable=False,
                        )
                    }
                else:
                    try:
                        with _PeriodicLeaseHeartbeat(
                            task_id=state["context"].task_id,
                            heartbeat=heartbeat,
                            interval_seconds=self.heartbeat_interval_seconds,
                        ):
                            update = handler(state)
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        update = {
                            "error": GraphError(
                                step=step,
                                code="SCHEMA_VALIDATION_FAILED",
                                message=str(exc),
                                retryable=False,
                            )
                        }
                    except Exception:
                        update = {
                            "error": GraphError(
                                step=step,
                                code="GRAPH_NODE_FAILED",
                                message=f"Graph node {step.value} failed unexpectedly.",
                                retryable=False,
                            )
                        }

            merged = cast(MarketIntelligenceState, {**state, **update, "current_step": step})
            if merged["error"] is None:
                merged["state_version"] = state["state_version"] + 1
                try:
                    self.checkpoint_port.save(merged)
                except Exception:
                    merged["error"] = GraphError(
                        step=step,
                        code="CHECKPOINT_FAILED",
                        message="The graph checkpoint could not be saved.",
                        retryable=False,
                    )
            self.step_execution_port.finish(execution_id, merged)
            return merged

        return execute

    @staticmethod
    def _validate_input(state: MarketIntelligenceState) -> dict[str, Any]:
        request = state["request"]
        context = state["context"]
        if request.schema_version != "1.0" or context.schema_version != "1.0":
            raise ValueError("Unsupported market intelligence schema version")
        if len(request.platforms) != 1:
            raise ValueError("Exactly one platform is required")
        return {"error": None}

    def _search_products(self, state: MarketIntelligenceState) -> dict[str, Any]:
        request = state["request"]
        response, control, error = self._call_tool(
            state,
            GraphStep.SEARCH_PRODUCTS,
            self.product_search_tool,
            {
                "schema_version": request.schema_version,
                "task_id": state["context"].task_id,
                "platform": request.platforms[0],
                "market": request.market,
                "category": request.category,
                "keyword": request.keyword,
                "product_limit": request.collection.product_limit,
                "sort_by": request.collection.sort_by.value,
                "data_source_mode": request.data_source_mode.value,
            },
        )
        update = {"product_result": response, **control, "error": error}
        if error is not None:
            return update

        products = self._models(response, "products", NormalizedProduct)
        evidence = self._models(response, "evidence_refs", EvidenceReference)
        if not products:
            update["error"] = GraphError(
                step=GraphStep.SEARCH_PRODUCTS,
                code="DATA_EMPTY",
                message="Product search returned no products.",
                retryable=False,
            )
            return update

        limitations = list(state["data_limitations"])
        flags = list(state["degraded_flags"])
        if response.degraded:
            limitations = self._merge_limitations(
                limitations,
                [
                    self._limitation(
                        "products-partial",
                        "competitor_matrix",
                        LimitationStatus.PARTIAL,
                        "PRODUCT_COLLECTION_PARTIAL",
                        "仅采集到部分请求的商品样本。",
                        [item.evidence_id for item in evidence],
                    )
                ],
            )
            flags = self._merge_strings(flags, ["PRODUCT_COLLECTION_PARTIAL"])
        update.update(
            evidence_refs=self._merge_evidence(state["evidence_refs"], evidence),
            data_limitations=limitations,
            degraded_flags=flags,
        )
        return update

    def _build_competitor_matrix(
        self,
        state: MarketIntelligenceState,
    ) -> dict[str, Any]:
        products = self._models(state["product_result"], "products", NormalizedProduct)
        evidence_by_product: dict[tuple[str, str], list[str]] = {}
        for evidence in state["evidence_refs"]:
            if evidence.product_id:
                evidence_by_product.setdefault(
                    (evidence.platform.casefold(), evidence.product_id), []
                ).append(evidence.evidence_id)
        matrix = [
            CompetitorItem(
                rank=rank,
                platform=item.platform,
                market=item.market,
                product_id=item.product_id,
                title=item.title,
                brand=item.brand,
                price=item.price,
                currency=item.currency,
                sales_display=item.sales_display,
                sales_value=item.sales_value,
                sales_value_type=item.sales_value_type,
                rating=item.rating,
                review_count=item.review_count,
                shop_name=item.shop_name,
                source_ref=item.source_ref,
                evidence_ids=evidence_by_product.get(
                    (item.platform.casefold(), item.product_id), []
                ),
            )
            for rank, item in enumerate(products, start=1)
        ]
        return {"competitor_matrix": matrix, "error": None}

    def _build_market_snapshot(
        self,
        state: MarketIntelligenceState,
    ) -> dict[str, Any]:
        request = state["request"]
        products = self._models(state["product_result"], "products", NormalizedProduct)
        response, control, error = self._call_tool(
            state,
            GraphStep.BUILD_MARKET_SNAPSHOT,
            self.market_data_tool,
            {
                "schema_version": request.schema_version,
                "task_id": state["context"].task_id,
                "platform": request.platforms[0],
                "market": request.market,
                "category": request.category,
                "keyword": request.keyword,
                "market_metric_batch_id": request.market_metric_batch_id,
                "market_metric_product_match": (
                    request.market_metric_product_match.model_dump(mode="json")
                    if request.market_metric_product_match
                    else None
                ),
                "data_source_mode": request.data_source_mode.value,
                "products": [item.model_dump(mode="json") for item in products],
                "evidence_refs": [
                    item.model_dump(mode="json") for item in state["evidence_refs"]
                ],
            },
        )
        limitations = list(state["data_limitations"])
        flags = list(state["degraded_flags"])
        evidence: list[EvidenceReference] = []
        if error is not None:
            limitations = self._merge_limitations(
                limitations,
                [self._unavailable("market-data", "market_snapshot", error.code, error.message)],
            )
            flags = self._merge_strings(flags, [error.code])
            error = None
        else:
            metrics = self._models(response, "metrics", MarketMetric)
            evidence = self._models(response, "evidence_refs", EvidenceReference)
            response_warnings = [str(item) for item in response.data.get("warnings", [])]
            if any(
                item.startswith("SELECTED_MARKET_METRIC_BATCH_INVALID:")
                for item in response_warnings
            ):
                limitations = self._merge_limitations(
                    limitations,
                    [
                        self._unavailable(
                            "selected-market-metric-batch",
                            "market_snapshot",
                            "SELECTED_MARKET_METRIC_BATCH_INVALID",
                            "所选宏观市场数据批次已失效或不再适用于当前平台和市场。",
                        )
                    ],
                )
                flags = self._merge_strings(
                    flags,
                    ["SELECTED_MARKET_METRIC_BATCH_INVALID"],
                )
            missing = [metric for metric in metrics if metric.status is not MetricStatus.AVAILABLE]
            limitations = self._merge_limitations(
                limitations,
                [
                    self._limitation(
                        f"market-{metric.metric_code}",
                        f"market_snapshot.{metric.metric_code}",
                        LimitationStatus(metric.status.value),
                        metric.reason_code or "MARKET_METRIC_INCOMPLETE",
                        f"市场指标 {metric.metric_code} 当前状态为"
                        f"{METRIC_STATUS_LABELS[metric.status]}。",
                        metric.evidence_ids,
                    )
                    for metric in missing
                ],
            )
            if response.degraded or missing:
                flags = self._merge_strings(flags, ["MARKET_DATA_INCOMPLETE"])
        return {
            "market_result": response,
            "evidence_refs": self._merge_evidence(state["evidence_refs"], evidence),
            "data_limitations": limitations,
            "degraded_flags": flags,
            **control,
            "error": error,
        }

    def _analyze_reviews(self, state: MarketIntelligenceState) -> dict[str, Any]:
        request = state["request"]
        products = self._models(state["product_result"], "products", NormalizedProduct)
        review_limit = request.collection.review_limit_per_product or getattr(
            self.review_insight_tool, "max_reviews_per_product", 50
        )
        response, control, error = self._call_tool(
            state,
            GraphStep.ANALYZE_REVIEWS,
            self.review_insight_tool,
            {
                "schema_version": request.schema_version,
                "task_id": state["context"].task_id,
                "platform": request.platforms[0],
                "market": request.market,
                "category": request.category,
                "keyword": request.keyword,
                "product_ids": [item.product_id for item in products],
                "review_limit_per_product": review_limit,
                "data_source_mode": request.data_source_mode.value,
            },
        )
        limitations = list(state["data_limitations"])
        flags = list(state["degraded_flags"])
        evidence: list[EvidenceReference] = []
        if error is not None:
            limitations = self._merge_limitations(
                limitations,
                [self._unavailable("reviews", "review_insights", error.code, error.message)],
            )
            flags = self._merge_strings(flags, [error.code])
            error = None
        else:
            insight = ReviewInsight.model_validate(response.data["review_insight"])
            evidence = self._models(response, "evidence_refs", EvidenceReference)
            if insight.status is not MetricStatus.AVAILABLE:
                limitations = self._merge_limitations(
                    limitations,
                    [
                        self._limitation(
                            "reviews-incomplete",
                            "review_insights",
                            LimitationStatus(insight.status.value),
                            "REVIEW_DATA_INCOMPLETE",
                            f"评论洞察当前状态为{METRIC_STATUS_LABELS[insight.status]}。",
                            insight.evidence_ids,
                        )
                    ],
                )
                flags = self._merge_strings(flags, ["REVIEW_DATA_INCOMPLETE"])
        return {
            "review_result": response,
            "evidence_refs": self._merge_evidence(state["evidence_refs"], evidence),
            "data_limitations": limitations,
            "degraded_flags": flags,
            **control,
            "error": error,
        }

    def _calculate_profit(self, state: MarketIntelligenceState) -> dict[str, Any]:
        parameters = state["request"].profit_constraints
        if parameters is None:
            analysis = self._unavailable_profit()
            response = ToolResponse(
                success=True,
                data={"schema_version": "1.0", "profit_analysis": analysis.model_dump(mode="json")},
                source=self.profit_calculator_tool.name,
                trace_id=state["context"].trace_id,
                degraded=False,
            )
            return {
                "profit_result": response,
                "error": None,
            }

        response, control, error = self._call_tool(
            state,
            GraphStep.CALCULATE_PROFIT,
            self.profit_calculator_tool,
            parameters.model_dump(mode="json"),
        )
        if error is not None:
            limitation = self._unavailable(
                "profit-calculation",
                "profit_analysis",
                error.code,
                error.message,
            )
            return {
                "profit_result": response,
                "data_limitations": self._merge_limitations(
                    state["data_limitations"], [limitation]
                ),
                "degraded_flags": self._merge_strings(
                    state["degraded_flags"], [error.code]
                ),
                **control,
                "error": None,
            }

        analysis = ProfitAnalysis.model_validate(response.data["profit_analysis"])
        evidence = self._profit_evidence(state, parameters.model_dump(mode="json"), analysis)
        analysis = analysis.model_copy(update={"evidence_ids": [evidence.evidence_id]})
        response = response.model_copy(
            update={
                "data": {
                    **response.data,
                    "profit_analysis": analysis.model_dump(mode="json"),
                }
            }
        )
        return {
            "profit_result": response,
            "evidence_refs": self._merge_evidence(state["evidence_refs"], [evidence]),
            **control,
            "error": None,
        }

    def _synthesize_report(self, state: MarketIntelligenceState) -> dict[str, Any]:
        limitations = list(state["data_limitations"])
        flags = list(state["degraded_flags"])
        retries = 0
        while True:
            started_at = monotonic()
            try:
                synthesis = self.report_synthesizer.synthesize(state)
                break
            except ReportSynthesisError as exc:
                elapsed_ms = (monotonic() - started_at) * 1000
                will_retry = exc.retryable and retries < self.max_retries
                logger.warning(
                    "Report synthesis failed task_id=%s trace_id=%s "
                    "error_code=%s provider=%s retryable=%s attempt=%s "
                    "max_attempts=%s elapsed_ms=%.2f will_retry=%s message=%s",
                    state["context"].task_id,
                    state["context"].trace_id,
                    exc.code,
                    exc.provider or "unknown",
                    exc.retryable,
                    retries + 1,
                    self.max_retries + 1,
                    elapsed_ms,
                    will_retry,
                    str(exc),
                )
                if will_retry:
                    retries += 1
                    continue
                logger.warning(
                    "Report synthesis degraded task_id=%s trace_id=%s "
                    "error_code=%s attempts=%s",
                    state["context"].task_id,
                    state["context"].trace_id,
                    exc.code,
                    retries + 1,
                )
                limitation = self._unavailable(
                    "report-synthesis",
                    "entry_assessment",
                    "LLM_UNAVAILABLE",
                    "报告合成服务当前不可用，已保留现有结构化分析结果。",
                )
                limitations = self._merge_limitations(limitations, [limitation])
                flags = self._merge_strings(flags, ["LLM_UNAVAILABLE"])
                synthesis = LLMMarketIntelligenceReporter.degraded(
                    limitation_id=limitation.limitation_id
                )
                break

        retry_counts = dict(state["retry_counts"])
        retry_counts[GraphStep.SYNTHESIZE_REPORT] += retries
        report = MarketIntelligenceReport(
            report_id=str(uuid4()),
            task_id=state["context"].task_id,
            status=ReportStatus.DEGRADED if limitations or flags else ReportStatus.COMPLETED,
            scope=self._scope(state),
            market_snapshot=self._market_snapshot(state),
            competitor_matrix=state["competitor_matrix"],
            review_insights=self._review_insight(state),
            profit_analysis=self._profit_analysis(state),
            entry_assessment=synthesis.entry_assessment,
            facts=synthesis.facts,
            inferences=synthesis.inferences,
            opportunity_signals=synthesis.opportunity_signals,
            risk_signals=synthesis.risk_signals,
            suggested_actions=synthesis.suggested_actions,
            data_limitations=limitations,
            evidence_refs=state["evidence_refs"],
        )
        return {
            "facts": synthesis.facts,
            "inferences": synthesis.inferences,
            "opportunity_signals": synthesis.opportunity_signals,
            "risk_signals": synthesis.risk_signals,
            "suggested_actions": synthesis.suggested_actions,
            "data_limitations": limitations,
            "degraded_flags": flags,
            "retry_count": state["retry_count"] + retries,
            "retry_counts": retry_counts,
            "final_report": report,
            "error": None,
        }

    def _validate_evidence(self, state: MarketIntelligenceState) -> dict[str, Any]:
        report = state["final_report"]
        if report is None:
            raise ValueError("Final report is required before evidence validation")
        known = {item.evidence_id for item in report.evidence_refs}
        nested = {
            evidence_id
            for item in report.competitor_matrix
            for evidence_id in item.evidence_ids
        }
        nested |= set(report.market_snapshot.evidence_ids)
        nested |= set(report.review_insights.evidence_ids)
        nested |= set(report.profit_analysis.evidence_ids)
        if nested - known:
            raise ValueError("Report contains unknown nested evidence references")

        critical_codes = {
            "COST_INPUT_UNAVAILABLE",
            "DATA_CONFLICT",
            "LLM_UNAVAILABLE",
        }
        critical = [
            item
            for item in report.data_limitations
            if item.reason_code in critical_codes
            or item.status is LimitationStatus.CONFLICT
        ]
        if critical and report.entry_assessment.decision is not EntryDecision.INSUFFICIENT_DATA:
            assessment = EntryAssessment(
                decision=EntryDecision.INSUFFICIENT_DATA,
                summary="关键数据存在限制，当前无法形成可靠的市场进入判断。",
                evidence_ids=report.entry_assessment.evidence_ids,
                limitation_ids=[item.limitation_id for item in critical],
            )
            report = MarketIntelligenceReport.model_validate(
                {
                    **report.model_dump(mode="json"),
                    "entry_assessment": assessment.model_dump(mode="json"),
                }
            )
        return {"final_report": report, "error": None}

    def _persist_result(self, state: MarketIntelligenceState) -> dict[str, Any]:
        report = state["final_report"]
        if report is None:
            raise ValueError("Final report is required before persistence")
        self.report_persistence_port.save(report, state)
        return {"error": None}

    def _call_tool(
        self,
        state: MarketIntelligenceState,
        step: GraphStep,
        tool: Any,
        parameters: dict[str, Any],
    ) -> tuple[ToolResponse, dict[str, Any], GraphError | None]:
        retries = 0
        idempotency_key = hashlib.sha256(
            json.dumps(
                {
                    "task_id": state["context"].task_id,
                    "step": step.value,
                    "parameters": parameters,
                },
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        cached = self.tool_execution_port.load(idempotency_key)
        if cached is not None:
            return cached, {}, None
        request = ToolRequest(
            tenant_id=state["context"].tenant_id,
            user_id=state["context"].user_id,
            trace_id=state["context"].trace_id,
            task_id=state["context"].task_id,
            step_name=step.value,
            idempotency_key=idempotency_key,
            parameters=parameters,
        )
        while True:
            request = request.model_copy(update={"attempt": retries + 1})
            self.tool_execution_port.start(
                request, getattr(tool, "name", step.value)
            )
            try:
                response = tool.execute(request)
            except Exception:
                logger.exception(
                    "Tool execution escaped its boundary tool=%s task_id=%s "
                    "trace_id=%s step=%s",
                    getattr(tool, "name", step.value),
                    state["context"].task_id,
                    state["context"].trace_id,
                    step.value,
                )
                response = ToolResponse(
                    success=False,
                    error=ToolError(
                        code="TOOL_EXECUTION_FAILED",
                        message=f"{getattr(tool, 'name', step.value)} failed unexpectedly.",
                        retryable=False,
                    ),
                    source=getattr(tool, "name", step.value),
                    trace_id=request.trace_id,
                )
            self.tool_execution_port.finish(request, response)
            if response.success:
                error = None
                break
            tool_error = response.error
            if tool_error and tool_error.retryable and retries < self.max_retries:
                retries += 1
                continue
            error = GraphError(
                step=step,
                code=tool_error.code if tool_error else "TOOL_EXECUTION_FAILED",
                message=tool_error.message if tool_error else "Tool execution failed.",
                retryable=tool_error.retryable if tool_error else False,
            )
            break
        retry_counts = dict(state["retry_counts"])
        retry_counts[step] += retries
        return response, {
            "retry_count": state["retry_count"] + retries,
            "retry_counts": retry_counts,
        }, error

    @staticmethod
    def _models(response: ToolResponse | None, key: str, model: type):
        if response is None or not response.success:
            return []
        return [model.model_validate(item) for item in response.data.get(key, [])]

    def _scope(self, state: MarketIntelligenceState) -> AnalysisScope:
        products = self._models(state["product_result"], "products", NormalizedProduct)
        review_result = state["review_result"]
        reviews = (
            review_result.data.get("reviews", [])
            if review_result and review_result.success
            else []
        )
        timestamps = [item.source_timestamp for item in state["evidence_refs"]]
        request = state["request"]
        return AnalysisScope(
            market=request.market,
            platforms=request.platforms,
            category=request.category,
            keyword=request.keyword,
            start_time=min(timestamps) if timestamps else None,
            end_time=max(timestamps) if timestamps else None,
            requested_product_count=request.collection.product_limit,
            actual_product_count=len(products),
            actual_review_count=len(reviews),
            data_source_mode=request.data_source_mode,
        )

    def _market_snapshot(self, state: MarketIntelligenceState) -> MarketSnapshot:
        metrics = self._models(state["market_result"], "metrics", MarketMetric)
        available = [item for item in metrics if item.status is MetricStatus.AVAILABLE]
        status = (
            MetricStatus.UNAVAILABLE
            if not available
            else MetricStatus.AVAILABLE
            if len(available) == len(metrics)
            else MetricStatus.PARTIAL
        )
        return MarketSnapshot(
            status=status,
            scope=self._scope(state),
            metrics=metrics,
            evidence_ids=self._merge_strings(
                [], [e for item in metrics for e in item.evidence_ids]
            ),
        )

    def _review_insight(self, state: MarketIntelligenceState) -> ReviewInsight:
        response = state["review_result"]
        if response and response.success and response.data.get("review_insight"):
            return ReviewInsight.model_validate(response.data["review_insight"])
        return ReviewInsight(status=MetricStatus.UNAVAILABLE, sample_scope=self._scope(state))

    def _profit_analysis(self, state: MarketIntelligenceState) -> ProfitAnalysis:
        response = state["profit_result"]
        if response and response.success and response.data.get("profit_analysis"):
            return ProfitAnalysis.model_validate(response.data["profit_analysis"])
        return self._unavailable_profit()

    def _profit_evidence(
        self,
        state: MarketIntelligenceState,
        parameters: dict[str, Any],
        analysis: ProfitAnalysis,
    ) -> EvidenceReference:
        encoded = json.dumps(parameters, sort_keys=True, default=str).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        now = datetime.now(UTC)
        run_id = (
            state["product_result"].data.get("collection_run_id")
            if state["product_result"]
            else state["context"].task_id
        ) or state["context"].task_id
        return EvidenceReference(
            evidence_id=f"profit-{digest[:24]}",
            evidence_type=EvidenceType.PROFIT_INPUT,
            data_level=DataLevel.A,
            data_source=self.profit_calculator_tool.name,
            platform=state["request"].platforms[0],
            query_range={"fields": sorted(parameters), "currency": parameters.get("currency")},
            source_timestamp=now,
            ingest_timestamp=now,
            tool_call_id=str(uuid4()),
            collection_run_id=str(run_id),
            snapshot_ref=f"profit-input:{digest}",
            sha256=digest,
            data_version=analysis.calculation_version,
            sample_scope=self._scope(state),
        )

    @staticmethod
    def _unavailable_profit() -> ProfitAnalysis:
        return ProfitAnalysis(
            status=ProfitStatus.UNAVAILABLE,
            calculation_version="profit-v1",
        )

    @staticmethod
    def _limitation(
        suffix: str,
        field: str,
        status: LimitationStatus,
        reason_code: str,
        message: str,
        evidence_ids: list[str] | None = None,
    ) -> DataLimitation:
        return DataLimitation(
            limitation_id=f"lim-{suffix}",
            field=field,
            status=status,
            reason_code=reason_code,
            message=message,
            evidence_ids=evidence_ids or [],
        )

    @classmethod
    def _unavailable(
        cls,
        suffix: str,
        field: str,
        reason_code: str,
        message: str,
    ) -> DataLimitation:
        return cls._limitation(
            suffix,
            field,
            LimitationStatus.UNAVAILABLE,
            reason_code,
            message,
        )

    @staticmethod
    def _merge_strings(current: list[str], added: list[str]) -> list[str]:
        return list(dict.fromkeys([*current, *added]))

    @staticmethod
    def _merge_evidence(
        current: list[EvidenceReference],
        added: list[EvidenceReference],
    ) -> list[EvidenceReference]:
        return list({item.evidence_id: item for item in [*current, *added]}.values())

    @staticmethod
    def _merge_limitations(
        current: list[DataLimitation],
        added: list[DataLimitation],
    ) -> list[DataLimitation]:
        return list({item.limitation_id: item for item in [*current, *added]}.values())
