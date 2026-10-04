"""Add listing conversations and participant-scoped chat state.

Revision ID: 0010_conversations
Revises: 0009_notification_outbox
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_conversations"
down_revision = "0009_notification_outbox"
branch_labels = None
depends_on = None


def _columns(table: str) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_index(name: str, table: str, columns: list[str]) -> None:
    if name not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns)


def _add_check(name: str, table: str, expression: str) -> None:
    existing = {item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints(table)}
    if name not in existing:
        op.create_check_constraint(name, table, expression)


def _create_chat_tables() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "conversations" not in tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("buyer_id", sa.Uuid(), nullable=False),
            sa.Column("seller_id", sa.Uuid(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_message_sequence", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("buyer_id <> seller_id", name="ck_conversation_distinct_participants"),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["seller_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("buyer_id", "listing_id", name="uq_conversation_buyer_listing"),
        )
    if "conversation_messages" not in tables:
        op.create_table(
            "conversation_messages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("sender_id", sa.Uuid(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("conversation_id", "sequence", name="uq_conversation_message_sequence"),
        )
    if "conversation_participant_states" not in tables:
        op.create_table(
            "conversation_participant_states",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("conversation_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
            sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["last_read_message_id"], ["conversation_messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant_state"),
        )

    _add_index("ix_conversations_listing_id", "conversations", ["listing_id"])
    _add_index("ix_conversations_buyer_id", "conversations", ["buyer_id"])
    _add_index("ix_conversations_seller_id", "conversations", ["seller_id"])
    _add_index("ix_conversations_last_message_at", "conversations", ["last_message_at"])
    _add_index("ix_conversations_buyer_last_message", "conversations", ["buyer_id", "last_message_at", "id"])
    _add_index("ix_conversations_seller_last_message", "conversations", ["seller_id", "last_message_at", "id"])
    _add_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])
    _add_index("ix_conversation_messages_sender_id", "conversation_messages", ["sender_id"])
    _add_index("ix_conversation_messages_created_at", "conversation_messages", ["created_at"])
    _add_index("ix_conversation_participant_states_conversation_id", "conversation_participant_states", ["conversation_id"])
    _add_index("ix_conversation_participant_states_user_id", "conversation_participant_states", ["user_id"])
    _add_index("ix_conversation_participant_states_user", "conversation_participant_states", ["user_id", "conversation_id"])


def _extend_notifications() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("notification_outbox", "user_notifications"):
        if table not in tables:
            continue
        cols = _columns(table)
        if "saved_search_id" in cols and not cols["saved_search_id"]["nullable"]:
            op.alter_column(table, "saved_search_id", existing_type=sa.Uuid(), nullable=True)
        if "conversation_id" not in cols:
            op.add_column(table, sa.Column("conversation_id", sa.Uuid(), nullable=True))
            op.create_foreign_key(
                f"fk_{table}_conversation_id_conversations",
                table,
                "conversations",
                ["conversation_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "saved_search_id" in cols:
            _add_check(
                "ck_notification_outbox_source" if table == "notification_outbox" else "ck_user_notification_source",
                table,
                "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
                "(saved_search_id IS NULL AND conversation_id IS NOT NULL)",
            )
        _add_index(f"ix_{table}_conversation_id", table, ["conversation_id"])


def upgrade() -> None:
    _create_chat_tables()
    _extend_notifications()


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("user_notifications", "notification_outbox"):
        if table not in tables or "conversation_id" not in _columns(table):
            continue
        # Notification rows refer to the chat through a cascade FK. Remove
        # them explicitly so saved_search_id can return to NOT NULL below.
        if table == "user_notifications":
            op.execute("DELETE FROM user_notifications WHERE conversation_id IS NOT NULL")
        else:
            op.execute(
                "DELETE FROM worker_jobs WHERE kind = 'notification.deliver' "
                "AND payload->>'outbox_id' IN (SELECT id::text FROM notification_outbox WHERE conversation_id IS NOT NULL)"
            )
            op.execute("DELETE FROM notification_outbox WHERE conversation_id IS NOT NULL")
        constraint_name = "ck_notification_outbox_source" if table == "notification_outbox" else "ck_user_notification_source"
        checks = {item.get("name") for item in sa.inspect(op.get_bind()).get_check_constraints(table)}
        if constraint_name in checks:
            op.drop_constraint(constraint_name, table, type_="check")
        indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}
        index_name = f"ix_{table}_conversation_id"
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
        foreign_keys = {item.get("name") for item in sa.inspect(op.get_bind()).get_foreign_keys(table)}
        fk_name = f"fk_{table}_conversation_id_conversations"
        if fk_name in foreign_keys:
            op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_column(table, "conversation_id")
        cols = _columns(table)
        if "saved_search_id" in cols and cols["saved_search_id"]["nullable"]:
            op.alter_column(table, "saved_search_id", existing_type=sa.Uuid(), nullable=False)

    if "idempotency_records" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.execute("DELETE FROM idempotency_records WHERE scope LIKE 'conversation.%'")

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "conversation_participant_states" in tables:
        for name in (
            "ix_conversation_participant_states_user",
            "ix_conversation_participant_states_user_id",
            "ix_conversation_participant_states_conversation_id",
        ):
            indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("conversation_participant_states")}
            if name in indexes:
                op.drop_index(name, table_name="conversation_participant_states")
        op.drop_table("conversation_participant_states")
    if "conversation_messages" in tables:
        for name in (
            "ix_conversation_messages_created_at",
            "ix_conversation_messages_sender_id",
            "ix_conversation_messages_conversation_id",
        ):
            indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("conversation_messages")}
            if name in indexes:
                op.drop_index(name, table_name="conversation_messages")
        op.drop_table("conversation_messages")
    if "conversations" in tables:
        for name in (
            "ix_conversations_seller_last_message",
            "ix_conversations_buyer_last_message",
            "ix_conversations_last_message_at",
            "ix_conversations_seller_id",
            "ix_conversations_buyer_id",
            "ix_conversations_listing_id",
        ):
            indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("conversations")}
            if name in indexes:
                op.drop_index(name, table_name="conversations")
        op.drop_table("conversations")
