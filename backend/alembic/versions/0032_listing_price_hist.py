"""Add public listing price history and opt-in price-drop inbox delivery.

Revision ID: 0032_listing_price_hist
Revises: 0031_contact_click_analytics
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_listing_price_hist"
down_revision = "0031_contact_click_analytics"
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
    return {item["name"] for item in inspector.get_check_constraints(table) if item.get("name")}


def _indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {item["name"] for item in inspector.get_indexes(table) if item.get("name")}


def _replace_check(table: str, name: str, expression: str) -> None:
    if name in _checks(table):
        op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    if "price_drop_notifications_enabled" not in _columns("favorites"):
        op.add_column(
            "favorites",
            sa.Column(
                "price_drop_notifications_enabled",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )

    if not sa.inspect(op.get_bind()).has_table("listing_price_events"):
        op.create_table(
            "listing_price_events",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("listing_id", sa.Uuid(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=20), nullable=False),
            sa.Column("price_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=True),
            sa.Column("previous_price_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("previous_currency", sa.String(length=3), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "(price_amount IS NULL AND currency IS NULL) OR (price_amount > 0 AND currency IN ('BYN', 'USD'))",
                name="ck_listing_price_event_price",
            ),
            sa.CheckConstraint(
                "(previous_price_amount IS NULL AND previous_currency IS NULL) OR "
                "(previous_price_amount > 0 AND previous_currency IN ('BYN', 'USD'))",
                name="ck_listing_price_event_previous_price",
            ),
            sa.CheckConstraint(
                "event_type IN ('baseline', 'published', 'added', 'changed', 'removed')",
                name="ck_listing_price_event_type",
            ),
            sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("listing_id", "revision", name="uq_listing_price_event_revision"),
        )
    if "ix_listing_price_events_listing_id" not in _indexes("listing_price_events"):
        op.create_index("ix_listing_price_events_listing_id", "listing_price_events", ["listing_id"])
    if "ix_listing_price_events_listing_created" not in _indexes("listing_price_events"):
        op.create_index(
            "ix_listing_price_events_listing_created",
            "listing_price_events",
            ["listing_id", "created_at", "id"],
        )

    if "price_event_id" not in _columns("notification_outbox"):
        op.add_column("notification_outbox", sa.Column("price_event_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_notification_outbox_price_event_id_listing_price_events",
            "notification_outbox",
            "listing_price_events",
            ["price_event_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if "ix_notification_outbox_price_event_id" not in _indexes("notification_outbox"):
        op.create_index("ix_notification_outbox_price_event_id", "notification_outbox", ["price_event_id"])
    _replace_check(
        "notification_outbox",
        "ck_notification_outbox_source",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL AND price_event_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL AND price_event_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NULL AND listing_id IS NOT NULL AND price_event_id IS NOT NULL)",
    )

    if "price_event_id" not in _columns("user_notifications"):
        op.add_column("user_notifications", sa.Column("price_event_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            "fk_user_notifications_price_event_id_listing_price_events",
            "user_notifications",
            "listing_price_events",
            ["price_event_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if "ix_user_notifications_price_event_id" not in _indexes("user_notifications"):
        op.create_index("ix_user_notifications_price_event_id", "user_notifications", ["price_event_id"])
    _replace_check(
        "user_notifications",
        "ck_user_notification_source",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL AND price_event_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL AND price_event_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NULL AND listing_id IS NOT NULL AND price_event_id IS NOT NULL)",
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_events = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM listing_price_events)")).scalar_one()
    has_delivery = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM notification_outbox WHERE price_event_id IS NOT NULL) "
            "OR EXISTS (SELECT 1 FROM user_notifications WHERE price_event_id IS NOT NULL)"
        )
    ).scalar_one()
    has_opt_ins = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM favorites WHERE price_drop_notifications_enabled IS TRUE)")
    ).scalar_one()
    if has_events or has_delivery or has_opt_ins:
        raise RuntimeError("Refusing to downgrade while price history or price-drop preferences exist.")

    _replace_check(
        "notification_outbox",
        "ck_notification_outbox_source",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL)",
    )
    _replace_check(
        "user_notifications",
        "ck_user_notification_source",
        "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
        "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL)",
    )
    op.drop_index("ix_user_notifications_price_event_id", table_name="user_notifications")
    op.drop_column("user_notifications", "price_event_id")
    op.drop_index("ix_notification_outbox_price_event_id", table_name="notification_outbox")
    op.drop_column("notification_outbox", "price_event_id")
    op.drop_index("ix_listing_price_events_listing_created", table_name="listing_price_events")
    op.drop_index("ix_listing_price_events_listing_id", table_name="listing_price_events")
    op.drop_table("listing_price_events")
    op.drop_column("favorites", "price_drop_notifications_enabled")
