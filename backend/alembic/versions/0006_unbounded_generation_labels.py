"""Keep imported generation labels intact.

Revision ID: 0006_unbounded_generation_labels
Revises: 0005_drom_trim_provenance
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_unbounded_generation_labels"
down_revision = "0005_drom_trim_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "catalog_generations",
        "name",
        existing_type=sa.String(length=180),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "listings",
        "generation_name_snapshot",
        existing_type=sa.String(length=180),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    has_long_labels = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM catalog_generations WHERE char_length(name) > 180 "
                "UNION ALL "
                "SELECT 1 FROM listings "
                "WHERE char_length(generation_name_snapshot) > 180"
                ")"
            )
        )
        .scalar_one()
    )
    if has_long_labels:
        raise RuntimeError(
            "Cannot downgrade generation labels while values exceed 180 characters"
        )

    op.alter_column(
        "listings",
        "generation_name_snapshot",
        existing_type=sa.Text(),
        type_=sa.String(length=180),
        existing_nullable=True,
    )
    op.alter_column(
        "catalog_generations",
        "name",
        existing_type=sa.Text(),
        type_=sa.String(length=180),
        existing_nullable=False,
    )
