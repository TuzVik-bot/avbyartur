"""Denormalize first publication time, index public search, add worker heartbeats.

Revision ID: 0034_listing_search_perf
Revises: 0033_listing_in_transit
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_listing_search_perf"
down_revision = "0033_listing_in_transit"
branch_labels = None
depends_on = None

PUBLICATION_ORDER_INDEX = "ix_listing_publication_order"
# Trigram indexes back the ILIKE '%term%' text search on listing columns.
TRIGRAM_INDEXES = {
    "ix_listing_title_trgm": "title",
    "ix_listing_make_name_snapshot_trgm": "make_name_snapshot",
    "ix_listing_model_name_snapshot_trgm": "model_name_snapshot",
}
HEARTBEAT_TABLE = "worker_heartbeats"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {
        item["name"] for item in _inspector().get_indexes(table) if item.get("name")
    }


def upgrade() -> None:
    if "published_at" not in _columns("listings"):
        op.add_column(
            "listings",
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        )
    # Same value the search used to aggregate on every request.
    op.execute(
        """
        UPDATE listings AS listing
        SET published_at = first_active.published_at
        FROM (
            SELECT listing_id, min(created_at) AS published_at
            FROM listing_status_events
            WHERE to_status = 'active'
            GROUP BY listing_id
        ) AS first_active
        WHERE first_active.listing_id = listing.id
          AND listing.published_at IS DISTINCT FROM first_active.published_at
        """
    )
    indexes = _indexes("listings")
    if PUBLICATION_ORDER_INDEX not in indexes:
        op.execute(
            f"CREATE INDEX {PUBLICATION_ORDER_INDEX} ON listings "
            "(status, category_code, coalesce(published_at, created_at) DESC, id DESC)"
        )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, column in TRIGRAM_INDEXES.items():
        if name not in indexes:
            op.execute(
                f"CREATE INDEX {name} ON listings USING gin ({column} gin_trgm_ops)"
            )
    if not _inspector().has_table(HEARTBEAT_TABLE):
        op.create_table(
            HEARTBEAT_TABLE,
            sa.Column("worker_id", sa.String(length=100), primary_key=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    if _inspector().has_table(HEARTBEAT_TABLE):
        op.drop_table(HEARTBEAT_TABLE)
    indexes = _indexes("listings")
    for name in (*TRIGRAM_INDEXES, PUBLICATION_ORDER_INDEX):
        if name in indexes:
            op.drop_index(name, table_name="listings")
    if "published_at" in _columns("listings"):
        op.drop_column("listings", "published_at")
