"""Add dealer logos and moderated public reviews.

Revision ID: 0030_dealer_reviews_and_logo
Revises: 0029_urgent_promotion_service
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_dealer_reviews_and_logo"
down_revision = "0029_urgent_promotion_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("companies") and "logo_storage_name" not in {column["name"] for column in inspector.get_columns("companies")}:
        op.add_column("companies", sa.Column("logo_storage_name", sa.String(length=64), nullable=True))
    if not inspector.has_table("dealer_reviews"):
        op.create_table(
            "dealer_reviews",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("company_id", sa.Uuid(), nullable=False),
            sa.Column("author_id", sa.Uuid(), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(length=2000), nullable=False),
            sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
            sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("moderation_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_dealer_review_rating"),
            sa.CheckConstraint("status IN ('pending', 'published', 'rejected', 'hidden')", name="ck_dealer_review_status"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "author_id", name="uq_dealer_review_company_author"),
        )
        op.create_index("ix_dealer_reviews_company_id", "dealer_reviews", ["company_id"])
        op.create_index("ix_dealer_reviews_author_id", "dealer_reviews", ["author_id"])
        op.create_index("ix_dealer_reviews_status", "dealer_reviews", ["status"])
    if not inspector.has_table("dealer_review_reports"):
        op.create_table(
            "dealer_review_reports",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("review_id", sa.Uuid(), nullable=False),
            sa.Column("reporter_id", sa.Uuid(), nullable=False),
            sa.Column("reason", sa.String(length=1000), nullable=False),
            sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["review_id"], ["dealer_reviews.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("review_id", "reporter_id", name="uq_dealer_review_reporter"),
        )
        op.create_index("ix_dealer_review_reports_review_id", "dealer_review_reports", ["review_id"])
        op.create_index("ix_dealer_review_reports_reporter_id", "dealer_review_reports", ["reporter_id"])
        op.create_index("ix_dealer_review_reports_status", "dealer_review_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dealer_review_reports_status", table_name="dealer_review_reports")
    op.drop_index("ix_dealer_review_reports_reporter_id", table_name="dealer_review_reports")
    op.drop_index("ix_dealer_review_reports_review_id", table_name="dealer_review_reports")
    op.drop_table("dealer_review_reports")
    op.drop_index("ix_dealer_reviews_status", table_name="dealer_reviews")
    op.drop_index("ix_dealer_reviews_author_id", table_name="dealer_reviews")
    op.drop_index("ix_dealer_reviews_company_id", table_name="dealer_reviews")
    op.drop_table("dealer_reviews")
    op.drop_column("companies", "logo_storage_name")
