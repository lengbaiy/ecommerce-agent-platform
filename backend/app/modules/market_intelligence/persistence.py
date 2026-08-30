from datetime import UTC, datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AgentStepRecord,
    AgentTaskRecord,
    GraphCheckpointRecord,
    TaskEventRecord,
    ToolCallRecord,
)
from app.domain import TaskEvent, TaskEventType, TaskStatus
from app.modules.market_intelligence.state import GraphStep, MarketIntelligenceState
from app.tools.support.contracts import ToolRequest, ToolResponse

_STATE_ADAPTER = TypeAdapter(MarketIntelligenceState)


class SQLAlchemyTaskEventPublisher:
    """Persists progress before an SSE consumer can observe it."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def publish(
        self,
        task_id: str,
        event_type: TaskEventType,
        summary: str,
        *,
        step: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            task = session.scalar(
                select(AgentTaskRecord)
                .where(AgentTaskRecord.id == task_id)
                .with_for_update()
            )
            if task is None:
                return
            event = TaskEvent(
                task_id=task.id,
                trace_id=task.trace_id,
                event_type=event_type,
                state_version=max(1, task.state_version),
                step=step,
                status=TaskStatus(task.status),
                summary=summary,
            )
            session.add(
                TaskEventRecord(
                    id=event.event_id,
                    tenant_id=task.tenant_id,
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


class SQLAlchemyMarketCancellationPort:
    def __init__(self, session_factory: sessionmaker[Session], lease_seconds: int) -> None:
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds

    def heartbeat(self, task_id: str) -> None:
        now = datetime.now(UTC)
        with self.session_factory() as session:
            session.execute(
                update(AgentTaskRecord)
                .where(
                    AgentTaskRecord.id == task_id,
                    AgentTaskRecord.claimed_by.is_not(None),
                )
                .values(
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=self.lease_seconds),
                )
            )
            session.commit()

    def is_cancelled(self, task_id: str) -> bool:
        with self.session_factory() as session:
            row = session.execute(
                select(
                    AgentTaskRecord.cancel_requested_at,
                    AgentTaskRecord.status,
                ).where(AgentTaskRecord.id == task_id)
            ).one_or_none()
            return bool(
                row
                and (
                    row.cancel_requested_at is not None
                    or row.status == "CANCELLED"
                )
            )


class SQLAlchemyMarketCheckpointPort:
    """Stores one immutable checkpoint after each successful Graph node."""

    graph_name = "market_intelligence"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def load(self, task_id: str) -> MarketIntelligenceState | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(GraphCheckpointRecord)
                .where(
                    GraphCheckpointRecord.task_id == task_id,
                    GraphCheckpointRecord.graph_name == self.graph_name,
                )
                .order_by(GraphCheckpointRecord.state_version.desc())
                .limit(1)
            )
            if record is None:
                return None
            return _STATE_ADAPTER.validate_python(record.state_payload)

    def save(self, state: MarketIntelligenceState) -> None:
        context = state["context"]
        with self.session_factory() as session:
            existing = session.scalar(
                select(GraphCheckpointRecord.id).where(
                    GraphCheckpointRecord.task_id == context.task_id,
                    GraphCheckpointRecord.graph_name == self.graph_name,
                    GraphCheckpointRecord.state_version == state["state_version"],
                )
            )
            if existing is not None:
                return
            session.add(
                GraphCheckpointRecord(
                    tenant_id=context.tenant_id,
                    trace_id=context.trace_id,
                    task_id=context.task_id,
                    graph_name=self.graph_name,
                    current_step=state["current_step"].value,
                    state_version=state["state_version"],
                    state_payload=_STATE_ADAPTER.dump_python(state, mode="json"),
                )
            )
            session.commit()


class SQLAlchemyToolExecutionPort:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_publisher: SQLAlchemyTaskEventPublisher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.event_publisher = event_publisher or SQLAlchemyTaskEventPublisher(
            session_factory
        )

    def load(self, idempotency_key: str) -> ToolResponse | None:
        with self.session_factory() as session:
            record = session.scalar(
                select(ToolCallRecord).where(
                    ToolCallRecord.idempotency_key == idempotency_key,
                    ToolCallRecord.status == "COMPLETED",
                )
            )
            return (
                ToolResponse.model_validate(record.response_payload)
                if record and record.response_payload
                else None
            )

    def start(self, request: ToolRequest, tool_name: str) -> None:
        if request.idempotency_key is None or request.task_id is None:
            return
        now = datetime.now(UTC)
        with self.session_factory() as session:
            record = session.scalar(
                select(ToolCallRecord).where(
                    ToolCallRecord.idempotency_key == request.idempotency_key
                )
            )
            if record is None:
                session.add(
                    ToolCallRecord(
                        tenant_id=request.tenant_id,
                        trace_id=request.trace_id,
                        task_id=request.task_id,
                        tool_name=tool_name,
                        step_name=request.step_name,
                        status="RUNNING",
                        attempt=request.attempt,
                        idempotency_key=request.idempotency_key,
                        request_payload=request.model_dump(mode="json"),
                        started_at=now,
                    )
                )
            else:
                record.status = "RUNNING"
                record.attempt = request.attempt
                record.request_payload = request.model_dump(mode="json")
                record.started_at = now
                record.finished_at = None
            session.commit()
        self.event_publisher.publish(
            request.task_id,
            TaskEventType.TOOL_STARTED,
            f"Tool {tool_name} attempt {request.attempt} started.",
            step=request.step_name,
        )
        if request.attempt > 1:
            self.event_publisher.publish(
                request.task_id,
                TaskEventType.NODE_RETRYING,
                f"Node {request.step_name} is retrying.",
                step=request.step_name,
            )

    def finish(self, request: ToolRequest, response: ToolResponse) -> None:
        if request.idempotency_key is None:
            return
        with self.session_factory() as session:
            record = session.scalar(
                select(ToolCallRecord).where(
                    ToolCallRecord.idempotency_key == request.idempotency_key
                )
            )
            if record is None:
                return
            record.status = "COMPLETED" if response.success else "FAILED"
            record.error_code = response.error.code if response.error else None
            record.response_payload = response.model_dump(mode="json")
            record.finished_at = datetime.now(UTC)
            tool_name = record.tool_name
            session.commit()
        if request.task_id is not None:
            self.event_publisher.publish(
                request.task_id,
                (
                    TaskEventType.TOOL_COMPLETED
                    if response.success
                    else TaskEventType.TOOL_FAILED
                ),
                (
                    f"Tool {tool_name} completed."
                    if response.success
                    else f"Tool {tool_name} failed."
                ),
                step=request.step_name,
            )

    def progress(
        self,
        request: ToolRequest,
        tool_name: str,
        summary: str,
    ) -> None:
        if request.task_id is None:
            return
        self.event_publisher.publish(
            request.task_id,
            TaskEventType.TOOL_PROGRESS,
            summary,
            step=request.step_name,
        )


class SQLAlchemyStepExecutionPort:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_publisher: SQLAlchemyTaskEventPublisher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.event_publisher = event_publisher or SQLAlchemyTaskEventPublisher(
            session_factory
        )

    def start(self, state: MarketIntelligenceState, step: GraphStep) -> str:
        context = state["context"]
        record = AgentStepRecord(
            tenant_id=context.tenant_id,
            trace_id=context.trace_id,
            task_id=context.task_id,
            step_name=step.value,
            status="RUNNING",
            attempt=state["retry_counts"][step] + 1,
            state_version=state["state_version"],
            started_at=datetime.now(UTC),
        )
        with self.session_factory() as session:
            session.add(record)
            session.flush()
            execution_id = record.id
            session.commit()
        self.event_publisher.publish(
            context.task_id,
            TaskEventType.NODE_STARTED,
            f"Node {step.value} started.",
            step=step.value,
        )
        return execution_id

    def finish(self, execution_id: str | None, state: MarketIntelligenceState) -> None:
        if execution_id is None:
            return
        error = state["error"]
        with self.session_factory() as session:
            session.execute(
                update(AgentStepRecord)
                .where(AgentStepRecord.id == execution_id)
                .values(
                    status="FAILED" if error else "COMPLETED",
                    state_version=state["state_version"],
                    error_code=error.code if error else None,
                    finished_at=datetime.now(UTC),
                )
            )
            session.commit()
        self.event_publisher.publish(
            state["context"].task_id,
            TaskEventType.NODE_COMPLETED,
            (
                f"Node {state['current_step'].value} completed."
                if error is None
                else f"Node {state['current_step'].value} stopped with {error.code}."
            ),
            step=state["current_step"].value,
        )

__all__ = [
    "SQLAlchemyMarketCancellationPort",
    "SQLAlchemyMarketCheckpointPort",
    "SQLAlchemyToolExecutionPort",
    "SQLAlchemyStepExecutionPort",
    "SQLAlchemyTaskEventPublisher",
]
