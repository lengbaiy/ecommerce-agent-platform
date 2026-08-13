from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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
    request: TaskCreate
    result: AgentResult | None = None
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    approval_hash: str | None = None
    approver_id: str | None = None
    events: list[str] = Field(default_factory=list)
    error: str | None = None


class AgentTaskList(BaseModel):
    items: list[AgentTask]
    total: int


def result_hash(result: AgentResult) -> str:
    return sha256(result.model_dump_json().encode()).hexdigest()
