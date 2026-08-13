from datetime import UTC, datetime

from app.core.config import settings
from app.core.security import Principal
from app.domain import AgentTask, ApprovalStatus, TaskCreate, TaskStatus, result_hash
from app.graph.operations_graph import EcommerceOperationsGraph
from app.policy import ApprovalPolicy
from app.repositories import InMemoryTaskRepository, TaskRepository


class TaskService:
    """Owns trusted identity, task state transitions, execution and approval boundaries."""

    def __init__(
        self,
        repository: TaskRepository | None = None,
        operations_graph: EcommerceOperationsGraph | None = None,
        execution_mode: str | None = None,
        approval_policy: ApprovalPolicy | None = None,
    ) -> None:
        self.repository = repository or InMemoryTaskRepository()
        self.operations_graph = operations_graph or EcommerceOperationsGraph()
        self.execution_mode = execution_mode or settings.task_execution_mode
        self.approval_policy = approval_policy or ApprovalPolicy()

    def create(self, payload: TaskCreate, principal: Principal) -> AgentTask:
        trusted_payload = payload.model_copy(
            update={"tenant_id": principal.tenant_id, "user_id": principal.user_id}
        )
        task = AgentTask(request=trusted_payload)
        self.repository.add(task)
        if self.execution_mode == "inline":
            self._execute(task, claimed=False)
        return task

    def run_next(self) -> AgentTask | None:
        task = self.repository.claim_next()
        if task is None:
            return None
        return self._execute(task, claimed=True)

    def _execute(self, task: AgentTask, *, claimed: bool) -> AgentTask:
        try:
            if not claimed:
                self._transition(task, TaskStatus.PLANNING, "task:planning")
            self._transition(task, TaskStatus.RUNNING, "task:running")
            state = self.operations_graph.run(task)
            if state.approval_status == "WAITING_APPROVAL":
                if task.result is None:
                    raise ValueError("approval task has no result")
                task.approval_hash = result_hash(task.result)
                task.approval_status = ApprovalStatus.WAITING_APPROVAL
                self._transition(task, TaskStatus.WAITING_APPROVAL, "task:waiting_approval")
            else:
                self._transition(task, TaskStatus.COMPLETED, "task:completed")
            return task
        except Exception as error:
            task.error = str(error)
            self._transition(task, TaskStatus.FAILED, "task:failed")
            raise

    def get(self, task_id: str, principal: Principal) -> AgentTask:
        return self.repository.get(task_id, principal.tenant_id)

    def list(
        self,
        principal: Principal,
        limit: int = 50,
        status: TaskStatus | None = None,
    ) -> list[AgentTask]:
        return self.repository.list(principal.tenant_id, limit, status)

    def cancel(self, task_id: str, principal: Principal) -> AgentTask:
        task = self.get(task_id, principal)
        if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ValueError(f"task cannot be cancelled from {task.status}")
        self._transition(task, TaskStatus.CANCELLED, "task:cancelled")
        return task

    def approve(
        self,
        task_id: str,
        principal: Principal,
        reason: str | None = None,
    ) -> AgentTask:
        task = self.get(task_id, principal)
        if task.status != TaskStatus.WAITING_APPROVAL or task.result is None:
            raise ValueError("task is not waiting for approval")
        if task.approval_hash != result_hash(task.result):
            raise ValueError("approved result hash mismatch")
        task.approval_status = ApprovalStatus.APPROVED
        task.approver_id = principal.user_id
        task.events.append(f"approval:approved:{principal.user_id}")
        self.approval_policy.validate_completion(task)
        self._transition(task, TaskStatus.COMPLETED, "task:completed", persist=False)
        self.repository.save_with_approval(task, principal, "APPROVED", reason)
        return task

    def reject(
        self,
        task_id: str,
        principal: Principal,
        reason: str | None = None,
    ) -> AgentTask:
        task = self.get(task_id, principal)
        if task.status != TaskStatus.WAITING_APPROVAL:
            raise ValueError("task is not waiting for approval")
        task.approval_status = ApprovalStatus.REJECTED
        task.approver_id = principal.user_id
        task.events.append(f"approval:rejected:{principal.user_id}")
        self._transition(task, TaskStatus.CANCELLED, "task:cancelled", persist=False)
        self.repository.save_with_approval(task, principal, "REJECTED", reason)
        return task

    def _transition(
        self,
        task: AgentTask,
        status: TaskStatus,
        event: str,
        *,
        persist: bool = True,
    ) -> None:
        task.status = status
        task.current_step = event.removeprefix("task:")
        task.state_version += 1
        task.updated_at = datetime.now(UTC)
        task.events.append(event)
        if persist:
            self.repository.save(task)
