from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import Principal
from app.db.models import AgentTaskRecord, ApprovalRecord
from app.domain import AgentResult, AgentTask, ApprovalStatus, TaskCreate, TaskStatus


class ConcurrentTaskUpdateError(RuntimeError):
    pass


class TaskRepository(Protocol):
    def add(self, task: AgentTask) -> AgentTask: ...

    def save(self, task: AgentTask) -> AgentTask: ...

    def get(self, task_id: str, tenant_id: str) -> AgentTask: ...

    def list(
        self,
        tenant_id: str,
        limit: int = 50,
        status: TaskStatus | None = None,
    ) -> list[AgentTask]: ...

    def claim_next(self) -> AgentTask | None: ...

    def save_with_approval(
        self,
        task: AgentTask,
        principal: Principal,
        action: str,
        reason: str | None = None,
    ) -> None: ...


class InMemoryTaskRepository:
    """Isolated unit-test repository; runtime wiring uses SQLAlchemyTaskRepository."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}

    def add(self, task: AgentTask) -> AgentTask:
        self._tasks[str(task.id)] = task.model_copy(deep=True)
        return task

    def save(self, task: AgentTask) -> AgentTask:
        return self.add(task)

    def get(self, task_id: str, tenant_id: str) -> AgentTask:
        task = self._tasks.get(task_id)
        if task is None or task.request.tenant_id != tenant_id:
            raise KeyError("task not found")
        return task.model_copy(deep=True)

    def list(
        self,
        tenant_id: str,
        limit: int = 50,
        status: TaskStatus | None = None,
    ) -> list[AgentTask]:
        tasks = [task for task in self._tasks.values() if task.request.tenant_id == tenant_id]
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        return [task.model_copy(deep=True) for task in reversed(tasks[-limit:])]

    def claim_next(self) -> AgentTask | None:
        for task in self._tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.PLANNING
                task.current_step = "planning"
                task.state_version += 1
                task.updated_at = datetime.now(UTC)
                task.events.append("task:planning")
                return task.model_copy(deep=True)
        return None

    def save_with_approval(
        self,
        task: AgentTask,
        principal: Principal,
        action: str,
        reason: str | None = None,
    ) -> None:
        self.save(task)

    def seed(self, tasks: Iterable[AgentTask]) -> None:
        for task in tasks:
            self.add(task)


class SQLAlchemyTaskRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _record_values(task: AgentTask) -> dict:
        return {
            "id": str(task.id),
            "tenant_id": task.request.tenant_id,
            "trace_id": task.trace_id,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "user_id": task.request.user_id,
            "status": task.status.value,
            "intent": task.request.intent,
            "user_query": task.request.user_query,
            "current_step": task.current_step,
            "retry_count": task.retry_count,
            "state_version": task.state_version,
            "request_payload": task.request.model_dump(mode="json"),
            "result_payload": task.result.model_dump(mode="json") if task.result else None,
            "approval_status": task.approval_status.value,
            "approval_hash": task.approval_hash,
            "approver_id": task.approver_id,
            "events": list(task.events),
            "error": task.error,
        }

    @staticmethod
    def _to_domain(record: AgentTaskRecord) -> AgentTask:
        return AgentTask(
            id=record.id,
            trace_id=record.trace_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            status=TaskStatus(record.status),
            current_step=record.current_step,
            retry_count=record.retry_count,
            state_version=record.state_version,
            request=TaskCreate.model_validate(record.request_payload),
            result=AgentResult.model_validate(record.result_payload)
            if record.result_payload
            else None,
            approval_status=ApprovalStatus(record.approval_status),
            approval_hash=record.approval_hash,
            approver_id=record.approver_id,
            events=list(record.events or []),
            error=record.error,
        )

    def add(self, task: AgentTask) -> AgentTask:
        with self.session_factory() as session:
            session.add(AgentTaskRecord(**self._record_values(task)))
            session.commit()
        return task

    def save(self, task: AgentTask) -> AgentTask:
        with self.session_factory() as session:
            result = session.execute(
                update(AgentTaskRecord)
                .where(
                    AgentTaskRecord.id == str(task.id),
                    AgentTaskRecord.tenant_id == task.request.tenant_id,
                    AgentTaskRecord.state_version == task.state_version - 1,
                )
                .values(**self._record_values(task))
            )
            if result.rowcount != 1:
                raise ConcurrentTaskUpdateError("task state version conflict")
            session.commit()
        return task

    def get(self, task_id: str, tenant_id: str) -> AgentTask:
        with self.session_factory() as session:
            record = session.scalar(
                select(AgentTaskRecord).where(
                    AgentTaskRecord.id == task_id,
                    AgentTaskRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                raise KeyError("task not found")
            return self._to_domain(record)

    def list(
        self,
        tenant_id: str,
        limit: int = 50,
        status: TaskStatus | None = None,
    ) -> list[AgentTask]:
        statement = select(AgentTaskRecord).where(AgentTaskRecord.tenant_id == tenant_id)
        if status is not None:
            statement = statement.where(AgentTaskRecord.status == status.value)
        statement = statement.order_by(AgentTaskRecord.created_at.desc()).limit(limit)
        with self.session_factory() as session:
            return [self._to_domain(record) for record in session.scalars(statement)]

    def claim_next(self) -> AgentTask | None:
        with self.session_factory() as session:
            statement = (
                select(AgentTaskRecord)
                .where(AgentTaskRecord.status == TaskStatus.PENDING.value)
                .order_by(AgentTaskRecord.created_at)
                .limit(1)
            )
            if session.bind and session.bind.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            record = session.scalar(statement)
            if record is None:
                return None
            record.status = TaskStatus.PLANNING.value
            record.current_step = "planning"
            record.state_version += 1
            record.updated_at = datetime.now(UTC)
            record.events = [*(record.events or []), "task:planning"]
            session.commit()
            return self._to_domain(record)

    def save_with_approval(
        self,
        task: AgentTask,
        principal: Principal,
        action: str,
        reason: str | None = None,
    ) -> None:
        if not task.approval_hash:
            raise ValueError("approval snapshot is missing")
        with self.session_factory() as session:
            result = session.execute(
                update(AgentTaskRecord)
                .where(
                    AgentTaskRecord.id == str(task.id),
                    AgentTaskRecord.tenant_id == principal.tenant_id,
                    AgentTaskRecord.state_version == task.state_version - 1,
                )
                .values(**self._record_values(task))
            )
            if result.rowcount != 1:
                raise ConcurrentTaskUpdateError("task state version conflict")
            session.add(
                ApprovalRecord(
                    tenant_id=principal.tenant_id,
                    trace_id=task.trace_id,
                    task_id=str(task.id),
                    action=action,
                    result_hash=task.approval_hash,
                    approver_id=principal.user_id,
                    approver_roles=sorted(principal.roles),
                    reason=reason,
                )
            )
            session.commit()
