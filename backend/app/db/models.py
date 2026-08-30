from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantAuditRecord(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AgentTaskRecord(TenantAuditRecord):
    __tablename__ = "agent_task"

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    intent: Mapped[str] = mapped_column(String(64), index=True)
    user_query: Mapped[str] = mapped_column(Text)
    current_step: Mapped[str | None] = mapped_column(String(96), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(32), index=True)
    approval_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approver_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    events: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TaskEventRecord(TenantAuditRecord):
    __tablename__ = "task_event"

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    state_version: Mapped[int] = mapped_column(Integer)
    step: Mapped[str | None] = mapped_column(String(96), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(Text)


class AgentStepRecord(TenantAuditRecord):
    __tablename__ = "agent_step"

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    step_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    state_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ToolCallRecord(TenantAuditRecord):
    __tablename__ = "tool_call"

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(96), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GraphCheckpointRecord(TenantAuditRecord):
    __tablename__ = "graph_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "graph_name",
            "state_version",
            name="uq_checkpoint_task_graph_version",
        ),
    )

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    graph_name: Mapped[str] = mapped_column(String(96), index=True)
    current_step: Mapped[str] = mapped_column(String(96))
    state_version: Mapped[int] = mapped_column(Integer)
    state_payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MarketIntelligenceReportRecord(TenantAuditRecord):
    __tablename__ = "market_intelligence_report"
    __table_args__ = (UniqueConstraint("task_id", name="uq_market_report_task"),)

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    report_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    schema_version: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    report_hash: Mapped[str] = mapped_column(String(64), index=True)
    report_payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MarketMetricBatchRecord(TenantAuditRecord):
    """一次宏观市场指标上传及其数据范围、来源和审核状态。"""

    __tablename__ = "market_metric_batch"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "market",
            "category",
            "keyword",
            "period_start",
            "period_end",
            "source_name",
            "data_version",
            name="uq_market_metric_batch_scope_version",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_market_metric_batch_period",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'disabled')",
            name="ck_market_metric_batch_status",
        ),
        Index(
            "ix_market_metric_batch_scope_lookup",
            "tenant_id",
            "platform",
            "market",
            "category",
            "status",
            "period_end",
        ),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(255), index=True)
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    methodology: Mapped[str] = mapped_column(Text)
    license_or_authorization: Mapped[str] = mapped_column(Text)
    data_version: Mapped[str] = mapped_column(String(64))
    original_file_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_file_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending_review", index=True
    )
    uploaded_by: Mapped[str] = mapped_column(String(64), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_codes: Mapped[list[str]] = mapped_column(JSON, default=list)


class MarketMetricObservationRecord(TenantAuditRecord):
    """上传批次中的一条宏观市场指标观测值。"""

    __tablename__ = "market_metric_observation"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "metric_code",
            name="uq_market_metric_observation_batch_code",
        ),
        CheckConstraint(
            "status IN ('available', 'unavailable', 'partial', 'stale', 'conflict')",
            name="ck_market_metric_observation_status",
        ),
        CheckConstraint(
            "value_kind IN ('direct', 'derived')",
            name="ck_market_metric_observation_value_kind",
        ),
        CheckConstraint(
            "(value_kind = 'direct' AND formula_code IS NULL AND formula_version IS NULL "
            "AND calculated_at IS NULL) OR "
            "(value_kind = 'derived' AND formula_code IS NOT NULL "
            "AND formula_version IS NOT NULL AND calculated_at IS NOT NULL)",
            name="ck_market_metric_observation_derivation",
        ),
        CheckConstraint(
            "comparison_period_end IS NULL OR comparison_period_start IS NOT NULL",
            name="ck_market_metric_observation_comparison_start",
        ),
        CheckConstraint(
            "comparison_period_start IS NULL OR comparison_period_end IS NOT NULL",
            name="ck_market_metric_observation_comparison_end",
        ),
        CheckConstraint(
            "comparison_period_end IS NULL OR comparison_period_end >= comparison_period_start",
            name="ck_market_metric_observation_comparison_period",
        ),
        Index(
            "ix_market_metric_observation_lookup",
            "tenant_id",
            "metric_code",
            "status",
            "source_timestamp",
        ),
    )

    batch_id: Mapped[str] = mapped_column(
        ForeignKey("market_metric_batch.id", ondelete="CASCADE"), index=True
    )
    metric_code: Mapped[str] = mapped_column(String(64), index=True)
    value_kind: Mapped[str] = mapped_column(String(16), index=True)
    value: Mapped[Decimal | None] = mapped_column(
        Numeric(28, 6), nullable=True
    )
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="available", index=True
    )
    reason_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    methodology: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    growth_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comparison_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comparison_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    formula_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    formula_version: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    source_observation_ids: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )
    calculated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CollectionRunRecord(TenantAuditRecord):
    __tablename__ = "collection_run"

    task_id: Mapped[str] = mapped_column(String(64), index=True)
    keyword: Mapped[str] = mapped_column(String(255), index=True)
    requested_count: Mapped[int] = mapped_column(Integer)
    actual_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    stop_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    adapter_version: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProductSnapshotRecord(TenantAuditRecord):
    __tablename__ = "product_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "platform",
            "product_id",
            name="uq_product_snapshot_run_platform_product",
        ),
    )

    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_run.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(32), index=True)
    product_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3))
    sales_display: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sales_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sales_value_type: Mapped[str] = mapped_column(String(32))
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot_ref: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    data_status: Mapped[str] = mapped_column(String(32), index=True)

class ReviewSnapshotRecord(TenantAuditRecord):
    __tablename__ = "review_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "collection_run_id",
            "platform",
            "review_id",
            name="uq_review_snapshot_run_platform_review",
        ),
    )

    # 本条评论属于哪一次采集
    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_run.id", ondelete="CASCADE"), index=True,
    )

    # 评论所属平台与市场
    platform: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(32), index=True)

    # 评论自身及所属商品
    review_id: Mapped[str] = mapped_column(String(128), index=True)
    product_id: Mapped[str] = mapped_column(String(128), index=True)

    # 评论正文
    content: Mapped[str] = mapped_column(Text)

    # 评论原始属性
    rating: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    review_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_purchase: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    helpful_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 后续评论分析可能产生的字段
    sentiment: Mapped[str | None] = mapped_column(String(32),nullable=True)
    themes: Mapped[list[str]] = mapped_column(JSON, default=list)

    # 数据来源与时间信息
    source_ref: Mapped[str] = mapped_column(Text)
    source_snapshot_ref: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 数据质量状态
    data_status: Mapped[str] = mapped_column(String(32), index=True)


class EvidenceReferenceRecord(TenantAuditRecord):
    __tablename__ = "evidence_reference"

    collection_run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_run.id", ondelete="CASCADE"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    data_level: Mapped[str] = mapped_column(String(16))
    data_source: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    product_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    review_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    query_range: Mapped[dict] = mapped_column(JSON)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tool_call_id: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_ref: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    data_version: Mapped[str] = mapped_column(String(128))
    sample_scope: Mapped[dict] = mapped_column(JSON)


class ApprovalRecord(TenantAuditRecord):
    __tablename__ = "approval"

    task_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    result_hash: Mapped[str] = mapped_column(String(64))
    approver_id: Mapped[str] = mapped_column(String(64), index=True)
    approver_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class UserAccountRecord(Base):
    __tablename__ = "user_account"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(96))
    password_hash: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class CaptchaChallengeRecord(Base):
    __tablename__ = "captcha_challenge"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    target_x: Mapped[int] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    login_consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthSessionRecord(Base):
    __tablename__ = "auth_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
