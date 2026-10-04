"""Add the saved-search notification outbox and in-app notifications.

Revision ID: 0009_notification_outbox
Revises: 0008_saved_searches
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009_notification_outbox"
down_revision = "0008_saved_searches"
branch_labels = None
depends_on = None


def _create_outbox() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("channel IN ('web', 'email')", name="ck_notification_outbox_channel"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'delivered', 'failed', 'unsupported')",
            name="ck_notification_outbox_status",
        ),
        sa.ForeignKeyConstraint(["saved_search_id"], ["saved_searches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),
    )
    op.create_index(
        "ix_notification_outbox_claim",
        "notification_outbox",
        ["status", "available_at", "created_at", "id"],
    )
    op.create_index("ix_notification_outbox_user_created", "notification_outbox", ["user_id", "created_at", "id"])
    op.create_index("ix_notification_outbox_saved_search_id", "notification_outbox", ["saved_search_id"])
    op.create_index("ix_notification_outbox_listing_id", "notification_outbox", ["listing_id"])


def _create_notifications() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outbox_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["outbox_id"], ["notification_outbox.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["saved_search_id"], ["saved_searches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outbox_id", name="uq_user_notification_outbox"),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_saved_search_id", "user_notifications", ["saved_search_id"])
    op.create_index("ix_user_notifications_listing_id", "user_notifications", ["listing_id"])
    op.create_index("ix_user_notifications_user_created", "user_notifications", ["user_id", "created_at", "id"])


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    # A database created directly from the current metadata already contains
    # both tables.  This keeps the 0001 -> 0009 migration path idempotent while
    # still adding them to installations that were upgraded from 0008.
    if "notification_outbox" not in tables:
        _create_outbox()
    if "user_notifications" not in tables:
        _create_notifications()


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "user_notifications" in tables:
        op.drop_index("ix_user_notifications_user_created", table_name="user_notifications")
        op.drop_index("ix_user_notifications_listing_id", table_name="user_notifications")
        op.drop_index("ix_user_notifications_saved_search_id", table_name="user_notifications")
        op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
        op.drop_table("user_notifications")
    if "notification_outbox" in tables:
        op.drop_index("ix_notification_outbox_listing_id", table_name="notification_outbox")
        op.drop_index("ix_notification_outbox_saved_search_id", table_name="notification_outbox")
        op.drop_index("ix_notification_outbox_user_created", table_name="notification_outbox")
        op.drop_index("ix_notification_outbox_claim", table_name="notification_outbox")
        op.drop_table("notification_outbox")
