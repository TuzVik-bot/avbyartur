"""Add gated SMS OTP login and registration persistence.

Revision ID: 0011_sms_otp_auth
Revises: 0010_conversations
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_sms_otp_auth"
down_revision = "0010_conversations"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _checks(table_name: str) -> set[str | None]:
    return {
        constraint.get("name")
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    }


def _unique_constraints(table_name: str) -> set[str | None]:
    return {
        constraint.get("name")
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    }


def upgrade() -> None:
    user_columns = _columns("users")
    if user_columns["email"]["nullable"] is False:
        op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    if user_columns["password_hash"]["nullable"] is False:
        op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=True)
    if "phone_e164" not in user_columns:
        op.add_column("users", sa.Column("phone_e164", sa.String(length=16), nullable=True))
    if "phone_verified_at" not in user_columns:
        op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))

    if "uq_user_phone_e164" not in _unique_constraints("users"):
        op.create_unique_constraint("uq_user_phone_e164", "users", ["phone_e164"])
    checks = _checks("users")
    if "ck_user_phone_e164_supported" not in checks:
        op.create_check_constraint(
            "ck_user_phone_e164_supported",
            "users",
            r"phone_e164 IS NULL OR phone_e164 ~ '^\+375(25|29|33|44)[0-9]{7}$'",
        )
    if "ck_user_phone_verified_timestamp" not in checks:
        op.create_check_constraint(
            "ck_user_phone_verified_timestamp",
            "users",
            "phone_e164 IS NULL OR phone_verified_at IS NOT NULL",
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "sms_otp_challenges" not in tables:
        op.create_table(
            "sms_otp_challenges",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("phone_hash", sa.String(length=64), nullable=False),
            sa.Column("purpose", sa.String(length=20), nullable=False),
            sa.Column("code_digest", sa.String(length=64), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
            sa.Column("registration_display_name", sa.String(length=120), nullable=True),
            sa.Column("registration_terms_version", sa.String(length=80), nullable=True),
            sa.Column("registration_privacy_version", sa.String(length=80), nullable=True),
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("delivery_suppressed", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("delivery_failed", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("purpose IN ('login', 'registration')", name="ck_sms_otp_purpose"),
            sa.CheckConstraint("attempt_count >= 0", name="ck_sms_otp_attempt_count_nonnegative"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("phone_hash", "idempotency_key_hash", name="uq_sms_otp_phone_idempotency"),
        )
    indexes = _indexes("sms_otp_challenges")
    for name, columns in (
        ("ix_sms_otp_challenges_phone_hash", ["phone_hash"]),
        ("ix_sms_otp_challenges_expires_at", ["expires_at"]),
        ("ix_sms_otp_phone_created", ["phone_hash", "created_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "sms_otp_challenges", columns)

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "user_consents" not in tables:
        op.create_table(
            "user_consents",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("document_type", sa.String(length=20), nullable=False),
            sa.Column("version", sa.String(length=80), nullable=False),
            sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("source", sa.String(length=40), server_default="sms_registration", nullable=False),
            sa.CheckConstraint("document_type IN ('terms', 'privacy')", name="ck_user_consent_document_type"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "user_id", "document_type", "version", name="uq_user_consent_user_document_version"
            ),
        )
    indexes = _indexes("user_consents")
    for name, columns in (
        ("ix_user_consents_user_id", ["user_id"]),
        ("ix_user_consents_user_accepted", ["user_id", "accepted_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "user_consents", columns)


def downgrade() -> None:
    bind = op.get_bind()
    has_sms_accounts = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM users WHERE email IS NULL OR password_hash IS NULL)")
    ).scalar_one()
    if has_sms_accounts:
        raise RuntimeError("Refusing to remove SMS auth while passwordless user accounts exist")

    op.drop_index("ix_user_consents_user_accepted", table_name="user_consents")
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_table("user_consents")
    op.drop_index("ix_sms_otp_phone_created", table_name="sms_otp_challenges")
    op.drop_index("ix_sms_otp_challenges_expires_at", table_name="sms_otp_challenges")
    op.drop_index("ix_sms_otp_challenges_phone_hash", table_name="sms_otp_challenges")
    op.drop_table("sms_otp_challenges")
    op.drop_constraint("ck_user_phone_verified_timestamp", "users", type_="check")
    op.drop_constraint("ck_user_phone_e164_supported", "users", type_="check")
    op.drop_constraint("uq_user_phone_e164", "users", type_="unique")
    op.drop_column("users", "phone_verified_at")
    op.drop_column("users", "phone_e164")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=512), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
