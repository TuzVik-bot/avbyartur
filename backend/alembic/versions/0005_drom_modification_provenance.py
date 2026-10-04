"""Persist per-trim source provenance for Drom catalog records.

Revision ID: 0005_drom_trim_provenance
Revises: 0004_geography_provenance
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_drom_trim_provenance"
down_revision = "0004_geography_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("catalog_modifications")
    }
    if "source_metadata" not in columns:
        op.add_column(
            "catalog_modifications",
            sa.Column("source_metadata", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("catalog_modifications")
    }
    if "source_metadata" in columns:
        op.drop_column("catalog_modifications", "source_metadata")
