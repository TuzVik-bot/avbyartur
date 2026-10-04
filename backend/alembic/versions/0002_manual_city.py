"""Add support for listing locations outside the city catalog.

Revision ID: 0002_manual_city
Revises: 0001_initial
"""
import sqlalchemy as sa

from alembic import op

revision = "0002_manual_city"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial revision builds from current metadata, which may already include this column.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("listings")}
    if "manual_city" not in columns:
        op.add_column("listings", sa.Column("manual_city", sa.String(length=160), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("listings")}
    if "manual_city" in columns:
        op.drop_column("listings", "manual_city")
