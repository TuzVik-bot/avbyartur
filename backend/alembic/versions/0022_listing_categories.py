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


def _scalar_int(statement: str) -> int:
    return int(op.get_bind().execute(sa.text(statement)).scalar_one())


def _ambiguous_legacy_listings() -> int:
    """Count rows that cannot be proven to be historical car-form listings.

    Before this revision, every known API and dealer-feed path used the car
    form. A row with no car-form evidence may have been written outside those
    paths, so migration must stop for an operator review instead of guessing.
    """

    return _scalar_int(
        """
        SELECT count(*) FROM listings
        WHERE category_code IS NULL
          AND make_id IS NULL AND model_id IS NULL
          AND NULLIF(btrim(COALESCE(manual_make, '')), '') IS NULL
          AND NULLIF(btrim(COALESCE(manual_model, '')), '') IS NULL
          AND year IS NULL AND mileage_km IS NULL
          AND fuel IS NULL AND transmission IS NULL AND drive IS NULL
          AND body_type_id IS NULL AND body_variant_id IS NULL AND modification_id IS NULL
          AND engine_volume_l IS NULL AND power_hp IS NULL AND vin IS NULL
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("listings"):
        if "category_code" not in _columns("listings"):
            op.add_column(
                "listings",
                sa.Column("category_code", sa.String(length=32), nullable=True),
            )
        ambiguous_count = _ambiguous_legacy_listings()
        if ambiguous_count:
            raise RuntimeError(
                f"Refusing to classify {ambiguous_count} ambiguous legacy listings as cars. "
                "Export their IDs for review, assign a confirmed category, then rerun the migration."
            )
        # Known historical API and dealer-feed paths use the passenger-car
        # form. This update only classifies rows carrying that form's evidence.
        # It does not change IDs or related rows (photos, messages, owner,
        # status, or address).
        op.execute(sa.text("UPDATE listings SET category_code = 'cars' WHERE category_code IS NULL"))
        op.alter_column("listings", "category_code", nullable=False, server_default="cars")
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
    if inspector.has_table("listings"):
        non_car_count = _scalar_int("SELECT count(*) FROM listings WHERE category_code <> 'cars'")
        detail_count = _scalar_int("SELECT count(*) FROM listing_category_details") if inspector.has_table("listing_category_details") else 0
        if non_car_count or detail_count:
            raise RuntimeError(
                "Refusing a lossy category downgrade. Preserve listings.category_code and "
                "listing_category_details in a backup/export, remove category data only with "
                "an approved migration plan, then rerun downgrade."
            )
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
