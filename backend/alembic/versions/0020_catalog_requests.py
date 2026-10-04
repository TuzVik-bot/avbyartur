"""Durable seller requests for missing catalog modifications.

Revision ID: 0020_catalog_requests
Revises: 0019_guest_contact
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020_catalog_requests"
down_revision = "0019_guest_contact"
branch_labels = None
depends_on = None


_TABLE = "catalog_requests"
_INDEXES = (
    (
        "ix_catalog_requests_status_created",
        ["status", "created_at", "id"],
        False,
        None,
    ),
    (
        "ix_catalog_requests_listing_created",
        ["listing_id", "created_at", "id"],
        False,
        None,
    ),
    (
        "uq_catalog_request_pending_listing_digest",
        ["listing_id", "request_digest"],
        True,
        sa.text("status = 'pending'"),
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("actor_id", sa.Uuid(), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("idempotency_payload_digest", sa.String(length=64), nullable=False),
            sa.Column("listing_revision", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("manual_modification_name", sa.String(length=180), nullable=True),
            sa.Column("note", sa.String(length=1200), nullable=True),
            sa.Column("resolved_modification_id", sa.Uuid(), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.Uuid(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'resolved', 'rejected')",
                name="ck_catalog_request_status",
            ),
            sa.CheckConstraint("revision > 0", name="ck_catalog_request_revision_positive"),
            sa.CheckConstraint(
                "length(idempotency_key_hash) = 64",
                name="ck_catalog_request_idempotency_hash_length",
            ),
            sa.CheckConstraint(
                "length(request_digest) = 64",
                name="ck_catalog_request_digest_length",
            ),
            sa.CheckConstraint(
                "length(idempotency_payload_digest) = 64",
                name="ck_catalog_request_idempotency_payload_digest_length",
            ),
            sa.ForeignKeyConstraint(
                ["listing_id"],
                ["listings.id"],
                name="fk_catalog_requests_listing_id_listings",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["actor_id"],
                ["users.id"],
                name="fk_catalog_requests_actor_id_users",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["resolved_modification_id"],
                ["catalog_modifications.id"],
                name="fk_catalog_request_resolved_modification",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["reviewed_by"],
                ["users.id"],
                name="fk_catalog_requests_reviewed_by_users",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_catalog_requests"),
            sa.UniqueConstraint(
                "actor_id",
                "idempotency_key_hash",
                name="uq_catalog_request_actor_idempotency_hash",
            ),
        )
    else:
        columns = {column["name"] for column in sa.inspect(bind).get_columns(_TABLE)}
        required = {
            "id",
            "listing_id",
            "actor_id",
            "idempotency_key_hash",
            "request_digest",
            "idempotency_payload_digest",
            "listing_revision",
            "status",
            "revision",
            "snapshot",
            "manual_modification_name",
            "note",
            "resolved_modification_id",
            "review_reason",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "updated_at",
        }
        missing = sorted(required - columns)
        if missing:
            raise RuntimeError(
                "catalog_requests already exists without the complete metadata table: "
                + ", ".join(missing)
            )

    existing_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes(_TABLE)
    }
    for name, columns, unique, predicate in _INDEXES:
        if name in existing_indexes:
            continue
        options = {"unique": unique}
        if predicate is not None:
            options["postgresql_where"] = predicate
        op.create_index(name, _TABLE, columns, **options)


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(_TABLE):
        op.drop_table(_TABLE)
