"""Add anonymous dealer click events for company analytics.

Revision ID: 0024_dealer_click_events
Revises: 0023_saved_search_batches
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_dealer_click_events"
down_revision = "0023_saved_search_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("dealer_click_events"):
        return
    op.create_table(
        "dealer_click_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="listing_detail", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dealer_click_events_company_id", "dealer_click_events", ["company_id"])
    op.create_index("ix_dealer_click_events_listing_id", "dealer_click_events", ["listing_id"])
    op.create_index("ix_dealer_click_events_company_created", "dealer_click_events", ["company_id", "created_at"])
    op.create_index("ix_dealer_click_events_listing_created", "dealer_click_events", ["listing_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_dealer_click_events_listing_created", table_name="dealer_click_events")
    op.drop_index("ix_dealer_click_events_company_created", table_name="dealer_click_events")
    op.drop_index("ix_dealer_click_events_listing_id", table_name="dealer_click_events")
    op.drop_index("ix_dealer_click_events_company_id", table_name="dealer_click_events")
    op.drop_table("dealer_click_events")
