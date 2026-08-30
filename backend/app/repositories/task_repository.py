from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import Principal
from app.db.models import (
    AgentTaskRecord,
    ApprovalRecord,
    MarketIntelligenceReportRecord,
    TaskEventRecord,
)
from app.domain import (
    AgentResult,
    AgentTask,
    ApprovalStatus,
    TaskCreate,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskStatus,
    create_task_event,
)

if TYPE_CHECKING:
    from app.modules.task_center.executor_dispatcher import TaskArtifact


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

    def claim_next(self, worker_id: str, lease_seconds: int) -> AgentTask | None: ...

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: int) -> None: ...

    def request_cancel(self, task_id: str, tenant_id: str) -> AgentTask: ...

    def is_cancel_requested(self, task_id: str) -> bool: ...

    def events(
        self,
        task_id: str,
        tenant_id: str,
        after_event_id: str | None = None,
    ) -> list[TaskEvent]: ...

    def finalize(self, task: AgentTask, artifacts: tuple[TaskArtifact, ...]) -> AgentTask: ...

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

    def claim_next(
        self,
        worker_id: str = "in-memory",
        lease_seconds: int = 300,
    ) -> AgentTask | None:
        now = datetime.now(UTC)
        for task in self._tasks.values():
            reclaimable = (
                task.status in {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.RETRYING}
                and task.lease_expires_at is not None
                and task.lease_expires_at <= now
            )
            if task.status == TaskStatus.PENDING or reclaimable:
                task.status = TaskStatus.PLANNING
                task.current_step = "planning"
                task.state_version += 1
                task.updated_at = now
                task.claimed_by = worker_id
                task.heartbeat_at = now
                task.lease_expires_at = now + timedelta(seconds=lease_seconds)
                task.events.append(
                    create_task_event(
                        task,
                        TaskEventType.TASK_PLANNING,
                        "Task claimed by worker.",
                    )
                )
                return task.model_copy(deep=True)
        return None

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: int) -> None:
        task = self._tasks[task_id]
        if task.claimed_by != worker_id:
            raise ConcurrentTaskUpdateError("task lease owner mismatch")
        now = datetime.now(UTC)
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)

    def request_cancel(self, task_id: str, tenant_id: str) -> AgentTask:
        task = self.get(task_id, tenant_id)
        task.cancel_requested_at = datetime.now(UTC)
        if task.status is TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            task.completed_at = task.cancel_requested_at
        task.state_version += 1
        task.updated_at = task.cancel_requested_at
        task.events.append(
            create_task_event(
                task,
                TaskEventType.TASK_CANCELLED
                if task.status is TaskStatus.CANCELLED
                else TaskEventType.TASK_CANCEL_REQUESTED,
                "Task cancellation requested.",
            )
        )
        return self.save(task)

    def is_cancel_requested(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return bool(task and (task.cancel_requested_at or task.status is TaskStatus.CANCELLED))

    def events(
        self,
        task_id: str,
        tenant_id: str,
        after_event_id: str | None = None,
    ) -> list[TaskEvent]:
        events = self.get(task_id, tenant_id).events
        if after_event_id is None:
            return events
        for index, event in enumerate(events):
            if event.event_id == after_event_id:
                return events[index + 1 :]
        return events

    def finalize(self, task: AgentTask, artifacts: tuple[TaskArtifact, ...] = ()) -> AgentTask:
        task.claimed_by = None
        task.lease_expires_at = None
        task.heartbeat_at = datetime.now(UTC)
        return self.save(task)

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
            "events": [event.model_dump(mode="json") for event in task.events],
            "error": task.error.model_dump_json() if task.error else None,
            "cancel_requested_at": task.cancel_requested_at,
            "claimed_by": task.claimed_by,
            "lease_expires_at": task.lease_expires_at,
            "heartbeat_at": task.heartbeat_at,
            "result_hash": task.result_hash,
            "completed_at": task.completed_at,
        }

    @staticmethod
    def _to_domain(
        record: AgentTaskRecord,
        events: list[TaskEvent] | None = None,
    ) -> AgentTask:
        legacy_events = SQLAlchemyTaskRepository._task_events(record)
        if events is not None:
            events = sorted(
                {
                    event.event_id: event
                    for event in [*legacy_events, *events]
                }.values(),
                key=lambda event: (event.timestamp, event.event_id),
            )
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
            events=events if events is not None else legacy_events,
            error=SQLAlchemyTaskRepository._task_error(record.error),
            cancel_requested_at=record.cancel_requested_at,
            claimed_by=record.claimed_by,
            lease_expires_at=record.lease_expires_at,
            heartbeat_at=record.heartbeat_at,
            result_hash=record.result_hash,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _task_error(value: str | None) -> TaskError | None:
        if value is None:
            return None
        try:
            return TaskError.model_validate_json(value)
        except ValueError:
            return TaskError(code="LEGACY_TASK_ERROR", message=value)

    @staticmethod
    def _task_events(record: AgentTaskRecord) -> list[TaskEvent]:
        event_types = {
            "task:planning": TaskEventType.TASK_PLANNING,
            "task:running": TaskEventType.TASK_RUNNING,
            "task:waiting_approval": TaskEventType.TASK_WAITING_APPROVAL,
            "task:completed": TaskEventType.TASK_COMPLETED,
            "task:failed": TaskEventType.TASK_FAILED,
            "task:cancelled": TaskEventType.TASK_CANCELLED,
        }
        events: list[TaskEvent] = []
        for value in record.events or []:
            if isinstance(value, dict):
                events.append(TaskEvent.model_validate(value))
                continue
            legacy_value = str(value)
            events.append(
                TaskEvent(
                    task_id=record.id,
                    trace_id=record.trace_id,
                    event_type=event_types.get(
                        legacy_value,
                        TaskEventType.NODE_COMPLETED,
                    ),
                    state_version=max(1, record.state_version),
                    step=record.current_step,
                    status=TaskStatus(record.status),
                    timestamp=record.updated_at,
                    summary=legacy_value,
                )
            )
        return events

    @staticmethod
    def _event_record(task: AgentTask, event: TaskEvent) -> TaskEventRecord:
        return TaskEventRecord(
            id=event.event_id,
            tenant_id=task.request.tenant_id,
            trace_id=event.trace_id,
            created_at=event.timestamp,
            task_id=event.task_id,
            event_type=event.event_type.value,
            state_version=event.state_version,
            step=event.step,
            status=event.status.value,
            summary=event.summary,
        )

    @staticmethod
    def _to_event(record: TaskEventRecord) -> TaskEvent:
        return TaskEvent(
            event_id=record.id,
            task_id=record.task_id,
            trace_id=record.trace_id,
            event_type=TaskEventType(record.event_type),
            state_version=record.state_version,
            step=record.step,
            status=TaskStatus(record.status),
            timestamp=record.created_at,
            summary=record.summary,
        )

    @classmethod
    def _persist_events(
        cls,
        session: Session,
        task: AgentTask,
    ) -> None:
        event_ids = [event.event_id for event in task.events]
        if not event_ids:
            return
        existing_ids = set(
            session.scalars(
                select(TaskEventRecord.id).where(TaskEventRecord.id.in_(event_ids))
            )
        )
        session.add_all(
            [
                cls._event_record(task, event)
                for event in task.events
                if event.event_id not in existing_ids
            ]
        )

    @classmethod
    def _load_events(cls, session: Session, task_id: str) -> list[TaskEvent]:
        records = session.scalars(
            select(TaskEventRecord)
            .where(TaskEventRecord.task_id == task_id)
            .order_by(TaskEventRecord.created_at, TaskEventRecord.id)
        ).all()
        return [cls._to_event(record) for record in records]

    def add(self, task: AgentTask) -> AgentTask:
        with self.session_factory() as session:
            session.add(AgentTaskRecord(**self._record_values(task)))
            self._persist_events(session, task)
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
            self._persist_events(session, task)
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
            return self._to_domain(record, self._load_events(session, task_id))

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
            return [
                self._to_domain(record, self._load_events(session, record.id))
                for record in session.scalars(statement)
            ]

    def claim_next(self, worker_id: str = "worker", lease_seconds: int = 300) -> AgentTask | None:
        with self.session_factory() as session:
            now = datetime.now(UTC)
            statement = (
                select(AgentTaskRecord)
                .where(
                    or_(
                        AgentTaskRecord.status == TaskStatus.PENDING.value,
                        (
                            AgentTaskRecord.status.in_(
                                [
                                    TaskStatus.PLANNING.value,
                                    TaskStatus.RUNNING.value,
                                    TaskStatus.RETRYING.value,
                                ]
                            )
                            & (AgentTaskRecord.lease_expires_at < now)
                        ),
                    )
                )
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
            record.updated_at = now
            record.claimed_by = worker_id
            record.heartbeat_at = now
            record.lease_expires_at = now + timedelta(seconds=lease_seconds)
            event = TaskEvent(
                task_id=record.id,
                trace_id=record.trace_id,
                event_type=TaskEventType.TASK_PLANNING,
                state_version=record.state_version,
                step=record.current_step,
                status=TaskStatus.PLANNING,
                timestamp=record.updated_at,
                summary="Task claimed by worker.",
            )
            record.events = [
                *(record.events or []),
                event.model_dump(mode="json"),
            ]
            session.add(
                TaskEventRecord(
                    id=event.event_id,
                    tenant_id=record.tenant_id,
                    trace_id=event.trace_id,
                    created_at=event.timestamp,
                    task_id=event.task_id,
                    event_type=event.event_type.value,
                    state_version=event.state_version,
                    step=event.step,
                    status=event.status.value,
                    summary=event.summary,
                )
            )
            session.commit()
            return self._to_domain(record, self._load_events(session, record.id))

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: int) -> None:
        now = datetime.now(UTC)
        with self.session_factory() as session:
            result = session.execute(
                update(AgentTaskRecord)
                .where(
                    AgentTaskRecord.id == task_id,
                    AgentTaskRecord.claimed_by == worker_id,
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
            )
            if result.rowcount != 1:
                raise ConcurrentTaskUpdateError("task lease owner mismatch")
            session.commit()

    def request_cancel(self, task_id: str, tenant_id: str) -> AgentTask:
        with self.session_factory() as session:
            record = session.scalar(
                select(AgentTaskRecord)
                .where(AgentTaskRecord.id == task_id, AgentTaskRecord.tenant_id == tenant_id)
                .with_for_update()
            )
            if record is None:
                raise KeyError("task not found")
            terminal = {
                TaskStatus.COMPLETED.value,
                TaskStatus.DEGRADED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            }
            if record.status in terminal:
                raise ValueError(f"task cannot be cancelled from {record.status}")
            now = datetime.now(UTC)
            record.cancel_requested_at = now
            if record.status == TaskStatus.PENDING.value:
                record.status = TaskStatus.CANCELLED.value
                record.current_step = "cancelled"
                record.completed_at = now
            record.state_version += 1
            record.updated_at = now
            event = TaskEvent(
                task_id=record.id,
                trace_id=record.trace_id,
                event_type=(
                    TaskEventType.TASK_CANCELLED
                    if record.status == TaskStatus.CANCELLED.value
                    else TaskEventType.TASK_CANCEL_REQUESTED
                ),
                state_version=record.state_version,
                step=record.current_step,
                status=TaskStatus(record.status),
                timestamp=now,
                summary="Task cancellation requested.",
            )
            record.events = [*(record.events or []), event.model_dump(mode="json")]
            session.add(
                TaskEventRecord(
                    id=event.event_id,
                    tenant_id=record.tenant_id,
                    trace_id=event.trace_id,
                    created_at=event.timestamp,
                    task_id=event.task_id,
                    event_type=event.event_type.value,
                    state_version=event.state_version,
                    step=event.step,
                    status=event.status.value,
                    summary=event.summary,
                )
            )
            session.commit()
            return self._to_domain(record, self._load_events(session, record.id))

    def is_cancel_requested(self, task_id: str) -> bool:
        with self.session_factory() as session:
            record = session.execute(
                select(AgentTaskRecord.cancel_requested_at, AgentTaskRecord.status).where(
                    AgentTaskRecord.id == task_id
                )
            ).one_or_none()
            return bool(
                record
                and (
                    record.cancel_requested_at is not None
                    or record.status == TaskStatus.CANCELLED.value
                )
            )

    def events(
        self,
        task_id: str,
        tenant_id: str,
        after_event_id: str | None = None,
    ) -> list[TaskEvent]:
        with self.session_factory() as session:
            record = session.scalar(
                select(AgentTaskRecord).where(
                    AgentTaskRecord.id == task_id,
                    AgentTaskRecord.tenant_id == tenant_id,
                )
            )
            if record is None:
                raise KeyError("task not found")
            # 合并旧 JSON 事件与新的持久化事件流，保证存量任务仍可回放。
            events = self._to_domain(record, self._load_events(session, task_id)).events
        if after_event_id is None:
            return events
        for index, event in enumerate(events):
            if event.event_id == after_event_id:
                return events[index + 1 :]
        return events

    def finalize(self, task: AgentTask, artifacts: tuple[TaskArtifact, ...] = ()) -> AgentTask:
        task.claimed_by = None
        task.lease_expires_at = None
        task.heartbeat_at = datetime.now(UTC)
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
            self._persist_events(session, task)
            for artifact in artifacts:
                if artifact.artifact_type != "market_intelligence_report":
                    continue
                canonical = json.dumps(
                    artifact.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                report_hash = sha256(canonical.encode("utf-8")).hexdigest()
                existing = session.scalar(
                    select(MarketIntelligenceReportRecord).where(
                        MarketIntelligenceReportRecord.task_id == str(task.id)
                    )
                )
                values = {
                    "tenant_id": task.request.tenant_id,
                    "trace_id": task.trace_id,
                    "task_id": str(task.id),
                    "report_id": artifact.artifact_id,
                    "schema_version": artifact.schema_version,
                    "status": artifact.status,
                    "report_hash": report_hash,
                    "report_payload": artifact.payload,
                }
                if existing is None:
                    session.add(MarketIntelligenceReportRecord(**values))
                else:
                    for key, value in values.items():
                        setattr(existing, key, value)
                task.result_hash = report_hash
                session.execute(
                    update(AgentTaskRecord)
                    .where(AgentTaskRecord.id == str(task.id))
                    .values(result_hash=report_hash)
                )
            session.commit()
        return task

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
            self._persist_events(session, task)
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
