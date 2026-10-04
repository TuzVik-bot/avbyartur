"""Complete seller listing fields, view analytics and photo fingerprints.

Revision ID: 0017_listing_completion
Revises: 0016_managed_content
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0017_listing_completion"
down_revision = "0016_managed_content"
branch_labels = None
depends_on = None


LISTING_COLUMNS = (
    ("color", sa.String(length=20)),
    ("customs_status", sa.String(length=24)),
    ("technical_condition", sa.String(length=24)),
    ("body_condition", sa.String(length=24)),
    ("exchange", sa.Boolean()),
    ("bargaining", sa.Boolean()),
    ("credit", sa.Boolean()),
    ("leasing", sa.Boolean()),
    ("equipment", JSONB()),
    ("district", sa.String(length=120)),
    ("call_hours", sa.String(length=120)),
)

LISTING_CHECKS = {
    "ck_listing_color": "color IS NULL OR color IN ('black', 'white', 'gray', 'silver', 'red', 'blue', 'green', 'yellow', 'brown', 'beige', 'orange', 'purple', 'other')",
    "ck_listing_customs_status": "customs_status IS NULL OR customs_status IN ('cleared_rb', 'eaeu_import', 'uncleared', 'unknown')",
    "ck_listing_technical_condition": "technical_condition IS NULL OR technical_condition IN ('good', 'needs_repair', 'non_operational')",
    "ck_listing_body_condition": "body_condition IS NULL OR body_condition IN ('good', 'minor_damage', 'significant_damage', 'repaired')",
}

BILLING_QUOTA_TABLES = ("billing_tariffs", "billing_orders", "listing_promotions")
BILLING_QUOTA_CHECKS = {
    "billing_tariffs": "ck_billing_tariff_listing_quota",
    "billing_orders": "ck_billing_order_listing_quota",
    "listing_promotions": "ck_listing_promotion_listing_quota",
}
BILLING_QUOTA_EXPRESSION = (
    "listing_quota IS NULL OR (service_code = 'dealer_package' AND listing_quota BETWEEN 1 AND 10000)"
)


def _install_billing_order_snapshot_guard() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_billing_order_snapshot_update()
        RETURNS trigger AS $$
        BEGIN
            IF ROW(
                OLD.user_id, OLD.listing_id, OLD.company_id, OLD.tariff_id,
                OLD.service_code, OLD.tariff_code, OLD.tariff_revision,
                OLD.amount, OLD.currency, OLD.duration_days, OLD.listing_quota,
                OLD.provider, OLD.idempotency_key_digest, OLD.request_digest, OLD.expires_at
            ) IS DISTINCT FROM ROW(
                NEW.user_id, NEW.listing_id, NEW.company_id, NEW.tariff_id,
                NEW.service_code, NEW.tariff_code, NEW.tariff_revision,
                NEW.amount, NEW.currency, NEW.duration_days, NEW.listing_quota,
                NEW.provider, NEW.idempotency_key_digest, NEW.request_digest, NEW.expires_at
            ) THEN
                RAISE EXCEPTION 'billing order snapshot fields are immutable';
            END IF;
            IF OLD.provider_reference IS NOT NULL
               AND OLD.provider_reference IS DISTINCT FROM NEW.provider_reference THEN
                RAISE EXCEPTION 'billing order provider reference is immutable once assigned';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_billing_order_snapshot_immutable ON billing_orders")
    op.execute(
        "CREATE TRIGGER trg_billing_order_snapshot_immutable "
        "BEFORE UPDATE ON billing_orders "
        "FOR EACH ROW EXECUTE FUNCTION guard_billing_order_snapshot_update()"
    )


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if "listings" not in inspector.get_table_names():
        raise RuntimeError("listings table is required before 0017_listing_completion")

    existing_columns = {column["name"] for column in inspector.get_columns("listings")}
    for name, column_type in LISTING_COLUMNS:
        if name not in existing_columns:
            op.add_column("listings", sa.Column(name, column_type, nullable=True))

    existing_checks = {item.get("name") for item in _inspector().get_check_constraints("listings")}
    for name, expression in LISTING_CHECKS.items():
        if name not in existing_checks:
            op.create_check_constraint(name, "listings", expression)

    photo_columns = {column["name"] for column in _inspector().get_columns("listing_photos")}
    if "perceptual_hash" not in photo_columns:
        op.add_column("listing_photos", sa.Column("perceptual_hash", sa.String(length=16), nullable=True))

    tables = set(_inspector().get_table_names())
    if "listing_view_events" not in tables:
        op.create_table(
            "listing_view_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        required = {"id", "listing_id", "created_at"}
        view_columns = {column["name"] for column in _inspector().get_columns("listing_view_events")}
        if required - view_columns:
            raise RuntimeError("listing_view_events exists with an incompatible schema")

    indexes = {item["name"] for item in _inspector().get_indexes("listing_view_events")}
    for name, columns in (
        ("ix_listing_view_events_listing_id", ["listing_id"]),
        ("ix_listing_view_events_created_at", ["created_at"]),
        ("ix_listing_view_events_listing_created", ["listing_id", "created_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "listing_view_events", columns)

    # Eight indexed 8-bit bands bound pHash-neighbor lookup. If two 64-bit
    # hashes differ in at most seven bits, at least one band is identical.
    photo_indexes = {item["name"] for item in _inspector().get_indexes("listing_photos")}
    for start in range(1, 17, 2):
        name = f"ix_listing_photo_phash_band_{start:02d}"
        if name not in photo_indexes:
            op.create_index(name, "listing_photos", [sa.text(f"substr(perceptual_hash, {start}, 2)")])

    tables = set(_inspector().get_table_names())
    for table_name in BILLING_QUOTA_TABLES:
        if table_name not in tables:
            raise RuntimeError(f"{table_name} is required before adding dealer package capacity")
        columns = {column["name"] for column in _inspector().get_columns(table_name)}
        if "listing_quota" not in columns:
            op.add_column(table_name, sa.Column("listing_quota", sa.Integer(), nullable=True))
        checks = {item.get("name") for item in _inspector().get_check_constraints(table_name)}
        check_name = BILLING_QUOTA_CHECKS[table_name]
        if check_name not in checks:
            op.create_check_constraint(check_name, table_name, BILLING_QUOTA_EXPRESSION)

    _install_billing_order_snapshot_guard()


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in BILLING_QUOTA_TABLES:
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table_name} WHERE listing_quota IS NOT NULL")):
            raise RuntimeError("Refusing to discard dealer package listing capacity")
    if bind.scalar(sa.text("SELECT count(*) FROM listing_view_events")):
        raise RuntimeError("Refusing to discard listing view history")
    for column in ("color", "customs_status", "technical_condition", "body_condition", "exchange", "bargaining", "credit", "leasing", "equipment", "district", "call_hours"):
        if bind.scalar(sa.text(f"SELECT count(*) FROM listings WHERE {column} IS NOT NULL")):
            raise RuntimeError("Refusing to discard extended listing details")
    if bind.scalar(sa.text("SELECT count(*) FROM listing_photos WHERE perceptual_hash IS NOT NULL")):
        raise RuntimeError("Refusing to discard photo fingerprints")

    for start in range(1, 17, 2):
        op.drop_index(f"ix_listing_photo_phash_band_{start:02d}", table_name="listing_photos")
    op.drop_index("ix_listing_view_events_listing_created", table_name="listing_view_events")
    op.drop_index("ix_listing_view_events_created_at", table_name="listing_view_events")
    op.drop_index("ix_listing_view_events_listing_id", table_name="listing_view_events")
    op.drop_table("listing_view_events")
    op.drop_column("listing_photos", "perceptual_hash")
    for name in reversed(tuple(LISTING_CHECKS)):
        op.drop_constraint(name, "listings", type_="check")
    for name, _column_type in reversed(LISTING_COLUMNS):
        op.drop_column("listings", name)
    for table_name in BILLING_QUOTA_TABLES:
        op.drop_constraint(BILLING_QUOTA_CHECKS[table_name], table_name, type_="check")
        op.drop_column(table_name, "listing_quota")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_billing_order_snapshot_update()
        RETURNS trigger AS $$
        BEGIN
            IF ROW(
                OLD.user_id, OLD.listing_id, OLD.company_id, OLD.tariff_id,
                OLD.service_code, OLD.tariff_code, OLD.tariff_revision,
                OLD.amount, OLD.currency, OLD.duration_days, OLD.provider,
                OLD.idempotency_key_digest, OLD.request_digest, OLD.expires_at
            ) IS DISTINCT FROM ROW(
                NEW.user_id, NEW.listing_id, NEW.company_id, NEW.tariff_id,
                NEW.service_code, NEW.tariff_code, NEW.tariff_revision,
                NEW.amount, NEW.currency, NEW.duration_days, NEW.provider,
                NEW.idempotency_key_digest, NEW.request_digest, NEW.expires_at
            ) THEN
                RAISE EXCEPTION 'billing order snapshot fields are immutable';
            END IF;
            IF OLD.provider_reference IS NOT NULL
               AND OLD.provider_reference IS DISTINCT FROM NEW.provider_reference THEN
                RAISE EXCEPTION 'billing order provider reference is immutable once assigned';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
