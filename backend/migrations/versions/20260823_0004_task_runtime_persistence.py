"""Add durable task runtime, graph checkpoints and market reports."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0004"
down_revision: str | None = "20260818_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(96), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("agent_task", column)
    op.create_index("ix_agent_task_claimed_by", "agent_task", ["claimed_by"])
    op.create_index("ix_agent_task_lease_expires_at", "agent_task", ["lease_expires_at"])

    for column in (
        sa.Column("step_name", sa.String(64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("tool_call", column)
    op.create_unique_constraint("uq_tool_call_idempotency_key", "tool_call", ["idempotency_key"])

    for column in (
        sa.Column("state_version", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("agent_step", column)

    op.create_table(
        "graph_checkpoint",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("graph_name", sa.String(96), nullable=False),
        sa.Column("current_step", sa.String(96), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("state_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "task_id",
            "graph_name",
            "state_version",
            name="uq_checkpoint_task_graph_version",
        ),
    )
    for column in ("tenant_id", "trace_id", "task_id", "graph_name"):
        op.create_index(f"ix_graph_checkpoint_{column}", "graph_checkpoint", [column])

    op.create_table(
        "market_intelligence_report",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("report_id", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("report_hash", sa.String(64), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", name="uq_market_report_task"),
        sa.UniqueConstraint("report_id", name="uq_market_report_id"),
    )
    report_indexes = (
        "tenant_id",
        "trace_id",
        "task_id",
        "report_id",
        "status",
        "report_hash",
    )
    for column in report_indexes:
        op.create_index(
            f"ix_market_intelligence_report_{column}",
            "market_intelligence_report",
            [column],
        )


def downgrade() -> None:
    op.drop_table("market_intelligence_report")
    op.drop_table("graph_checkpoint")
    op.drop_constraint("uq_tool_call_idempotency_key", "tool_call", type_="unique")
    for column in ("finished_at", "started_at", "error_code", "state_version"):
        op.drop_column("agent_step", column)
    tool_columns = (
        "finished_at",
        "started_at",
        "response_payload",
        "request_payload",
        "idempotency_key",
        "attempt",
        "step_name",
    )
    for column in tool_columns:
        op.drop_column("tool_call", column)
    op.drop_index("ix_agent_task_lease_expires_at", table_name="agent_task")
    op.drop_index("ix_agent_task_claimed_by", table_name="agent_task")
    task_columns = (
        "completed_at",
        "result_hash",
        "heartbeat_at",
        "lease_expires_at",
        "claimed_by",
        "cancel_requested_at",
    )
    for column in task_columns:
        op.drop_column("agent_task", column)
