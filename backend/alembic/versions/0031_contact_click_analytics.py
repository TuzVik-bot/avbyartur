"""Add privacy-limited contact click events.

Revision ID: 0031_contact_click_analytics
Revises: 0030_dealer_reviews_and_logo
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_contact_click_analytics"
down_revision = "0030_dealer_reviews_and_logo"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table) if item.get("name")}


def _create_missing_indexes() -> None:
    existing = _indexes("contact_click_events")
    if "ix_contact_click_events_listing_id" not in existing:
        op.create_index("ix_contact_click_events_listing_id", "contact_click_events", ["listing_id"])
    if "ix_contact_click_listing_created" not in existing:
        op.create_index("ix_contact_click_listing_created", "contact_click_events", ["listing_id", "created_at"])


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("contact_click_events"):
        _create_missing_indexes()
        return
    op.create_table(
        "contact_click_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("dedup_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("channel IN ('phone', 'telegram', 'viber', 'internal_chat')", name="ck_contact_click_channel"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_id", name="uq_contact_click_dedup"),
    )
    _create_missing_indexes()


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("contact_click_events"):
        return
    existing = _indexes("contact_click_events")
    if "ix_contact_click_listing_created" in existing:
        op.drop_index("ix_contact_click_listing_created", table_name="contact_click_events")
    if "ix_contact_click_events_listing_id" in existing:
        op.drop_index("ix_contact_click_events_listing_id", table_name="contact_click_events")
    op.drop_table("contact_click_events")
