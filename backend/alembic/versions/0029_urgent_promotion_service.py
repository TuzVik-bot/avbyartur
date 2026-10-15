"""Allow owner-configured urgent listing promotion.

Revision ID: 0029_urgent_promotion_service
Revises: 0028_listing_trust_evidence
"""

from alembic import op


revision = "0029_urgent_promotion_service"
down_revision = "0028_listing_trust_evidence"
branch_labels = None
depends_on = None

TABLES = (
    ("billing_tariffs", "ck_billing_tariff_service_code", "bump", "highlight", "top", "urgent", "dealer_package"),
    ("billing_orders", "ck_billing_order_service_code", "bump", "highlight", "top", "urgent", "dealer_package"),
    ("listing_promotions", "ck_listing_promotion_service_code", "bump", "highlight", "top", "urgent", "dealer_package"),
)


def _check_sql(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"service_code IN ({quoted})"


def upgrade() -> None:
    for table, name, *values in TABLES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _check_sql(tuple(values)))


def downgrade() -> None:
    for table, name, *values in TABLES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _check_sql(tuple(value for value in values if value != "urgent")))
