"""Add subscription start tracking and saved-search notification batches.

Revision ID: 0024_saved_search_batches
Revises: 0023_managed_articles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024_saved_search_batches"
down_revision = "0023_managed_articles"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _columns(table: str) -> dict[str, dict]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return {}
    return {column["name"]: column for column in inspector.get_columns(table)}


def _check_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_check_constraints(table) if item.get("name")}


def _ensure_check(table: str, name: str, expression: str) -> None:
    if name in _check_names(table):
        op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def _ensure_nullable(table: str, column: str, nullable: bool) -> None:
    existing = _columns(table).get(column)
    if existing is not None and existing["nullable"] != nullable:
        op.alter_column(table, column, existing_type=existing["type"], nullable=nullable)


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_indexes(table)} if inspector.has_table(table) else set()
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    if "subscription_started_at" not in _columns("saved_searches"):
        op.add_column(
            "saved_searches",
            sa.Column("subscription_started_at", sa.DateTime(timezone=True), nullable=True),
        )
    # Existing active preferences begin at this release boundary. Legacy
    # weekly subscriptions retain a NULL marker so their already-queued jobs
    # continue under the prior weekly behavior. No listing matches are
    # backfilled.
    if _table_exists("saved_searches"):
        op.execute(
            sa.text(
                "UPDATE saved_searches SET subscription_started_at = CURRENT_TIMESTAMP "
                "WHERE subscription_started_at IS NULL "
                "AND notifications_enabled IS TRUE AND notification_frequency <> 'weekly'"
            )
        )

    if _table_exists("notification_outbox"):
        _ensure_check(
            "notification_outbox",
            "ck_notification_outbox_status",
            "status IN ('queued', 'running', 'delivered', 'failed', 'unsupported', 'cancelled')",
        )
        _ensure_nullable("notification_outbox", "listing_id", True)
        _ensure_check(
            "notification_outbox",
            "ck_notification_outbox_source",
            "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
            "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL)",
        )

    if not _table_exists("saved_search_notification_batches"):
        op.create_table(
            "saved_search_notification_batches",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("saved_search_id", sa.Uuid(), nullable=False),
            sa.Column("channel", sa.String(length=20), nullable=False),
            sa.Column("period", sa.Date(), nullable=False),
            sa.Column("outbox_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("channel IN ('web', 'email')", name="ck_saved_search_notification_batch_channel"),
            sa.ForeignKeyConstraint(["saved_search_id"], ["saved_searches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["outbox_id"], ["notification_outbox.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("outbox_id", name="uq_saved_search_notification_batch_outbox"),
            sa.UniqueConstraint(
                "saved_search_id", "channel", "period",
                name="uq_saved_search_notification_batch_period",
            ),
        )
    _ensure_index(
        "saved_search_notification_batches",
        "ix_saved_search_notification_batches_saved_search_id",
        ["saved_search_id"],
    )
    _ensure_index(
        "saved_search_notification_batches",
        "ix_saved_search_notification_batches_outbox",
        ["outbox_id"],
    )

    if not _table_exists("saved_search_notification_matches"):
        op.create_table(
            "saved_search_notification_matches",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("saved_search_id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("listing_revision", sa.Integer(), nullable=False),
            sa.Column("outbox_id", sa.Uuid(), nullable=True),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("url", sa.String(length=2048), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["saved_search_id"], ["saved_searches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["outbox_id"], ["notification_outbox.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("saved_search_id", "listing_id", name="uq_saved_search_notification_match"),
        )
    for name, columns in (
        ("ix_saved_search_notification_matches_saved_search_id", ["saved_search_id"]),
        ("ix_saved_search_notification_matches_listing_id", ["listing_id"]),
        ("ix_saved_search_notification_matches_outbox_id", ["outbox_id"]),
        ("ix_saved_search_notification_matches_outbox", ["outbox_id", "created_at", "id"]),
    ):
        _ensure_index("saved_search_notification_matches", name, columns)

    if _table_exists("user_notifications"):
        _ensure_nullable("user_notifications", "listing_id", True)
        _ensure_check(
            "user_notifications",
            "ck_user_notification_source",
            "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
            "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL)",
        )
        if "listings" not in _columns("user_notifications"):
            op.add_column(
                "user_notifications",
                sa.Column(
                    "listings",
                    postgresql.JSONB(astext_type=sa.Text()),
                    server_default=sa.text("'[]'::jsonb"),
                    nullable=False,
                ),
            )
        if "total_count" not in _columns("user_notifications"):
            op.add_column(
                "user_notifications",
                sa.Column("total_count", sa.Integer(), server_default="1", nullable=False),
            )
        _ensure_check("user_notifications", "ck_user_notification_total_count", "total_count >= 1")


def downgrade() -> None:
    bind = op.get_bind()
    has_cancelled = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM notification_outbox WHERE status = 'cancelled')")
    ).scalar_one()
    if has_cancelled:
        raise RuntimeError("Refusing to downgrade while cancelled notification batches exist.")
    has_batches = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notification_outbox WHERE listing_id IS NULL) "
            "OR EXISTS (SELECT 1 FROM user_notifications WHERE listing_id IS NULL OR total_count > 1) "
            "OR EXISTS (SELECT 1 FROM saved_search_notification_batches)"
        )
    ).scalar_one()
    if has_batches:
        raise RuntimeError(
            "Refusing to downgrade while notification batches exist. Export or remove batch data first."
        )

    op.drop_constraint("ck_notification_outbox_status", "notification_outbox", type_="check")
    op.create_check_constraint(
        "ck_notification_outbox_status",
        "notification_outbox",
        "status IN ('queued', 'running', 'delivered', 'failed', 'unsupported')",
    )
    op.drop_constraint("ck_user_notification_total_count", "user_notifications", type_="check")
    op.drop_column("user_notifications", "total_count")
    op.drop_column("user_notifications", "listings")
    op.drop_constraint("ck_user_notification_source", "user_notifications", type_="check")
    op.create_check_constraint(
        "ck_user_notification_source",
        "user_notifications",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL)",
    )
    op.alter_column("user_notifications", "listing_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index("ix_saved_search_notification_batches_outbox", table_name="saved_search_notification_batches")
    op.drop_table("saved_search_notification_batches")

    op.drop_index("ix_saved_search_notification_matches_outbox", table_name="saved_search_notification_matches")
    op.drop_table("saved_search_notification_matches")

    op.drop_constraint("ck_notification_outbox_source", "notification_outbox", type_="check")
    op.create_check_constraint(
        "ck_notification_outbox_source",
        "notification_outbox",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL)",
    )
    op.alter_column("notification_outbox", "listing_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("saved_searches", "subscription_started_at")
