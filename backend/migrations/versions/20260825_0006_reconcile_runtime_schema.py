"""Reconcile runtime tables with the current ORM metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_0006"
down_revision: str | None = "20260824_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _require_no_rows(connection: sa.Connection, table: str, reason: str) -> None:
    count = connection.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one()
    if count:
        raise RuntimeError(f"Cannot migrate {table}: {reason}; found {count} rows.")


def _require_no_nulls(connection: sa.Connection, table: str, column: str) -> None:
    count = connection.execute(
        sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"Cannot make {table}.{column} non-nullable; found {count} null rows."
        )


def _has_table(connection: sa.Connection, table: str) -> bool:
    return sa.inspect(connection).has_table(table)


def _has_column(connection: sa.Connection, table: str, column: str) -> bool:
    return column in {
        item["name"] for item in sa.inspect(connection).get_columns(table)
    }


def upgrade() -> None:
    connection = op.get_bind()

    # Fresh databases already use the current snapshot schema. Legacy tables are
    # reconciled only when their identifying table/column is present.
    if _has_table(connection, "raw_source_snapshot"):
        _require_no_rows(
            connection,
            "raw_source_snapshot",
            "legacy snapshots require archiving",
        )
        op.drop_table("raw_source_snapshot")

    op.drop_constraint(
        "uq_market_report_id",
        "market_intelligence_report",
        type_="unique",
    )
    op.drop_index(
        "ix_market_intelligence_report_report_id",
        table_name="market_intelligence_report",
    )
    op.create_index(
        "ix_market_intelligence_report_report_id",
        "market_intelligence_report",
        ["report_id"],
        unique=True,
    )

    if _has_column(connection, "product_snapshot", "source_page_sha256"):
        _upgrade_legacy_product_schema(connection)


def _upgrade_legacy_product_schema(connection: sa.Connection) -> None:
    _require_no_nulls(connection, "collection_run", "task_id")
    op.alter_column(
        "collection_run",
        "task_id",
        existing_type=sa.String(36),
        type_=sa.String(64),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "collection_run",
        "keyword",
        existing_type=sa.String(100),
        type_=sa.String(255),
        existing_nullable=False,
    )
    op.alter_column(
        "collection_run",
        "stop_reason",
        existing_type=sa.String(64),
        type_=sa.String(128),
        existing_nullable=True,
    )
    op.alter_column(
        "collection_run",
        "parser_version",
        existing_type=sa.String(64),
        existing_nullable=False,
        nullable=True,
    )

    for column in (
        sa.Column("market", sa.String(32), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("rating", sa.Numeric(18, 4), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("source_snapshot_ref", sa.Text(), nullable=True),
    ):
        op.add_column("product_snapshot", column)

    connection.execute(
        sa.text(
            """
            UPDATE product_snapshot AS product
            SET market = evidence.query_range ->> 'market'
            FROM evidence_reference AS evidence
            WHERE evidence.collection_run_id = product.collection_run_id
              AND evidence.product_id = product.product_id
              AND product.market IS NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE product_snapshot
            SET source_ref = COALESCE(source_url, source_page_snapshot_ref),
                source_snapshot_ref = source_page_snapshot_ref
            """
        )
    )
    for column in ("market", "source_ref", "source_snapshot_ref"):
        _require_no_nulls(connection, "product_snapshot", column)

    too_long_currency = connection.execute(
        sa.text("SELECT count(*) FROM product_snapshot WHERE length(currency) > 3")
    ).scalar_one()
    too_long_source_type = connection.execute(
        sa.text("SELECT count(*) FROM product_snapshot WHERE length(source_type) > 32")
    ).scalar_one()
    if too_long_currency or too_long_source_type:
        raise RuntimeError("Cannot narrow product_snapshot string columns without data cleanup.")

    op.alter_column(
        "product_snapshot", "market", existing_type=sa.String(32), nullable=False
    )
    op.alter_column(
        "product_snapshot", "source_ref", existing_type=sa.Text(), nullable=False
    )
    op.alter_column(
        "product_snapshot",
        "source_snapshot_ref",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "product_snapshot",
        "price",
        existing_type=sa.Float(),
        type_=sa.Numeric(18, 4),
        existing_nullable=False,
        postgresql_using="price::numeric(18, 4)",
    )
    op.alter_column(
        "product_snapshot",
        "currency",
        existing_type=sa.String(8),
        type_=sa.String(3),
        existing_nullable=False,
    )
    op.alter_column(
        "product_snapshot",
        "sales_display",
        existing_type=sa.String(96),
        type_=sa.String(128),
        existing_nullable=True,
    )
    op.alter_column(
        "product_snapshot",
        "source_url",
        existing_type=sa.Text(),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "product_snapshot",
        "source_type",
        existing_type=sa.String(64),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.create_foreign_key(
        "fk_product_snapshot_collection_run",
        "product_snapshot",
        "collection_run",
        ["collection_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_product_snapshot_source_page_sha256", table_name="product_snapshot")
    for column in ("category", "data_status", "market", "source_type"):
        op.create_index(f"ix_product_snapshot_{column}", "product_snapshot", [column])
    op.drop_column("product_snapshot", "source_page_sha256")
    op.drop_column("product_snapshot", "source_page_snapshot_ref")


def downgrade() -> None:
    connection = op.get_bind()
    _require_no_rows(
        connection,
        "product_snapshot",
        "downgrade would discard current product snapshot fields",
    )

    op.add_column(
        "product_snapshot",
        sa.Column("source_page_snapshot_ref", sa.String(512), nullable=False),
    )
    op.add_column(
        "product_snapshot",
        sa.Column("source_page_sha256", sa.String(64), nullable=False),
    )
    for column in ("source_type", "market", "data_status", "category"):
        op.drop_index(f"ix_product_snapshot_{column}", table_name="product_snapshot")
    op.create_index(
        "ix_product_snapshot_source_page_sha256",
        "product_snapshot",
        ["source_page_sha256"],
    )
    op.drop_constraint(
        "fk_product_snapshot_collection_run", "product_snapshot", type_="foreignkey"
    )
    op.alter_column(
        "product_snapshot",
        "source_type",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    op.alter_column(
        "product_snapshot",
        "source_url",
        existing_type=sa.Text(),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "product_snapshot",
        "sales_display",
        existing_type=sa.String(128),
        type_=sa.String(96),
        existing_nullable=True,
    )
    op.alter_column(
        "product_snapshot",
        "currency",
        existing_type=sa.String(3),
        type_=sa.String(8),
        existing_nullable=False,
    )
    op.alter_column(
        "product_snapshot",
        "price",
        existing_type=sa.Numeric(18, 4),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="price::double precision",
    )
    for column in (
        "source_snapshot_ref",
        "source_ref",
        "review_count",
        "rating",
        "category",
        "brand",
        "market",
    ):
        op.drop_column("product_snapshot", column)

    op.drop_index(
        "ix_market_intelligence_report_report_id",
        table_name="market_intelligence_report",
    )
    op.create_unique_constraint(
        "uq_market_report_id", "market_intelligence_report", ["report_id"]
    )
    op.create_index(
        "ix_market_intelligence_report_report_id",
        "market_intelligence_report",
        ["report_id"],
    )

    op.alter_column(
        "collection_run",
        "parser_version",
        existing_type=sa.String(64),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "collection_run",
        "stop_reason",
        existing_type=sa.String(128),
        type_=sa.String(64),
        existing_nullable=True,
    )
    op.alter_column(
        "collection_run",
        "keyword",
        existing_type=sa.String(255),
        type_=sa.String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "collection_run",
        "task_id",
        existing_type=sa.String(64),
        type_=sa.String(36),
        existing_nullable=False,
        nullable=True,
    )

    op.create_table(
        "raw_source_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_run_id", sa.String(36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_type", sa.String(96), nullable=False),
        sa.Column("adapter_version", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
    )
    for column in ("tenant_id", "trace_id", "collection_run_id", "sha256"):
        op.create_index(f"ix_raw_source_snapshot_{column}", "raw_source_snapshot", [column])
