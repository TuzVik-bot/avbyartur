"""Versioned, non-secret runtime limits.

Revision ID: 0014_runtime_settings
Revises: 0013_identity_delivery
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_runtime_settings"
down_revision = "0013_identity_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "runtime_settings" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "runtime_settings",
            sa.Column("key", sa.String(80), primary_key=True),
            sa.Column("value", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("key IN ('private_listing_quota', 'company_listing_quota', 'saved_search_limit')", name="ck_runtime_setting_key"),
            sa.CheckConstraint("value BETWEEN 1 AND 10000", name="ck_runtime_setting_value"),
            sa.CheckConstraint("revision >= 1", name="ck_runtime_setting_revision"),
        )
    checks = {constraint["name"] for constraint in sa.inspect(op.get_bind()).get_check_constraints("runtime_settings")}
    for name, expression in (
        ("ck_runtime_setting_key", "key IN ('private_listing_quota', 'company_listing_quota', 'saved_search_limit')"),
        ("ck_runtime_setting_value", "value BETWEEN 1 AND 10000"),
        ("ck_runtime_setting_revision", "revision >= 1"),
    ):
        if name not in checks:
            op.create_check_constraint(name, "runtime_settings", expression)


def downgrade() -> None:
    op.drop_table("runtime_settings")
