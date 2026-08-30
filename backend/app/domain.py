from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.modules.market_intelligence.schemas.request import MarketIntelligenceRequest


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RETRYING = "RETRYING"
    DEGRADED = "DEGRADED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PreviewWarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"


class TaskEventType(StrEnum):
    TASK_PLANNING = "task.planning"
    TASK_RUNNING = "task.running"
    TASK_WAITING_APPROVAL = "task.waiting_approval"
    TASK_DEGRADED = "task.degraded"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    TASK_CANCEL_REQUESTED = "task.cancel_requested"
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    NODE_RETRYING = "node.retrying"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DatasetMatch(FrozenContract):
    dataset_id: str = Field(min_length=1)
    supported: bool
    score: float = Field(ge=0, le=1)
    platform: str = Field(min_length=1)
    market: str = Field(min_length=1)
    category: str = Field(min_length=1)
    canonical_keyword: str = Field(min_length=1)
    matched_aliases: list[str] = Field(default_factory=list)
    reason_code: str | None = None


class DataSourceOption(FrozenContract):
    platform: str = Field(min_length=1)
    market: str = Field(min_length=1)
    data_source_mode: Literal["fixed_dataset", "official_api"]
    label: str = Field(min_length=1)
    available: bool
    supports_products: bool = False
    supports_reviews: bool = False
    supports_market_metrics: bool = False
    unavailable_reason: str | None = None


class PreviewWarning(FrozenContract):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: PreviewWarningSeverity = PreviewWarningSeverity.WARNING
    field: str | None = None


class TaskPreviewRequest(FrozenContract):
    schema_version: Literal["1.0"] = "1.0"
    user_query: str = Field(min_length=5, max_length=1000)
    intent: str = Field(default="market_entry", min_length=1)


class TaskPreviewResponse(FrozenContract):
    schema_version: Literal["1.0"] = "1.0"
    intent: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    normalized_input: MarketIntelligenceRequest | None = None
    missing_fields: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    dataset_matches: list[DatasetMatch] = Field(default_factory=list)
    data_source_options: list[DataSourceOption] = Field(default_factory=list)
    warnings: list[PreviewWarning] = Field(default_factory=list)


class TaskError(FrozenContract):
    schema_version: Literal["1.0"] = "1.0"
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    step: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class TaskEvent(FrozenContract):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    event_type: TaskEventType
    state_version: int = Field(ge=1)
    step: str | None = None
    status: TaskStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str = Field(min_length=1)


class TaskCreate(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=1)
    user_id: str | None = Field(default=None, min_length=1)
    user_query: str = Field(min_length=5, max_length=1000)
    intent: str = "market_entry"
    business_context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    priority: TaskPriority = TaskPriority.MEDIUM


class EvidenceRef(BaseModel):
    id: str
    grade: str = Field(pattern="^[ABCD]$")
    source: str
    summary: str


class AgentResult(BaseModel):
    result_type: str
    summary: str
    facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.65, ge=0, le=1)
    requires_approval: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: TaskStatus = TaskStatus.PENDING
    current_step: str | None = None
    retry_count: int = 0
    state_version: int = 1
    cancel_requested_at: datetime | None = None
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    result_hash: str | None = None
    completed_at: datetime | None = None
    request: TaskCreate
    result: AgentResult | None = None
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approval_hash: str | None = None
    approver_id: str | None = None
    events: list[TaskEvent] = Field(default_factory=list)
    error: TaskError | None = None


class AgentTaskList(BaseModel):
    items: list[AgentTask]
    total: int


def result_hash(result: AgentResult) -> str:
    return sha256(result.model_dump_json().encode()).hexdigest()


def create_task_event(
    task: AgentTask,
    event_type: TaskEventType,
    summary: str,
    *,
    step: str | None = None,
) -> TaskEvent:
    """使用任务当前的可信状态创建可持久化、可恢复的事件。"""

    return TaskEvent(
        task_id=str(task.id),
        trace_id=task.trace_id,
        event_type=event_type,
        state_version=task.state_version,
        step=step or task.current_step,
        status=task.status,
        summary=summary,
    )
