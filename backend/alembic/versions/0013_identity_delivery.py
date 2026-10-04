"""Add verified identity contacts, recovery state, and email delivery outbox.

Revision ID: 0013_identity_delivery
Revises: 0012_dealer_workspaces
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_identity_delivery"
down_revision = "0012_dealer_workspaces"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _unique_constraints(table_name: str) -> set[str | None]:
    return {constraint.get("name") for constraint in _inspector().get_unique_constraints(table_name)}


def _check_constraints(table_name: str) -> set[str | None]:
    return {constraint.get("name") for constraint in _inspector().get_check_constraints(table_name)}


def _foreign_keys(table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key.get("constrained_columns") or ()),
            str(foreign_key.get("referred_table") or ""),
            tuple(foreign_key.get("referred_columns") or ()),
        )
        for foreign_key in _inspector().get_foreign_keys(table_name)
    }


def _validate_existing_table(
    table_name: str,
    *,
    columns: set[str],
    unique_constraints: tuple[str, ...] = (),
    check_constraints: tuple[str, ...] = (),
    foreign_keys: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = (),
) -> None:
    """Reject a partially matching table instead of masking schema drift."""

    missing_columns = columns - _columns(table_name)
    missing_unique = set(unique_constraints) - _unique_constraints(table_name)
    missing_checks = set(check_constraints) - _check_constraints(table_name)
    missing_foreign_keys = set(foreign_keys) - _foreign_keys(table_name)
    if missing_columns or missing_unique or missing_checks or missing_foreign_keys:
        details: list[str] = []
        if missing_columns:
            details.append(f"columns={sorted(missing_columns)}")
        if missing_unique:
            details.append(f"unique_constraints={sorted(missing_unique)}")
        if missing_checks:
            details.append(f"check_constraints={sorted(missing_checks)}")
        if missing_foreign_keys:
            details.append(f"foreign_keys={sorted(missing_foreign_keys)}")
        raise RuntimeError(f"{table_name} exists with an incompatible identity schema ({'; '.join(details)})")


def _ensure_indexes(table_name: str, indexes: tuple[tuple[str, list[str]], ...]) -> None:
    existing = _indexes(table_name)
    for name, columns in indexes:
        if name not in existing:
            op.create_index(name, table_name, columns)
            existing.add(name)


def upgrade() -> None:
    # 0001 bootstraps current ORM metadata, which can already include some or
    # all identity tables.  Handle each table independently so a partially
    # bootstrapped schema is repaired without attempting duplicate CREATEs.
    existing = _tables()

    if "verified_email_contacts" not in existing:
        op.create_table(
            "verified_email_contacts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_verified_email_address"),
            sa.UniqueConstraint("user_id", name="uq_verified_email_user"),
        )
    else:
        _validate_existing_table(
            "verified_email_contacts",
            columns={"id", "user_id", "email", "verified_at", "created_at"},
            unique_constraints=("uq_verified_email_address", "uq_verified_email_user"),
            foreign_keys=((('user_id',), "users", ('id',)),),
        )
    _ensure_indexes("verified_email_contacts", (("ix_verified_email_user", ["user_id"]),))

    if "email_verification_challenges" not in existing:
        op.create_table(
            "email_verification_challenges",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_digest", name="uq_email_verification_token_digest"),
        )
    else:
        _validate_existing_table(
            "email_verification_challenges",
            columns={
                "id",
                "user_id",
                "email",
                "token_digest",
                "expires_at",
                "consumed_at",
                "invalidated_at",
                "created_at",
            },
            unique_constraints=("uq_email_verification_token_digest",),
            foreign_keys=((('user_id',), "users", ('id',)),),
        )
    _ensure_indexes(
        "email_verification_challenges",
        (
            ("ix_email_verification_challenges_user_id", ["user_id"]),
            ("ix_email_verification_challenges_expires_at", ["expires_at"]),
            ("ix_email_verification_user_created", ["user_id", "created_at"]),
        ),
    )

    if "account_recovery_challenges" not in existing:
        op.create_table(
            "account_recovery_challenges",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_digest", name="uq_account_recovery_token_digest"),
        )
    else:
        _validate_existing_table(
            "account_recovery_challenges",
            columns={"id", "user_id", "token_digest", "expires_at", "consumed_at", "invalidated_at", "created_at"},
            unique_constraints=("uq_account_recovery_token_digest",),
            foreign_keys=((('user_id',), "users", ('id',)),),
        )
    _ensure_indexes(
        "account_recovery_challenges",
        (
            ("ix_account_recovery_challenges_user_id", ["user_id"]),
            ("ix_account_recovery_challenges_expires_at", ["expires_at"]),
            ("ix_account_recovery_user_created", ["user_id", "created_at"]),
        ),
    )

    if "account_deletion_requests" not in existing:
        op.create_table(
            "account_deletion_requests",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("revoked_sessions", sa.Integer(), nullable=False),
            sa.Column("withdrawn_listings", sa.Integer(), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("status IN ('requested', 'completed')", name="ck_account_deletion_status"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", name="uq_account_deletion_user"),
        )
    else:
        _validate_existing_table(
            "account_deletion_requests",
            columns={
                "id",
                "user_id",
                "status",
                "revoked_sessions",
                "withdrawn_listings",
                "requested_at",
                "completed_at",
            },
            unique_constraints=("uq_account_deletion_user",),
            check_constraints=("ck_account_deletion_status",),
            foreign_keys=((('user_id',), "users", ('id',)),),
        )

    if "identity_email_outbox" not in existing:
        op.create_table(
            "identity_email_outbox",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("dedupe_key", sa.String(length=240), nullable=False),
            sa.Column("message_type", sa.String(length=32), nullable=False),
            sa.Column("challenge_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("recipient", sa.String(length=320), nullable=False),
            sa.Column("subject", sa.String(length=240), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_by", sa.String(length=100), nullable=True),
            sa.Column("last_error", sa.String(length=100), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("message_type IN ('email_verification', 'password_recovery')", name="ck_identity_email_type"),
            sa.CheckConstraint("status IN ('queued', 'running', 'delivered', 'failed')", name="ck_identity_email_status"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dedupe_key", name="uq_identity_email_outbox_dedupe"),
        )
    else:
        _validate_existing_table(
            "identity_email_outbox",
            columns={
                "id",
                "dedupe_key",
                "message_type",
                "challenge_id",
                "user_id",
                "recipient",
                "subject",
                "body",
                "status",
                "attempts",
                "available_at",
                "lease_until",
                "locked_by",
                "last_error",
                "delivered_at",
                "created_at",
            },
            unique_constraints=("uq_identity_email_outbox_dedupe",),
            check_constraints=("ck_identity_email_type", "ck_identity_email_status"),
            foreign_keys=((('user_id',), "users", ('id',)),),
        )
    _ensure_indexes(
        "identity_email_outbox",
        (
            ("ix_identity_email_outbox_challenge_id", ["challenge_id"]),
            ("ix_identity_email_outbox_user_id", ["user_id"]),
            ("ix_identity_email_outbox_available_at", ["available_at"]),
            ("ix_identity_email_claim", ["status", "available_at", "created_at", "id"]),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "identity_email_outbox",
        "account_deletion_requests",
        "account_recovery_challenges",
        "email_verification_challenges",
        "verified_email_contacts",
    ):
        if bind.scalar(sa.text(f"SELECT count(*) FROM {table_name}")):
            raise RuntimeError(f"Refusing to remove identity data from {table_name}")
    op.drop_table("identity_email_outbox")
    op.drop_table("account_deletion_requests")
    op.drop_table("account_recovery_challenges")
    op.drop_table("email_verification_challenges")
    op.drop_table("verified_email_contacts")
