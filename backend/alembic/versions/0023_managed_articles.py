"""Allow managed article content while preserving article rows on downgrade.

Revision ID: 0023_managed_articles
Revises: 0022_listing_categories
"""

from alembic import op
import sqlalchemy as sa

revision = "0023_managed_articles"
down_revision = "0022_listing_categories"
branch_labels = None
depends_on = None

_OLD_KINDS = "kind IN ('notification_template', 'seo_page', 'legal_document')"
_ARTICLE_KINDS = "kind IN ('notification_template', 'seo_page', 'legal_document', 'article')"
_CONSTRAINT = "ck_managed_content_kind"


def _current_kind_check() -> str | None:
    constraints = sa.inspect(op.get_bind()).get_check_constraints("managed_content")
    return next((item.get("sqltext", "") for item in constraints if item.get("name") == _CONSTRAINT), None)


def upgrade():
    current = _current_kind_check()
    if current is not None and "'article'" in current:
        return
    if current is not None:
        op.drop_constraint(_CONSTRAINT, "managed_content", type_="check")
    op.create_check_constraint(_CONSTRAINT, "managed_content", _ARTICLE_KINDS)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM managed_content WHERE kind = 'article'")):
        raise RuntimeError("Refusing to remove the managed article content kind while articles exist")
    current = _current_kind_check()
    if current is not None and "'article'" not in current:
        return
    if current is not None:
        op.drop_constraint(_CONSTRAINT, "managed_content", type_="check")
    op.create_check_constraint(_CONSTRAINT, "managed_content", _OLD_KINDS)
