"""Persist geography row provenance and catalog import source snapshots.

Revision ID: 0004_geography_provenance
Revises: 0003_catalog_provenance
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_geography_provenance"
down_revision = "0003_catalog_provenance"
branch_labels = None
depends_on = None

PROVENANCE_COLUMNS = (
    ("location_regions", "source_metadata"),
    ("location_cities", "source_metadata"),
    ("catalog_imports", "source_metadata"),
)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table_name, column_name in PROVENANCE_COLUMNS:
        if column_name not in _columns(table_name):
            op.add_column(table_name, sa.Column(column_name, postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for table_name, column_name in reversed(PROVENANCE_COLUMNS):
        if column_name in _columns(table_name):
            op.drop_column(table_name, column_name)
