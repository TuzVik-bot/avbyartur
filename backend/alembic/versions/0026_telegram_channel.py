"""Add the Telegram notification channel and account linking fields.

Revision ID: 0026_telegram_channel
Revises: 0025_listing_price_hist
"""

import sqlalchemy as sa

from alembic import op

revision = "0026_telegram_channel"
down_revision = "0025_listing_price_hist"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _checks(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {
        item["name"]
        for item in inspector.get_check_constraints(table)
        if item.get("name")
    }


def _uniques(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {
        item["name"]
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }


def _replace_check(table: str, name: str, expression: str) -> None:
    if name in _checks(table):
        op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


CHANNEL_EXPRESSIONS = {
    "ck_saved_search_notification_channel": (
        "saved_searches",
        "notification_channel IS NULL OR notification_channel IN ('email', 'web', 'telegram')",
        "notification_channel IS NULL OR notification_channel IN ('email', 'web')",
    ),
    "ck_notification_outbox_channel": (
        "notification_outbox",
        "channel IN ('web', 'email', 'telegram')",
        "channel IN ('web', 'email')",
    ),
    "ck_saved_search_notification_batch_channel": (
        "saved_search_notification_batches",
        "channel IN ('web', 'email', 'telegram')",
        "channel IN ('web', 'email')",
    ),
}


def upgrade() -> None:
    user_columns = _columns("users")
    if "telegram_chat_id" not in user_columns:
        op.add_column(
            "users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True)
        )
    if "telegram_link_code" not in user_columns:
        op.add_column(
            "users",
            sa.Column("telegram_link_code", sa.String(length=64), nullable=True),
        )
    if "telegram_linked_at" not in user_columns:
        op.add_column(
            "users",
            sa.Column("telegram_linked_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "uq_users_telegram_chat_id" not in _uniques("users"):
        op.create_unique_constraint(
            "uq_users_telegram_chat_id", "users", ["telegram_chat_id"]
        )

    for name, (table, expression, _downgrade_expression) in CHANNEL_EXPRESSIONS.items():
        _replace_check(table, name, expression)


def downgrade() -> None:
    for name, (table, _expression, downgrade_expression) in CHANNEL_EXPRESSIONS.items():
        _replace_check(table, name, downgrade_expression)

    if "uq_users_telegram_chat_id" in _uniques("users"):
        op.drop_constraint("uq_users_telegram_chat_id", "users", type_="unique")
    user_columns = _columns("users")
    for column in ("telegram_linked_at", "telegram_link_code", "telegram_chat_id"):
        if column in user_columns:
            op.drop_column("users", column)
