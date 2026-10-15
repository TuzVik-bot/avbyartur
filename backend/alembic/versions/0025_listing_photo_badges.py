"""Add administrator assigned photo labels.

Revision ID: 0025_listing_photo_badges
Revises: 0024_saved_search_batches
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_listing_photo_badges"
down_revision = "0024_saved_search_batches"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("listings")}
    if "photo_badges" in columns:
        return
    op.add_column("listings", sa.Column("photo_badges", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    op.drop_column("listings", "photo_badges")
