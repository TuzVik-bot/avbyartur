"""Versioned notification templates and approved SEO/legal documents.

Revision ID: 0016_managed_content
Revises: 0015_billing
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016_managed_content"
down_revision = "0015_billing"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "managed_content" not in existing:
        op.create_table("managed_content",
                        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("kind", sa.String(32), nullable=False),
                        sa.Column("key", sa.String(100), nullable=False), sa.Column("payload", JSONB(), nullable=False),
                        sa.Column("status", sa.String(16), nullable=False), sa.Column("revision", sa.Integer(), nullable=False),
                        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
                        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                        sa.UniqueConstraint("kind", "key", name="uq_managed_content_kind_key"),
                        sa.CheckConstraint("kind IN ('notification_template', 'seo_page', 'legal_document')", name="ck_managed_content_kind"),
                        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_managed_content_status"),
                        sa.CheckConstraint("revision >= 1", name="ck_managed_content_revision"))
    if "managed_content_versions" not in existing:
        op.create_table("managed_content_versions",
                        sa.Column("id", sa.Uuid(), primary_key=True),
                        sa.Column("content_id", sa.Uuid(), sa.ForeignKey("managed_content.id", ondelete="RESTRICT"), nullable=False),
                        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("payload", JSONB(), nullable=False),
                        sa.Column("status", sa.String(16), nullable=False),
                        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
                        sa.Column("reason", sa.String(1000), nullable=False),
                        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                        sa.UniqueConstraint("content_id", "revision", name="uq_managed_content_version"),
                        sa.CheckConstraint("revision >= 1", name="ck_managed_content_version_revision"),
                        sa.CheckConstraint("status IN ('draft', 'published')", name="ck_managed_content_version_status"))
    if "ix_managed_content_versions_content_id" not in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("managed_content_versions")}:
        op.create_index("ix_managed_content_versions_content_id", "managed_content_versions", ["content_id"])


def downgrade():
    for table in ("managed_content_versions", "managed_content"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Refusing to discard managed content history")
    op.drop_table("managed_content_versions")
    op.drop_table("managed_content")
