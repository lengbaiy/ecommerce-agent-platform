from app.domain import AgentTask, ApprovalStatus, TaskStatus
from app.graph.operations_graph import EcommerceOperationsGraph
from app.modules.task_center.executor_dispatcher import AgentExecutionOutcome


class LegacyOperationsTaskExecutor:
    """保持尚未迁移 Agent 的现有 Supervisor Graph 行为。"""

    def __init__(self, graph: EcommerceOperationsGraph) -> None:
        self.graph = graph

    def execute(self, task: AgentTask) -> AgentExecutionOutcome:
        state = self.graph.run(task)
        if task.result is None:
            raise RuntimeError("legacy operations graph completed without a result")
        waiting_approval = state.approval_status == "WAITING_APPROVAL"
        return AgentExecutionOutcome(
            status=(
                TaskStatus.WAITING_APPROVAL
                if waiting_approval
                else TaskStatus.COMPLETED
            ),
            result=task.result,
            approval_status=(
                ApprovalStatus.WAITING_APPROVAL
                if waiting_approval
                else ApprovalStatus.NOT_REQUIRED
            ),
            retry_count=state.retry_count,
        )


__all__ = ["LegacyOperationsTaskExecutor"]
