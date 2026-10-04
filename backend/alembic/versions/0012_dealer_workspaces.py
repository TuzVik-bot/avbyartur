"""Add dealer teams, import feeds, and external listing identities.

Revision ID: 0012_dealer_workspaces
Revises: 0011_sms_otp_auth
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "0012_dealer_workspaces"
down_revision = "0011_sms_otp_auth"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _constraints(table_name: str) -> set[str | None]:
    inspector = sa.inspect(op.get_bind())
    names = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints(table_name)
    }
    names.update(constraint.get("name") for constraint in inspector.get_check_constraints(table_name))
    names.update(constraint.get("name") for constraint in inspector.get_foreign_keys(table_name))
    return names


def upgrade() -> None:
    tables = _tables()
    if "business_hours" not in _columns("companies"):
        op.add_column("companies", sa.Column("business_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    if "dealer_team_members" not in tables:
        op.create_table(
            "dealer_team_members",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("granted_by", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("role IN ('admin', 'seller', 'viewer')", name="ck_dealer_team_role"),
            sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_dealer_team_status"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "user_id", name="uq_dealer_team_company_user"),
        )
    for name, columns in (
        ("ix_dealer_team_members_company_id", ["company_id"]),
        ("ix_dealer_team_members_user_id", ["user_id"]),
        ("ix_dealer_team_members_status", ["status"]),
        ("ix_dealer_team_user_status", ["user_id", "status"]),
    ):
        if name not in _indexes("dealer_team_members"):
            op.create_index(name, "dealer_team_members", columns)

    tables = _tables()
    if "dealer_feeds" not in tables:
        op.create_table(
            "dealer_feeds",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("format", sa.String(length=8), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("field_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("api_token_digest", sa.String(length=64), nullable=True),
            sa.Column("api_token_prefix", sa.String(length=12), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("format IN ('csv', 'xml', 'api')", name="ck_dealer_feed_format"),
            sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_dealer_feed_status"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("api_token_digest", name="uq_dealer_feed_api_token_digest"),
        )
    for name, columns in (
        ("ix_dealer_feeds_company_id", ["company_id"]),
        ("ix_dealer_feeds_status", ["status"]),
        ("ix_dealer_feeds_api_token_digest", ["api_token_digest"]),
    ):
        if name not in _indexes("dealer_feeds"):
            op.create_index(name, "dealer_feeds", columns)

    tables = _tables()
    if "feed_import_runs" not in tables:
        op.create_table(
            "feed_import_runs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("feed_id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("initiated_by", sa.Uuid(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=120), nullable=False),
            sa.Column("payload_digest", sa.String(length=64), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("source_filename", sa.String(length=180), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False),
            sa.Column("applied_rows", sa.Integer(), nullable=False),
            sa.Column("rejected_rows", sa.Integer(), nullable=False),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("status IN ('preview', 'succeeded', 'partial', 'failed')", name="ck_feed_import_status"),
            sa.CheckConstraint("total_rows >= 0 AND applied_rows >= 0 AND rejected_rows >= 0", name="ck_feed_import_counts_nonnegative"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["feed_id"], ["dealer_feeds.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["initiated_by"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("feed_id", "idempotency_key", name="uq_feed_import_idempotency"),
        )
    for name, columns in (
        ("ix_feed_import_runs_feed_id", ["feed_id"]),
        ("ix_feed_import_runs_company_id", ["company_id"]),
        ("ix_feed_import_runs_status", ["status"]),
        ("ix_feed_import_company_created", ["company_id", "created_at"]),
    ):
        if name not in _indexes("feed_import_runs"):
            op.create_index(name, "feed_import_runs", columns)

    tables = _tables()
    if "feed_import_rows" not in tables:
        op.create_table(
            "feed_import_rows",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("dealer_external_id", sa.String(length=120), nullable=True),
            sa.Column("listing_id", sa.Uuid(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("action", sa.String(length=16), nullable=True),
            sa.Column("error_code", sa.String(length=80), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("field_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("row_number > 0", name="ck_feed_import_row_number_positive"),
            sa.CheckConstraint("status IN ('preview', 'draft', 'submitted', 'unchanged', 'rejected')", name="ck_feed_import_row_status"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["feed_import_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "row_number", name="uq_feed_import_run_row"),
        )
    for name, columns in (
        ("ix_feed_import_rows_run_id", ["run_id"]),
        ("ix_feed_import_rows_listing_id", ["listing_id"]),
    ):
        if name not in _indexes("feed_import_rows"):
            op.create_index(name, "feed_import_rows", columns)

    tables = _tables()
    if "dealer_external_listing_keys" not in tables:
        op.create_table(
            "dealer_external_listing_keys",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("feed_id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("dealer_external_id", sa.String(length=120), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("last_applied_hash", sa.String(length=64), nullable=False),
            sa.Column("source_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("length(dealer_external_id) > 0", name="ck_dealer_external_id_nonempty"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["feed_id"], ["dealer_feeds.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("feed_id", "dealer_external_id", name="uq_dealer_feed_external_id"),
            sa.UniqueConstraint("listing_id", name="uq_dealer_external_listing_listing"),
        )
    for name, columns in (
        ("ix_dealer_external_listing_keys_feed_id", ["feed_id"]),
        ("ix_dealer_external_listing_keys_company_id", ["company_id"]),
    ):
        if name not in _indexes("dealer_external_listing_keys"):
            op.create_index(name, "dealer_external_listing_keys", columns)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "feed_import_runs" in tables:
        count = bind.execute(sa.text("SELECT count(*) FROM feed_import_runs")).scalar_one()
        if count:
            raise RuntimeError("Refusing to remove dealer feed import history")
    if "dealer_external_listing_keys" in tables:
        op.drop_table("dealer_external_listing_keys")
    if "feed_import_rows" in tables:
        op.drop_table("feed_import_rows")
    if "feed_import_runs" in tables:
        op.drop_table("feed_import_runs")
    if "dealer_feeds" in tables:
        op.drop_table("dealer_feeds")
    if "dealer_team_members" in tables:
        op.drop_table("dealer_team_members")
    if "business_hours" in _columns("companies"):
        op.drop_column("companies", "business_hours")
