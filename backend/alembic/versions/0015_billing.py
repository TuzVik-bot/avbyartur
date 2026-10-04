"""Add owner-configured billing, payment attempts, callback history and promotions.

Revision ID: 0015_billing
Revises: 0014_runtime_settings
"""

import sqlalchemy as sa

from alembic import op


revision = "0015_billing"
down_revision = "0014_runtime_settings"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _names(kind: str, table_name: str) -> set[str | None]:
    inspector = _inspector()
    if kind == "unique":
        rows = inspector.get_unique_constraints(table_name)
    elif kind == "check":
        rows = inspector.get_check_constraints(table_name)
    else:
        raise ValueError(kind)
    return {row.get("name") for row in rows}


def _foreign_keys(table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(row.get("constrained_columns") or ()),
            str(row.get("referred_table") or ""),
            tuple(row.get("referred_columns") or ()),
        )
        for row in _inspector().get_foreign_keys(table_name)
    }


def _validate_existing(
    table_name: str,
    *,
    columns: set[str],
    unique: tuple[str, ...],
    checks: tuple[str, ...],
    foreign_keys: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...],
) -> None:
    inspector = _inspector()
    actual_columns = {row["name"] for row in inspector.get_columns(table_name)}
    actual_unique = _names("unique", table_name)
    actual_checks = _names("check", table_name)
    actual_foreign = _foreign_keys(table_name)
    missing = []
    if columns - actual_columns:
        missing.append(f"columns={sorted(columns - actual_columns)}")
    if set(unique) - actual_unique:
        missing.append(f"unique={sorted(set(unique) - actual_unique)}")
    if set(checks) - actual_checks:
        missing.append(f"checks={sorted(set(checks) - actual_checks)}")
    if set(foreign_keys) - actual_foreign:
        missing.append(f"foreign_keys={sorted(set(foreign_keys) - actual_foreign)}")
    if missing:
        raise RuntimeError(f"{table_name} exists with an incompatible billing schema ({'; '.join(missing)})")


def _ensure_indexes(table_name: str, indexes: tuple[tuple[str, list[str]], ...]) -> None:
    existing = {row["name"] for row in _inspector().get_indexes(table_name)}
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, table_name, columns)


