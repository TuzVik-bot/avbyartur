"""Track dealer feed conflict and missing-row policy.

Revision ID: 0021_dealer_feed_policy
Revises: 0020_catalog_requests
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_dealer_feed_policy"
down_revision = "0020_catalog_requests"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    feed_columns = _columns("dealer_feeds")
    if feed_columns:
        if "manual_conflict_policy" not in feed_columns:
            op.add_column(
                "dealer_feeds",
                sa.Column("manual_conflict_policy", sa.String(length=16), server_default="review", nullable=False),
            )
        if "missing_retirement_enabled" not in feed_columns:
            op.add_column(
                "dealer_feeds",
                sa.Column("missing_retirement_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
            )
        if "missing_retirement_delay_hours" not in feed_columns:
            op.add_column(
                "dealer_feeds",
                sa.Column("missing_retirement_delay_hours", sa.Integer(), server_default="168", nullable=False),
            )
        constraints = {item["name"] for item in sa.inspect(op.get_bind()).get_check_constraints("dealer_feeds")}
        if "ck_dealer_feed_manual_conflict_policy" not in constraints:
            op.create_check_constraint(
                "ck_dealer_feed_manual_conflict_policy",
                "dealer_feeds",
                "manual_conflict_policy IN ('review', 'feed_wins')",
            )
        if "ck_dealer_feed_missing_retirement_delay_hours" not in constraints:
            op.create_check_constraint(
                "ck_dealer_feed_missing_retirement_delay_hours",
                "dealer_feeds",
                "missing_retirement_delay_hours BETWEEN 1 AND 8760",
            )

    key_columns = _columns("dealer_external_listing_keys")
    if key_columns:
        additions = (
            ("last_applied_revision", sa.Integer(), True),
            ("last_applied_listing_digest", sa.String(length=64), True),
            ("missing_since", sa.DateTime(timezone=True), True),
            ("missing_snapshot_digest", sa.String(length=64), True),
            ("missing_listing_revision", sa.Integer(), True),
            ("missing_confirmed_at", sa.DateTime(timezone=True), True),
        )
        for name, type_, nullable in additions:
            if name not in key_columns:
                op.add_column("dealer_external_listing_keys", sa.Column(name, type_, nullable=nullable))
        if "missing_confirmed_by" not in key_columns:
            op.add_column(
                "dealer_external_listing_keys",
                sa.Column("missing_confirmed_by", sa.Uuid(), nullable=True),
            )
            op.create_foreign_key(
                "fk_dealer_external_listing_keys_missing_confirmed_by_users",
                "dealer_external_listing_keys",
                "users",
                ["missing_confirmed_by"],
                ["id"],
                ondelete="SET NULL",
            )
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("dealer_external_listing_keys")}
        if "ix_dealer_external_listing_keys_missing_since" not in indexes:
            op.create_index(
                "ix_dealer_external_listing_keys_missing_since",
                "dealer_external_listing_keys",
                ["feed_id", "missing_since"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("dealer_external_listing_keys"):
        indexes = {item["name"] for item in inspector.get_indexes("dealer_external_listing_keys")}
        if "ix_dealer_external_listing_keys_missing_since" in indexes:
            op.drop_index("ix_dealer_external_listing_keys_missing_since", table_name="dealer_external_listing_keys")
        fks = {item["name"] for item in inspector.get_foreign_keys("dealer_external_listing_keys")}
        if "fk_dealer_external_listing_keys_missing_confirmed_by_users" in fks:
            op.drop_constraint(
                "fk_dealer_external_listing_keys_missing_confirmed_by_users",
                "dealer_external_listing_keys",
                type_="foreignkey",
            )
        columns = _columns("dealer_external_listing_keys")
        for name in (
            "missing_confirmed_by", "missing_confirmed_at", "missing_listing_revision",
            "missing_snapshot_digest", "missing_since", "last_applied_listing_digest", "last_applied_revision",
        ):
            if name in columns:
                op.drop_column("dealer_external_listing_keys", name)

    if inspector.has_table("dealer_feeds"):
        constraints = {item["name"] for item in inspector.get_check_constraints("dealer_feeds")}
        if "ck_dealer_feed_missing_retirement_delay_hours" in constraints:
            op.drop_constraint("ck_dealer_feed_missing_retirement_delay_hours", "dealer_feeds", type_="check")
        if "ck_dealer_feed_manual_conflict_policy" in constraints:
            op.drop_constraint("ck_dealer_feed_manual_conflict_policy", "dealer_feeds", type_="check")
        columns = _columns("dealer_feeds")
        for name in ("missing_retirement_delay_hours", "missing_retirement_enabled", "manual_conflict_policy"):
            if name in columns:
                op.drop_column("dealer_feeds", name)
