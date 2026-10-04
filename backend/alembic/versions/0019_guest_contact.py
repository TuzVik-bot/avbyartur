"""Allow contact reveal events for anonymous public visitors.

Revision ID: 0019_guest_contact
Revises: 0018_profile_identity
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_guest_contact"
down_revision = "0018_profile_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "contact_reveals" not in inspector.get_table_names():
        raise RuntimeError("contact_reveals table is required before 0019_guest_contact")
    columns = {column["name"]: column for column in inspector.get_columns("contact_reveals")}
    user_id = columns.get("user_id")
    if user_id is None:
        raise RuntimeError("contact_reveals.user_id is required before 0019_guest_contact")
    if not user_id["nullable"]:
        op.alter_column(
            "contact_reveals",
            "user_id",
            existing_type=user_id["type"],
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "contact_reveals" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("contact_reveals")}
    user_id = columns.get("user_id")
    if user_id is None or not user_id["nullable"]:
        return
    anonymous_events = bind.scalar(
        sa.text("SELECT count(*) FROM contact_reveals WHERE user_id IS NULL")
    )
    if anonymous_events:
        raise RuntimeError("Refusing to discard anonymous contact reveal history")
    op.alter_column(
        "contact_reveals",
        "user_id",
        existing_type=user_id["type"],
        nullable=False,
    )