def upgrade() -> None:
    tables = _tables()
    if "billing_tariffs" not in tables:
        op.create_table(
            "billing_tariffs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("service_code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("duration_days", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("service_code IN ('bump', 'highlight', 'top', 'dealer_package')", name="ck_billing_tariff_service_code"),
            sa.CheckConstraint("amount > 0", name="ck_billing_tariff_amount_positive"),
            sa.CheckConstraint("currency IN ('BYN', 'USD')", name="ck_billing_tariff_currency"),
            sa.CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_billing_tariff_duration"),
            sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_billing_tariff_status"),
            sa.CheckConstraint("revision >= 1", name="ck_billing_tariff_revision"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_billing_tariff_code"),
        )
    else:
        _validate_existing(
            "billing_tariffs",
            columns={"id", "code", "service_code", "name", "amount", "currency", "duration_days", "status", "revision", "created_at", "updated_at"},
            unique=("uq_billing_tariff_code",),
            checks=("ck_billing_tariff_service_code", "ck_billing_tariff_amount_positive", "ck_billing_tariff_currency", "ck_billing_tariff_duration", "ck_billing_tariff_status", "ck_billing_tariff_revision"),
            foreign_keys=(),
        )
    _ensure_indexes(
        "billing_tariffs",
        (("ix_billing_tariffs_service_code", ["service_code"]), ("ix_billing_tariffs_status", ["status"]), ("ix_billing_tariffs_available", ["status", "service_code", "code"])),
    )

    tables = _tables()
    if "billing_orders" not in tables:
        op.create_table(
            "billing_orders",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=True),
            sa.Column("company_id", sa.Uuid(), nullable=True),
            sa.Column("tariff_id", sa.Uuid(), nullable=False),
            sa.Column("service_code", sa.String(length=32), nullable=False),
            sa.Column("tariff_code", sa.String(length=80), nullable=False),
            sa.Column("tariff_revision", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("duration_days", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("provider_reference", sa.String(length=180), nullable=True),
            sa.Column("idempotency_key_digest", sa.String(length=64), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("(service_code = 'dealer_package' AND company_id IS NOT NULL AND listing_id IS NULL) OR (service_code <> 'dealer_package' AND listing_id IS NOT NULL AND company_id IS NULL)", name="ck_billing_order_target"),
            sa.CheckConstraint("service_code IN ('bump', 'highlight', 'top', 'dealer_package')", name="ck_billing_order_service_code"),
            sa.CheckConstraint("amount > 0", name="ck_billing_order_amount_positive"),
            sa.CheckConstraint("currency IN ('BYN', 'USD')", name="ck_billing_order_currency"),
            sa.CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_billing_order_duration"),
            sa.CheckConstraint("status IN ('pending', 'paid', 'failed', 'cancelled', 'expired')", name="ck_billing_order_status"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["tariff_id"], ["billing_tariffs.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "idempotency_key_digest", name="uq_billing_order_user_idempotency"),
            sa.UniqueConstraint("provider", "provider_reference", name="uq_billing_order_provider_reference"),
        )
    else:
        _validate_existing(
            "billing_orders",
            columns={"id", "user_id", "listing_id", "company_id", "tariff_id", "service_code", "tariff_code", "tariff_revision", "amount", "currency", "duration_days", "provider", "provider_reference", "idempotency_key_digest", "request_digest", "status", "expires_at", "paid_at", "created_at", "updated_at"},
            unique=("uq_billing_order_user_idempotency", "uq_billing_order_provider_reference"),
            checks=("ck_billing_order_target", "ck_billing_order_service_code", "ck_billing_order_amount_positive", "ck_billing_order_currency", "ck_billing_order_duration", "ck_billing_order_status"),
            foreign_keys=((('user_id',), "users", ('id',)), (('listing_id',), "listings", ('id',)), (('company_id',), "companies", ('id',)), (('tariff_id',), "billing_tariffs", ('id',))),
        )
    _ensure_indexes(
        "billing_orders",
        (("ix_billing_orders_user_id", ["user_id"]), ("ix_billing_orders_listing_id", ["listing_id"]), ("ix_billing_orders_company_id", ["company_id"]), ("ix_billing_orders_tariff_id", ["tariff_id"]), ("ix_billing_orders_status", ["status"]), ("ix_billing_orders_expires_at", ["expires_at"]), ("ix_billing_orders_user_created", ["user_id", "created_at", "id"]), ("ix_billing_orders_target_service_status", ["listing_id", "company_id", "service_code", "status"])),
    )

    tables = _tables()
    if "payment_attempts" not in tables:
        op.create_table(
            "payment_attempts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("order_id", sa.Uuid(), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("provider_reference", sa.String(length=180), nullable=True),
            sa.Column("checkout_url", sa.Text(), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("attempt_number >= 1", name="ck_payment_attempt_number_positive"),
            sa.CheckConstraint("amount > 0", name="ck_payment_attempt_amount_positive"),
            sa.CheckConstraint("currency IN ('BYN', 'USD')", name="ck_payment_attempt_currency"),
            sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'cancelled')", name="ck_payment_attempt_status"),
            sa.ForeignKeyConstraint(["order_id"], ["billing_orders.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_id", "attempt_number", name="uq_payment_attempt_order_number"),
            sa.UniqueConstraint("provider", "provider_reference", name="uq_payment_attempt_provider_reference"),
        )
    else:
        _validate_existing(
            "payment_attempts",
            columns={"id", "order_id", "attempt_number", "provider", "provider_reference", "checkout_url", "amount", "currency", "status", "created_at", "updated_at"},
            unique=("uq_payment_attempt_order_number", "uq_payment_attempt_provider_reference"),
            checks=("ck_payment_attempt_number_positive", "ck_payment_attempt_amount_positive", "ck_payment_attempt_currency", "ck_payment_attempt_status"),
            foreign_keys=((('order_id',), "billing_orders", ('id',)),),
        )
    _ensure_indexes("payment_attempts", (("ix_payment_attempts_order_id", ["order_id"]), ("ix_payment_attempts_status", ["status"]), ("ix_payment_attempt_order_created", ["order_id", "created_at"])))

    tables = _tables()
    if "payment_callback_events" not in tables:
        op.create_table(
            "payment_callback_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("provider_event_id", sa.String(length=180), nullable=False),
            sa.Column("order_id", sa.Uuid(), nullable=False),
            sa.Column("provider_reference", sa.String(length=180), nullable=False),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("payment_status", sa.String(length=16), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("payload_sha256", sa.String(length=64), nullable=False),
            sa.Column("outcome", sa.String(length=16), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("amount > 0", name="ck_payment_callback_amount_positive"),
            sa.CheckConstraint("currency IN ('BYN', 'USD')", name="ck_payment_callback_currency"),
            sa.CheckConstraint("payment_status IN ('succeeded', 'failed', 'cancelled')", name="ck_payment_callback_status"),
            sa.CheckConstraint("outcome IN ('applied', 'ignored')", name="ck_payment_callback_outcome"),
            sa.ForeignKeyConstraint(["order_id"], ["billing_orders.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "provider_event_id", name="uq_payment_callback_provider_event"),
        )
    else:
        _validate_existing(
            "payment_callback_events",
            columns={"id", "provider", "provider_event_id", "order_id", "provider_reference", "event_type", "payment_status", "amount", "currency", "payload_sha256", "outcome", "received_at"},
            unique=("uq_payment_callback_provider_event",),
            checks=("ck_payment_callback_amount_positive", "ck_payment_callback_currency", "ck_payment_callback_status", "ck_payment_callback_outcome"),
            foreign_keys=((('order_id',), "billing_orders", ('id',)),),
        )
    _ensure_indexes("payment_callback_events", (("ix_payment_callback_events_order_id", ["order_id"]), ("ix_payment_callback_order_received", ["order_id", "received_at"])))

    tables = _tables()
    if "listing_promotions" not in tables:
        op.create_table(
            "listing_promotions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("order_id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=True),
            sa.Column("company_id", sa.Uuid(), nullable=True),
            sa.Column("service_code", sa.String(length=32), nullable=False),
            sa.Column("tariff_code", sa.String(length=80), nullable=False),
            sa.Column("tariff_revision", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("duration_days", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("(service_code = 'dealer_package' AND company_id IS NOT NULL AND listing_id IS NULL) OR (service_code <> 'dealer_package' AND listing_id IS NOT NULL AND company_id IS NULL)", name="ck_listing_promotion_target"),
            sa.CheckConstraint("service_code IN ('bump', 'highlight', 'top', 'dealer_package')", name="ck_listing_promotion_service_code"),
            sa.CheckConstraint("amount > 0", name="ck_listing_promotion_amount_positive"),
            sa.CheckConstraint("currency IN ('BYN', 'USD')", name="ck_listing_promotion_currency"),
            sa.CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_listing_promotion_duration"),
            sa.CheckConstraint("status IN ('active', 'expired', 'cancelled')", name="ck_listing_promotion_status"),
            sa.ForeignKeyConstraint(["order_id"], ["billing_orders.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_id", name="uq_listing_promotion_order"),
        )
    else:
        _validate_existing(
            "listing_promotions",
            columns={"id", "order_id", "listing_id", "company_id", "service_code", "tariff_code", "tariff_revision", "amount", "currency", "duration_days", "status", "starts_at", "ends_at", "created_at"},
            unique=("uq_listing_promotion_order",),
            checks=("ck_listing_promotion_target", "ck_listing_promotion_service_code", "ck_listing_promotion_amount_positive", "ck_listing_promotion_currency", "ck_listing_promotion_duration", "ck_listing_promotion_status"),
            foreign_keys=((('order_id',), "billing_orders", ('id',)), (('listing_id',), "listings", ('id',)), (('company_id',), "companies", ('id',))),
        )
    _ensure_indexes(
        "listing_promotions",
        (("ix_listing_promotions_order_id", ["order_id"]), ("ix_listing_promotions_listing_id", ["listing_id"]), ("ix_listing_promotions_company_id", ["company_id"]), ("ix_listing_promotions_status", ["status"]), ("ix_listing_promotions_starts_at", ["starts_at"]), ("ix_listing_promotions_ends_at", ["ends_at"]), ("ix_listing_promotion_listing_window", ["listing_id", "service_code", "status", "ends_at"]), ("ix_listing_promotion_company_window", ["company_id", "service_code", "status", "ends_at"])),
    )

    # ORM guards protect ordinary application writes; this database trigger
    # also makes the order snapshot immutable for SQL scripts and future code.
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
    op.execute("DROP TRIGGER IF EXISTS trg_billing_order_snapshot_immutable ON billing_orders")
    op.execute(
        "CREATE TRIGGER trg_billing_order_snapshot_immutable "
        "BEFORE UPDATE ON billing_orders "
        "FOR EACH ROW EXECUTE FUNCTION guard_billing_order_snapshot_update()"
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for table_name in (
        "payment_callback_events",
        "listing_promotions",
        "payment_attempts",
        "billing_orders",
        "billing_tariffs",
    ):
        if table_name in tables and bind.scalar(sa.text(f"SELECT count(*) FROM {table_name}")):
            raise RuntimeError(f"Refusing to remove billing data from {table_name}")
    for table_name in (
        "payment_callback_events",
        "listing_promotions",
        "payment_attempts",
        "billing_orders",
        "billing_tariffs",
    ):
        if table_name in tables:
            op.drop_table(table_name)
    op.execute("DROP FUNCTION IF EXISTS guard_billing_order_snapshot_update()")
