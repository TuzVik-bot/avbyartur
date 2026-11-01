"""Add opt-in messenger links to listings.

Revision ID: 0027_listing_contact_channels
Revises: 0026_dealer_click_events
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_listing_contact_channels"
down_revision = "0026_dealer_click_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("telegram_contact_url", sa.String(length=320), nullable=True))
    op.add_column("listings", sa.Column("viber_contact_url", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "viber_contact_url")
    op.drop_column("listings", "telegram_contact_url")
