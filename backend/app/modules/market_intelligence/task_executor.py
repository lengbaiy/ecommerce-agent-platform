from pydantic import ValidationError

from app.domain import AgentTask, TaskError, TaskStatus
from app.modules.market_intelligence.result_mapper import (
    market_intelligence_report_to_agent_result,
)
from app.modules.market_intelligence.schemas import (
    MarketIntelligenceBusinessContext,
    MarketIntelligenceContext,
    ReportStatus,
)
from app.modules.task_center import AgentExecutionOutcome, TaskArtifact
from app.services.market_intelligence_service import (
    MarketIntelligenceExecutionError,
    MarketIntelligenceService,
)


class MarketIntelligenceTaskExecutor:
    """连接通用任务系统与市场情报 Service。"""

    def __init__(self, service: MarketIntelligenceService) -> None:
        self.service = service

    def execute(self, task: AgentTask) -> AgentExecutionOutcome:
        if task.request.tenant_id is None or task.request.user_id is None:
            return self._failed(
                task,
                code="TASK_IDENTITY_MISSING",
                message="Market intelligence task is missing trusted identity.",
            )
        try:
            business_context = MarketIntelligenceBusinessContext.model_validate(
                task.request.business_context
            )
            context = MarketIntelligenceContext(
                task_id=str(task.id),
                tenant_id=task.request.tenant_id,
                user_id=task.request.user_id,
                trace_id=task.trace_id,
                user_query=task.request.user_query,
                constraints=task.request.constraints,
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            return self._failed(
                task,
                code="MARKET_INPUT_INVALID",
                message=str(first.get("msg", "Market task input is invalid.")),
                details={
                    "field": ".".join(str(item) for item in first.get("loc", ()))
                },
            )

        try:
            execution = self.service.execute_with_metadata(
                business_context.market_intelligence_request,
                context,
            )
        except MarketIntelligenceExecutionError as exc:
            error = TaskError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                step=exc.step.value,
            )
            return AgentExecutionOutcome(
                status=(
                    TaskStatus.CANCELLED if exc.cancelled else TaskStatus.FAILED
                ),
                error=error,
                retry_count=max(task.retry_count, exc.retry_count),
            )

        report = execution.report
        result = market_intelligence_report_to_agent_result(report)
        if report.status is ReportStatus.FAILED:
            return AgentExecutionOutcome(
                status=TaskStatus.FAILED,
                result=result,
                error=TaskError(
                    code="MARKET_REPORT_FAILED",
                    message="Market intelligence report completed with FAILED status.",
                    step="synthesize_report",
                ),
                retry_count=max(task.retry_count, execution.retry_count),
            )
        return AgentExecutionOutcome(
            status=(
                TaskStatus.DEGRADED
                if report.status is ReportStatus.DEGRADED
                else TaskStatus.COMPLETED
            ),
            result=result,
            retry_count=max(task.retry_count, execution.retry_count),
            artifacts=(
                TaskArtifact(
                    artifact_type="market_intelligence_report",
                    artifact_id=report.report_id,
                    schema_version=report.schema_version,
                    status=report.status.value,
                    payload=report.model_dump(mode="json"),
                ),
            ),
        )

    @staticmethod
    def _failed(
        task: AgentTask,
        *,
        code: str,
        message: str,
        details: dict | None = None,
    ) -> AgentExecutionOutcome:
        return AgentExecutionOutcome(
            status=TaskStatus.FAILED,
            error=TaskError(
                code=code,
                message=message,
                step="validate_input",
                details=details or {},
            ),
            retry_count=task.retry_count,
        )


__all__ = ["MarketIntelligenceTaskExecutor"]
