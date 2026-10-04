"""Add stable listing categories and their typed detail storage.

Revision ID: 0022_listing_categories
Revises: 0021_dealer_feed_policy
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_listing_categories"
down_revision = "0021_dealer_feed_policy"
branch_labels = None
depends_on = None


_CATEGORIES = "'cars', 'trucks', 'buses', 'motorcycles', 'special_equipment', 'agricultural_equipment', 'trailers', 'watercraft', 'parts', 'wheels', 'tires'"


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("listings"):
        if "category_code" not in _columns("listings"):
            op.add_column(
                "listings",
                sa.Column("category_code", sa.String(length=32), nullable=False, server_default="cars"),
            )
        # Every historical write path was the passenger-car listing form. This
        # only supplies its compatible default and does not change any listing
        # identifier or relation (photos, messages, owner, status, addresses).
        op.execute(sa.text("UPDATE listings SET category_code = 'cars' WHERE category_code IS NULL"))
        constraints = {item["name"] for item in sa.inspect(bind).get_check_constraints("listings")}
        if "ck_listing_category_code" not in constraints:
            op.create_check_constraint(
                "ck_listing_category_code", "listings", f"category_code IN ({_CATEGORIES})"
            )
        unique_constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("listings")}
        if "uq_listing_id_category_code" not in unique_constraints:
            op.create_unique_constraint("uq_listing_id_category_code", "listings", ["id", "category_code"])

    if not inspector.has_table("listing_category_details"):
        op.create_table(
            "listing_category_details",
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("category_code", sa.String(length=32), nullable=False),
            sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.CheckConstraint(f"category_code IN ({_CATEGORIES})", name="ck_listing_category_details_code"),
            sa.ForeignKeyConstraint(
                ["listing_id", "category_code"],
                ["listings.id", "listings.category_code"],
                name="fk_listing_category_details_listing_category",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("listing_id"),
        )
    else:
        foreign_keys = sa.inspect(bind).get_foreign_keys("listing_category_details")
        has_composite_category_fk = any(
            item["constrained_columns"] == ["listing_id", "category_code"]
            and item["referred_table"] == "listings"
            for item in foreign_keys
        )
        if not has_composite_category_fk:
            for item in foreign_keys:
                if item["constrained_columns"] == ["listing_id"] and item["referred_table"] == "listings" and item["name"]:
                    op.drop_constraint(item["name"], "listing_category_details", type_="foreignkey")
            op.create_foreign_key(
                "fk_listing_category_details_listing_category",
                "listing_category_details",
                "listings",
                ["listing_id", "category_code"],
                ["id", "category_code"],
                ondelete="CASCADE",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("listing_category_details"):
        op.drop_table("listing_category_details")
    if inspector.has_table("listings"):
        constraints = {item["name"] for item in sa.inspect(bind).get_check_constraints("listings")}
        if "ck_listing_category_code" in constraints:
            op.drop_constraint("ck_listing_category_code", "listings", type_="check")
        unique_constraints = {item["name"] for item in inspector.get_unique_constraints("listings")}
        if "uq_listing_id_category_code" in unique_constraints:
            op.drop_constraint("uq_listing_id_category_code", "listings", type_="unique")
        if "category_code" in _columns("listings"):
            op.drop_column("listings", "category_code")
