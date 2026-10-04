"""Add optimistic-concurrency revisions to companies and reports.

Revision ID: 0007_company_report_revisions
Revises: 0006_unbounded_generation_labels
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_company_report_revisions"
down_revision = "0006_unbounded_generation_labels"
branch_labels = None
depends_on = None


def _add_revision_column(table_name: str) -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    if "revision" in columns:
        return
    op.add_column(
        table_name,
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.alter_column(table_name, "revision", server_default=None)


def upgrade() -> None:
    _add_revision_column("companies")
    _add_revision_column("reports")


def downgrade() -> None:
    for table_name in ("reports", "companies"):
        columns = {
            column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
        }
        if "revision" in columns:
            op.drop_column(table_name, "revision")
