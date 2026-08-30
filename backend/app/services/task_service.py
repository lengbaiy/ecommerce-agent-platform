from __future__ import annotations
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import settings
from app.core.security import Principal
from app.domain import (
    AgentTask,
    ApprovalStatus,
    TaskCreate,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskStatus,
    create_task_event,
    result_hash,
)
from app.modules.task_center import TaskExecutorDispatcher, TaskInputDispatcher
from app.policy import ApprovalPolicy
from app.repositories import InMemoryTaskRepository, TaskRepository


class TaskService:
    """Owns trusted identity, task state transitions, execution and approval boundaries."""

    def __init__(
        self,
        repository: TaskRepository | None = None,
        execution_mode: str | None = None,
        approval_policy: ApprovalPolicy | None = None,
        input_dispatcher: TaskInputDispatcher | None = None,
        executor_dispatcher: TaskExecutorDispatcher | None = None,
        worker_id: str | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self.repository = repository or InMemoryTaskRepository()
        self.execution_mode = execution_mode or settings.task_execution_mode
        self.approval_policy = approval_policy or ApprovalPolicy()
        self.input_dispatcher = input_dispatcher
        self.executor_dispatcher = executor_dispatcher
        self.worker_id = worker_id or f"worker-{uuid4()}"
        self.lease_seconds = lease_seconds or settings.task_lease_seconds

    def create(self, payload: TaskCreate, principal: Principal) -> AgentTask:
        trusted_payload = payload.model_copy(
            update={"tenant_id": principal.tenant_id, "user_id": principal.user_id}
        )
        if self.input_dispatcher is not None:
            self.input_dispatcher.validate_task(trusted_payload)
        task = AgentTask(request=trusted_payload)
        self.repository.add(task)
        if self.execution_mode == "inline":
            self._execute(task, claimed=False)
        return task

    def run_next(self) -> AgentTask | None:
        task = self.repository.claim_next(self.worker_id, self.lease_seconds)
        if task is None:
            return None
        return self._execute(task, claimed=True)

    def _execute(self, task: AgentTask, *, claimed: bool) -> AgentTask:
        try:
            if not claimed:
                self._transition(task, TaskStatus.PLANNING, TaskEventType.TASK_PLANNING)
            self._transition(task, TaskStatus.RUNNING, TaskEventType.TASK_RUNNING)
            if claimed:
                self.repository.heartbeat(
                    str(task.id), self.worker_id, self.lease_seconds
                )
            if self.executor_dispatcher is None:
                raise RuntimeError("task executor dispatcher is not configured")
            outcome = self.executor_dispatcher.execute(task)
            # Graph progress and cancellation may have advanced persisted events/state.
            task = self.repository.get(str(task.id), task.request.tenant_id or "")
            task.result = outcome.result
            task.error = outcome.error
            task.retry_count = max(task.retry_count, outcome.retry_count)
            task.approval_status = outcome.approval_status

            if outcome.status is TaskStatus.WAITING_APPROVAL:
                if outcome.result is None:
                    raise ValueError("approval task has no result")
                task.approval_hash = result_hash(outcome.result)
                task.approval_status = ApprovalStatus.WAITING_APPROVAL
                self._transition(
                    task,
                    TaskStatus.WAITING_APPROVAL,
                    TaskEventType.TASK_WAITING_APPROVAL,
                    persist=False,
                )
                self.repository.finalize(task, outcome.artifacts)
            else:
                event_types = {
                    TaskStatus.COMPLETED: TaskEventType.TASK_COMPLETED,
                    TaskStatus.DEGRADED: TaskEventType.TASK_DEGRADED,
                    TaskStatus.FAILED: TaskEventType.TASK_FAILED,
                    TaskStatus.CANCELLED: TaskEventType.TASK_CANCELLED,
                }
                self._transition(
                    task,
                    outcome.status,
                    event_types[outcome.status],
                    persist=False,
                )
                task.completed_at = datetime.now(UTC)
                if task.result is not None:
                    task.result_hash = result_hash(task.result)
                self.repository.finalize(task, outcome.artifacts)
            return task
        except Exception as error:
            task.error = TaskError(
                code="TASK_EXECUTION_FAILED",
                message=str(error) or error.__class__.__name__,
                step=task.current_step,
                details={"exception_type": error.__class__.__name__},
            )
            self._transition(task, TaskStatus.FAILED, TaskEventType.TASK_FAILED)
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
        return self.repository.request_cancel(task_id, principal.tenant_id)

    def events(
        self,
        task_id: str,
        principal: Principal,
        after_event_id: str | None = None,
    ) -> list[TaskEvent]:
        return self.repository.events(
            task_id,
            principal.tenant_id,
            after_event_id,
        )

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
        task.events.append(
            create_task_event(
                task,
                TaskEventType.APPROVAL_APPROVED,
                "Task approval granted.",
                step="approval",
            )
        )
        self.approval_policy.validate_completion(task)
        self._transition(
            task,
            TaskStatus.COMPLETED,
            TaskEventType.TASK_COMPLETED,
            persist=False,
        )
        task.completed_at = datetime.now(UTC)
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
        task.events.append(
            create_task_event(
                task,
                TaskEventType.APPROVAL_REJECTED,
                "Task approval rejected.",
                step="approval",
            )
        )
        self._transition(
            task,
            TaskStatus.CANCELLED,
            TaskEventType.TASK_CANCELLED,
            persist=False,
        )
        task.completed_at = datetime.now(UTC)
        self.repository.save_with_approval(task, principal, "REJECTED", reason)
        return task

    def _transition(
        self,
        task: AgentTask,
        status: TaskStatus,
        event_type: TaskEventType,
        *,
        persist: bool = True,
    ) -> None:
        task.status = status
        task.current_step = event_type.value.removeprefix("task.")
        task.state_version += 1
        task.updated_at = datetime.now(UTC)
        task.events.append(
            create_task_event(
                task,
                event_type,
                f"Task status changed to {status.value}.",
            )
        )
        if persist:
            self.repository.save(task)
