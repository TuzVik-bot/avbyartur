"""Persist dataset and per-record catalog provenance.

Revision ID: 0003_catalog_provenance
Revises: 0002_manual_city
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_catalog_provenance"
down_revision = "0002_manual_city"
branch_labels = None
depends_on = None

RECORD_TABLES = (
    "catalog_makes",
    "catalog_models",
    "catalog_generations",
    "catalog_body_types",
    "catalog_body_variants",
)


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table_name in RECORD_TABLES:
        if "source_metadata" not in _columns(table_name):
            op.add_column(table_name, sa.Column("source_metadata", postgresql.JSONB(), nullable=True))

    source_columns = _columns("catalog_sources")
    if "license_url" not in source_columns:
        op.add_column("catalog_sources", sa.Column("license_url", sa.Text(), nullable=True))
    if "query_sha256" not in source_columns:
        op.add_column("catalog_sources", sa.Column("query_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    source_columns = _columns("catalog_sources")
    if "query_sha256" in source_columns:
        op.drop_column("catalog_sources", "query_sha256")
    if "license_url" in source_columns:
        op.drop_column("catalog_sources", "license_url")

    for table_name in reversed(RECORD_TABLES):
        if "source_metadata" in _columns(table_name):
            op.drop_column(table_name, "source_metadata")
