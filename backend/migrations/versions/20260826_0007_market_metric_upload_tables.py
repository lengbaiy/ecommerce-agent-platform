"""Add uploadable macro market metric tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260826_0007"
down_revision: str | None = "20260825_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def _remove_empty_unversioned_tables() -> None:
    """接管 create_all 在 0007 执行前误建的空表。"""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    batch_exists = inspector.has_table("market_metric_batch")
    observation_exists = inspector.has_table("market_metric_observation")
    if not batch_exists and not observation_exists:
        return
    if batch_exists != observation_exists:
        raise RuntimeError(
            "market metric schema is partially present; manual reconciliation is required"
        )
    batch_count = connection.scalar(
        sa.text("SELECT COUNT(*) FROM market_metric_batch")
    )
    observation_count = connection.scalar(
        sa.text("SELECT COUNT(*) FROM market_metric_observation")
    )
    if batch_count or observation_count:
        raise RuntimeError(
            "unversioned market metric tables contain data; migration stopped to protect it"
        )
    op.drop_table("market_metric_observation")
    op.drop_table("market_metric_batch")


def upgrade() -> None:
    _remove_empty_unversioned_tables()
    op.create_table(
        "market_metric_batch",
        *_tenant_columns(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("category", sa.String(255), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_description", sa.Text(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column("license_or_authorization", sa.Text(), nullable=False),
        sa.Column("data_version", sa.String(64), nullable=False),
        sa.Column("original_file_ref", sa.Text(), nullable=True),
        sa.Column("original_file_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("uploaded_by", sa.String(64), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("review_codes", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
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
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_market_metric_batch_period",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'disabled')",
            name="ck_market_metric_batch_status",
        ),
    )
    for column in (
        "tenant_id",
        "trace_id",
        "platform",
        "market",
        "category",
        "keyword",
        "period_end",
        "source_type",
        "source_timestamp",
        "original_file_sha256",
        "status",
        "uploaded_by",
        "reviewed_by",
    ):
        op.create_index(
            f"ix_market_metric_batch_{column}",
            "market_metric_batch",
            [column],
        )
    op.create_index(
        "ix_market_metric_batch_scope_lookup",
        "market_metric_batch",
        ["tenant_id", "platform", "market", "category", "status", "period_end"],
    )

    op.create_table(
        "market_metric_observation",
        *_tenant_columns(),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("market_metric_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_code", sa.String(64), nullable=False),
        sa.Column("value_kind", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(28, 6), nullable=True),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("growth_type", sa.String(16), nullable=True),
        sa.Column("comparison_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comparison_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("formula_code", sa.String(64), nullable=True),
        sa.Column("formula_version", sa.String(32), nullable=True),
        sa.Column("source_observation_ids", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "batch_id",
            "metric_code",
            name="uq_market_metric_observation_batch_code",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'unavailable', 'partial', 'stale', 'conflict')",
            name="ck_market_metric_observation_status",
        ),
        sa.CheckConstraint(
            "value_kind IN ('direct', 'derived')",
            name="ck_market_metric_observation_value_kind",
        ),
        sa.CheckConstraint(
            "(value_kind = 'direct' AND formula_code IS NULL AND formula_version IS NULL "
            "AND calculated_at IS NULL) OR "
            "(value_kind = 'derived' AND formula_code IS NOT NULL "
            "AND formula_version IS NOT NULL AND calculated_at IS NOT NULL)",
            name="ck_market_metric_observation_derivation",
        ),
        sa.CheckConstraint(
            "comparison_period_end IS NULL OR comparison_period_start IS NOT NULL",
            name="ck_market_metric_observation_comparison_start",
        ),
        sa.CheckConstraint(
            "comparison_period_start IS NULL OR comparison_period_end IS NOT NULL",
            name="ck_market_metric_observation_comparison_end",
        ),
        sa.CheckConstraint(
            "comparison_period_end IS NULL OR comparison_period_end >= comparison_period_start",
            name="ck_market_metric_observation_comparison_period",
        ),
    )
    for column in (
        "tenant_id",
        "trace_id",
        "batch_id",
        "metric_code",
        "value_kind",
        "status",
        "reason_code",
        "source_timestamp",
    ):
        op.create_index(
            f"ix_market_metric_observation_{column}",
            "market_metric_observation",
            [column],
        )
    op.create_index(
        "ix_market_metric_observation_lookup",
        "market_metric_observation",
        ["tenant_id", "metric_code", "status", "source_timestamp"],
    )


def downgrade() -> None:
    op.drop_table("market_metric_observation")
    op.drop_table("market_metric_batch")
