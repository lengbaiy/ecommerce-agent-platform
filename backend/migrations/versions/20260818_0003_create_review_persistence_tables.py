"""Create review persistence tables.

Revision ID: 20260818_0003
Revises: 20260817_0002
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260818_0003"
down_revision: str | None = "20260817_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1. 创建评论快照表
    # --------------------------------------------------
    op.create_table(
        "review_snapshot",

        # TenantAuditRecord
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        # ReviewSnapshotRecord
        sa.Column(
            "collection_run_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "market",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "review_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "rating",
            sa.Numeric(precision=18, scale=4),
            nullable=True,
        ),
        sa.Column(
            "review_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "verified_purchase",
            sa.Boolean(),
            nullable=True,
        ),
        sa.Column(
            "helpful_count",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "sentiment",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "themes",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "source_ref",
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
            "data_status",
            sa.String(length=32),
            nullable=False,
        ),

        # constraints
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_run.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_run_id",
            "platform",
            "review_id",
            name="uq_review_snapshot_run_platform_review",
        ),
    )

    # --------------------------------------------------
    # 2. ReviewSnapshotRecord 对应索引
    # --------------------------------------------------
    op.create_index(
        "ix_review_snapshot_tenant_id",
        "review_snapshot",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_trace_id",
        "review_snapshot",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_collection_run_id",
        "review_snapshot",
        ["collection_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_platform",
        "review_snapshot",
        ["platform"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_market",
        "review_snapshot",
        ["market"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_review_id",
        "review_snapshot",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_product_id",
        "review_snapshot",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_snapshot_data_status",
        "review_snapshot",
        ["data_status"],
        unique=False,
    )

    # --------------------------------------------------
    # 3. evidence_reference 增加 review_id
    # --------------------------------------------------
    op.add_column(
        "evidence_reference",
        sa.Column(
            "review_id",
            sa.String(length=128),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_evidence_reference_review_id",
        "evidence_reference",
        ["review_id"],
        unique=False,
    )


def downgrade() -> None:
    # --------------------------------------------------
    # 1. 撤销 evidence_reference.review_id
    # --------------------------------------------------
    op.drop_index(
        "ix_evidence_reference_review_id",
        table_name="evidence_reference",
    )

    op.drop_column(
        "evidence_reference",
        "review_id",
    )

    # --------------------------------------------------
    # 2. 删除 review_snapshot
    # --------------------------------------------------
    op.drop_index(
        "ix_review_snapshot_data_status",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_product_id",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_review_id",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_market",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_platform",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_collection_run_id",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_trace_id",
        table_name="review_snapshot",
    )
    op.drop_index(
        "ix_review_snapshot_tenant_id",
        table_name="review_snapshot",
    )

    op.drop_table("review_snapshot")