"""Create tenant-scoped task and audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def tenant_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def create_tenant_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index(f"ix_{table}_trace_id", table, ["trace_id"])


def upgrade() -> None:
    op.create_table(
        "agent_task",
        *tenant_columns(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("current_step", sa.String(length=96), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("approval_hash", sa.String(length=64), nullable=True),
        sa.Column("approver_id", sa.String(length=64), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    create_tenant_indexes("agent_task")
    for column in ("user_id", "status", "intent", "approval_status"):
        op.create_index(f"ix_agent_task_{column}", "agent_task", [column])

    op.create_table(
        "agent_step",
        *tenant_columns(),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("step_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
    )
    create_tenant_indexes("agent_step")
    for column in ("task_id", "step_name", "status"):
        op.create_index(f"ix_agent_step_{column}", "agent_step", [column])

    op.create_table(
        "tool_call",
        *tenant_columns(),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )
    create_tenant_indexes("tool_call")
    for column in ("task_id", "tool_name", "status"):
        op.create_index(f"ix_tool_call_{column}", "tool_call", [column])

    op.create_table(
        "approval",
        *tenant_columns(),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("approver_id", sa.String(length=64), nullable=False),
        sa.Column("approver_roles", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    create_tenant_indexes("approval")
    for column in ("task_id", "action", "approver_id"):
        op.create_index(f"ix_approval_{column}", "approval", [column])

    op.create_table(
        "user_account",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=96), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "username", name="uq_user_tenant_username"),
    )
    op.create_index("ix_user_account_tenant_id", "user_account", ["tenant_id"])
    op.create_index("ix_user_account_username", "user_account", ["username"])

    op.create_table(
        "captcha_challenge",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("target_x", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("login_consumed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_captcha_challenge_expires_at", "captcha_challenge", ["expires_at"])

    op.create_table(
        "auth_session",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_auth_session_tenant_id", "auth_session", ["tenant_id"])
    op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])
    op.create_index("ix_auth_session_expires_at", "auth_session", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_session")
    op.drop_table("captcha_challenge")
    op.drop_table("user_account")
    op.drop_table("approval")
    op.drop_table("tool_call")
    op.drop_table("agent_step")
    op.drop_table("agent_task")
