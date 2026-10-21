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


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    existing = _columns("listings")
    if "telegram_contact_url" not in existing:
        op.add_column("listings", sa.Column("telegram_contact_url", sa.String(length=320), nullable=True))
    if "viber_contact_url" not in existing:
        op.add_column("listings", sa.Column("viber_contact_url", sa.String(length=320), nullable=True))


def downgrade() -> None:
    existing = _columns("listings")
    if "viber_contact_url" in existing:
        op.drop_column("listings", "viber_contact_url")
    if "telegram_contact_url" in existing:
        op.drop_column("listings", "telegram_contact_url")
