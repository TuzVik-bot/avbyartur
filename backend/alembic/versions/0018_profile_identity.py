"""Profile phone proof challenges and global notification preferences.

Revision ID: 0018_profile_identity
Revises: 0017_listing_completion
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_profile_identity"
down_revision = "0017_listing_completion"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    tables = _tables()
    if "profile_phone_change_challenges" not in tables:
        op.create_table(
            "profile_phone_change_challenges",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("old_phone_hash", sa.String(length=64), nullable=False),
            sa.Column("new_phone_e164", sa.String(length=16), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("old_code_digest", sa.String(length=64), nullable=False),
            sa.Column("new_code_digest", sa.String(length=64), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "idempotency_key_hash", name="uq_profile_phone_change_idempotency"),
            sa.CheckConstraint("attempt_count >= 0", name="ck_profile_phone_change_attempts"),
        )
    existing = _indexes("profile_phone_change_challenges")
    for name, columns in (
        ("ix_profile_phone_change_user_id", ["user_id"]),
        ("ix_profile_phone_change_expires", ["expires_at"]),
        ("ix_profile_phone_change_user_created", ["user_id", "created_at"]),
    ):
        if name not in existing:
            op.create_index(name, "profile_phone_change_challenges", columns)

    if "user_notification_preferences" not in tables:
        op.create_table(
            "user_notification_preferences",
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("web_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("email_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
            sa.CheckConstraint("revision >= 1", name="ck_user_notification_preferences_revision"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM profile_phone_change_challenges")):
        raise RuntimeError("Refusing to discard phone-change proof history")
    if bind.scalar(sa.text("SELECT count(*) FROM user_notification_preferences")):
        raise RuntimeError("Refusing to discard notification preferences")
    op.drop_index("ix_profile_phone_change_user_created", table_name="profile_phone_change_challenges")
    op.drop_index("ix_profile_phone_change_expires", table_name="profile_phone_change_challenges")
    op.drop_index("ix_profile_phone_change_user_id", table_name="profile_phone_change_challenges")
    op.drop_table("user_notification_preferences")
    op.drop_table("profile_phone_change_challenges")
