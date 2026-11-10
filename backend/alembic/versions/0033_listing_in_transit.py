"""Add seller-declared vehicle transit status.

Revision ID: 0033_listing_in_transit
Revises: 0032_listing_price_hist
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_listing_in_transit"
down_revision = "0032_listing_price_hist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("listings")}
    if "in_transit" in columns:
        return
    op.add_column("listings", sa.Column("in_transit", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM listings WHERE in_transit IS TRUE)")).scalar():
        raise RuntimeError("Cannot remove in_transit while listings are marked in transit")
    op.drop_column("listings", "in_transit")
