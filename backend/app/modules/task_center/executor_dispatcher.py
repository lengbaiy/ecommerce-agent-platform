from dataclasses import dataclass
from typing import Any, Protocol

from app.domain import AgentResult, AgentTask, ApprovalStatus, TaskError, TaskStatus


@dataclass(frozen=True)
class TaskArtifact:
    artifact_type: str
    artifact_id: str
    schema_version: str
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class AgentExecutionOutcome:
    status: TaskStatus
    result: AgentResult | None = None
    error: TaskError | None = None
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    retry_count: int = 0
    artifacts: tuple[TaskArtifact, ...] = ()

    def __post_init__(self) -> None:
        allowed = {
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.DEGRADED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
        if self.status not in allowed:
            raise ValueError(f"executor returned non-terminal status: {self.status}")
        if self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.DEGRADED,
            TaskStatus.WAITING_APPROVAL,
        } and self.result is None:
            raise ValueError(f"{self.status} outcome must contain a result")
        if self.status is TaskStatus.FAILED and self.error is None:
            raise ValueError("FAILED outcome must contain an error")


class TaskExecutor(Protocol):
    def execute(self, task: AgentTask) -> AgentExecutionOutcome: ...


class TaskExecutorNotFoundError(ValueError):
    pass


class TaskExecutorDispatcher:
    """按任务 intent 路由到模块执行器。"""

    def __init__(self, executors: dict[str, TaskExecutor]) -> None:
        self.executors = dict(executors)

    def execute(self, task: AgentTask) -> AgentExecutionOutcome:
        executor = self.executors.get(task.request.intent)
        if executor is None:
            raise TaskExecutorNotFoundError(
                f"task executor is not registered: {task.request.intent}"
            )
        return executor.execute(task)


__all__ = [
    "AgentExecutionOutcome",
    "TaskArtifact",
    "TaskExecutor",
    "TaskExecutorDispatcher",
    "TaskExecutorNotFoundError",
]
