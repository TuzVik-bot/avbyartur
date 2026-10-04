"""Add owner-scoped saved searches and notification preferences.

Revision ID: 0008_saved_searches
Revises: 0007_company_report_revisions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_saved_searches"
down_revision = "0007_company_report_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "saved_searches" in inspector.get_table_names():
        # 0001 creates the current metadata as a bootstrap convenience. A
        # database upgraded from that revision can therefore already have
        # this table; keep this revision safe in both migration paths.
        indexes = {index["name"] for index in inspector.get_indexes("saved_searches")}
        if "ix_saved_searches_user_id" not in indexes:
            op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])
        if "ix_saved_searches_user_created" not in indexes:
            op.create_index(
                "ix_saved_searches_user_created",
                "saved_searches",
                ["user_id", "created_at", "id"],
            )
        return

    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("search_url", sa.String(length=2048), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notification_channel", sa.String(length=20), nullable=True),
        sa.Column("notification_frequency", sa.String(length=20), server_default="daily", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'paused')", name="ck_saved_search_status"),
        sa.CheckConstraint(
            "notification_channel IS NULL OR notification_channel IN ('email', 'web')",
            name="ck_saved_search_notification_channel",
        ),
        sa.CheckConstraint(
            "notification_frequency IN ('instant', 'daily', 'weekly')",
            name="ck_saved_search_notification_frequency",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])
    op.create_index(
        "ix_saved_searches_user_created",
        "saved_searches",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_searches_user_created", table_name="saved_searches")
    op.drop_index("ix_saved_searches_user_id", table_name="saved_searches")
    op.drop_table("saved_searches")
