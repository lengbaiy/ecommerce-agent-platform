"""Create market intelligence persistence tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260817_0002"
down_revision: str | None = "20260813_0001"
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
    # ---------------------------------------------------------
    # collection_run
    # ---------------------------------------------------------
    op.create_table(
        "collection_run",
        *tenant_columns(),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("actual_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stop_reason", sa.String(length=128), nullable=True),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    create_tenant_indexes("collection_run")

    for column in (
        "task_id",
        "keyword",
        "status",
    ):
        op.create_index(
            f"ix_collection_run_{column}",
            "collection_run",
            [column],
        )

    # ---------------------------------------------------------
    # product_snapshot
    # ---------------------------------------------------------
    op.create_table(
        "product_snapshot",
        *tenant_columns(),
        sa.Column(
            "collection_run_id",
            sa.String(length=36),
            sa.ForeignKey(
                "collection_run.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column(
            "price",
            sa.Numeric(precision=18, scale=4),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sales_display", sa.String(length=128), nullable=True),
        sa.Column("sales_value", sa.Integer(), nullable=True),
        sa.Column(
            "sales_value_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("shop_name", sa.String(length=255), nullable=True),
        sa.Column(
            "rating",
            sa.Numeric(precision=18, scale=4),
            nullable=True,
        ),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "source_snapshot_ref",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "source_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ingest_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "data_status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "collection_run_id",
            "platform",
            "product_id",
            name="uq_product_snapshot_run_platform_product",
        ),
    )

    create_tenant_indexes("product_snapshot")

    for column in (
        "collection_run_id",
        "platform",
        "market",
        "product_id",
        "category",
        "source_type",
        "data_status",
    ):
        op.create_index(
            f"ix_product_snapshot_{column}",
            "product_snapshot",
            [column],
        )

    # ---------------------------------------------------------
    # evidence_reference
    # ---------------------------------------------------------
    op.create_table(
        "evidence_reference",
        *tenant_columns(),
        sa.Column(
            "collection_run_id",
            sa.String(length=36),
            sa.ForeignKey(
                "collection_run.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "data_level",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "data_source",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column(
            "query_range",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "source_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ingest_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "tool_call_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "snapshot_ref",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "data_version",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "sample_scope",
            sa.JSON(),
            nullable=False,
        ),
    )

    create_tenant_indexes("evidence_reference")

    for column in (
        "collection_run_id",
        "evidence_type",
        "platform",
        "product_id",
        "tool_call_id",
        "sha256",
    ):
        op.create_index(
            f"ix_evidence_reference_{column}",
            "evidence_reference",
            [column],
        )


def downgrade() -> None:
    op.drop_table("evidence_reference")
    op.drop_table("product_snapshot")
    op.drop_table("collection_run")