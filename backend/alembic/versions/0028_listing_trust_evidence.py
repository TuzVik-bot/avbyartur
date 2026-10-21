"""Persist revision-bound moderator verified listing evidence.

Revision ID: 0028_listing_trust_evidence
Revises: 0027_listing_contact_channels
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_listing_trust_evidence"
down_revision = "0027_listing_contact_channels"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table) if item.get("name")}


def _create_missing_indexes() -> None:
    existing = _indexes("listing_trust_evidence")
    if "ix_listing_trust_evidence_listing_id" not in existing:
        op.create_index("ix_listing_trust_evidence_listing_id", "listing_trust_evidence", ["listing_id"])
    if "ix_listing_trust_listing_revision" not in existing:
        op.create_index("ix_listing_trust_listing_revision", "listing_trust_evidence", ["listing_id", "checked_revision", "removed_at"])


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("listing_trust_evidence"):
        _create_missing_indexes()
        return
    op.create_table(
        "listing_trust_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("checked_revision", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(240), nullable=False),
        sa.Column("checked_at", sa.Date(), nullable=False),
        sa.Column("scope", sa.String(240), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("length(trim(label)) > 0", name="ck_listing_trust_label_nonempty"),
        sa.CheckConstraint("length(trim(summary)) > 0", name="ck_listing_trust_summary_nonempty"),
        sa.CheckConstraint("length(trim(source)) > 0", name="ck_listing_trust_source_nonempty"),
        sa.CheckConstraint("length(trim(scope)) > 0", name="ck_listing_trust_scope_nonempty"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["removed_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_missing_indexes()


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("listing_trust_evidence"):
        return
    existing = _indexes("listing_trust_evidence")
    if "ix_listing_trust_listing_revision" in existing:
        op.drop_index("ix_listing_trust_listing_revision", table_name="listing_trust_evidence")
    if "ix_listing_trust_evidence_listing_id" in existing:
        op.drop_index("ix_listing_trust_evidence_listing_id", table_name="listing_trust_evidence")
    op.drop_table("listing_trust_evidence")
