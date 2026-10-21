"""Data-level verification of migration 0032_listing_price_hist.

The schema is built at 0031 through Alembic, populated with synthetic rows, and
then upgraded/downgraded through the real migration code.  Requires a dedicated
disposable PostgreSQL database (see ``_validated_url``); skipped otherwise.
"""

import json
import logging
import os
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

MIGRATION_URL_ENV = "MIGRATION_TEST_DATABASE_URL"
MIGRATION_CONFIRMATION_ENV = "MIGRATION_TEST_DATABASE_DISPOSABLE_CONFIRMATION"
BACKEND_DIR = Path(__file__).resolve().parents[1]
REV_0031 = "0031_contact_click_analytics"
REV_0032 = "0032_listing_price_hist"

SOURCE_CHECK_0031 = (
    "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
    "(saved_search_id IS NULL AND conversation_id IS NOT NULL AND listing_id IS NOT NULL)"
)
SEEDED_TABLES = (
    "users",
    "companies",
    "listings",
    "favorites",
    "saved_searches",
    "conversations",
    "notification_outbox",
    "user_notifications",
)


def _target(url: str) -> tuple[str, int, str]:
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    return (
        "<local>" if host in {"", "localhost", "127.0.0.1", "::1"} else host,
        parsed.port or 5432,
        parsed.database or "",
    )


def _validated_url() -> str:
    url = os.getenv(MIGRATION_URL_ENV)
    if not url:
        pytest.skip(
            f"Set {MIGRATION_URL_ENV} and {MIGRATION_CONFIRMATION_ENV} for a disposable PostgreSQL database"
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        pytest.fail(f"{MIGRATION_URL_ENV} must use PostgreSQL", pytrace=False)
    database = parsed.database or ""
    if not database.endswith("_test"):
        pytest.fail(
            f"{MIGRATION_URL_ENV} database name must end in _test", pytrace=False
        )
    if os.getenv(MIGRATION_CONFIRMATION_ENV) != database:
        pytest.fail(
            f"Set {MIGRATION_CONFIRMATION_ENV} to the exact disposable database name",
            pytrace=False,
        )
    protected = [
        os.getenv("DATABASE_URL"),
        os.getenv("TEST_DATABASE_URL"),
        get_settings().database_url,
    ]
    if any(other and _target(other) == _target(url) for other in protected):
        pytest.fail(
            f"{MIGRATION_URL_ENV} must not point at the runtime or integration database",
            pytrace=False,
        )
    return url


def _snapshot_logging() -> dict:
    loggers = [logging.getLogger(), *(l for l in logging.Logger.manager.loggerDict.values() if isinstance(l, logging.Logger))]
    return {logger: (logger.level, list(logger.handlers), logger.disabled, logger.propagate) for logger in loggers}


def _restore_logging(state: dict) -> None:
    """alembic/env.py calls fileConfig, which would otherwise leak into later tests."""
    for logger, (level, handlers, disabled, propagate) in state.items():
        logger.setLevel(level)
        logger.handlers[:] = handlers
        logger.disabled = disabled
        logger.propagate = propagate


@pytest.fixture
def migration_db(monkeypatch):
    url = _validated_url()
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    logging_state = _snapshot_logging()
    try:
        yield engine
    finally:
        _restore_logging(logging_state)
        engine.dispose()
        get_settings.cache_clear()


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return config


def _revision(engine: Engine) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()


def _strip_0032_objects(engine: Engine) -> None:
    """0001 runs create_all with current models, so remove 0032 objects to get a true 0031 schema."""
    with engine.begin() as connection:
        for table, constraint in (
            ("notification_outbox", "ck_notification_outbox_source"),
            ("user_notifications", "ck_user_notification_source"),
        ):
            connection.execute(
                text(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
            )
            connection.execute(text(f"ALTER TABLE {table} DROP COLUMN price_event_id"))
            connection.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK ({SOURCE_CHECK_0031})"
                )
            )
        connection.execute(text("DROP TABLE listing_price_events"))
        connection.execute(
            text("ALTER TABLE favorites DROP COLUMN price_drop_notifications_enabled")
        )


def _assert_schema_is_0031(engine: Engine) -> None:
    inspector = inspect(engine)
    assert not inspector.has_table("listing_price_events")
    assert "price_drop_notifications_enabled" not in {
        c["name"] for c in inspector.get_columns("favorites")
    }
    for table, constraint in (
        ("notification_outbox", "ck_notification_outbox_source"),
        ("user_notifications", "ck_user_notification_source"),
    ):
        assert "price_event_id" not in {c["name"] for c in inspector.get_columns(table)}
        sqltext = {
            c["name"]: c["sqltext"] for c in inspector.get_check_constraints(table)
        }[constraint]
        assert "price_event_id" not in sqltext
        assert "listing_id IS NOT NULL" in sqltext


def _seed(engine: Engine) -> dict:
    ids = {
        name: [uuid.uuid4() for _ in range(count)]
        for name, count in {"user": 4, "listing": 5, "search": 2}.items()
    }
    ids["company"] = uuid.uuid4()
    user_ids, listing_ids, search_ids = ids["user"], ids["listing"], ids["search"]
    listing_rows = [
        ("active", Decimal("12500.00"), "USD", user_ids[0], None),
        ("active", Decimal("38900.50"), "BYN", user_ids[0], ids["company"]),
        ("paused", Decimal("7000.00"), "USD", user_ids[1], None),
        ("draft", None, None, user_ids[1], None),
        ("active", None, None, user_ids[2], None),
    ]
    with engine.begin() as connection:
        for index, user_id in enumerate(user_ids):
            connection.execute(
                text(
                    "INSERT INTO users (id, email, display_name, role, status) "
                    "VALUES (:id, :email, :name, 'user', 'active')"
                ),
                {
                    "id": user_id,
                    "email": f"user{index}@example.test",
                    "name": f"User {index}",
                },
            )
        connection.execute(
            text(
                "INSERT INTO companies (id, owner_id, name, slug, unp, address, phone, status, revision) "
                "VALUES (:id, :owner, 'Test Motors', 'test-motors', '123456789', 'Minsk', '+375291112233', 'approved', 1)"
            ),
            {"id": ids["company"], "owner": user_ids[0]},
        )
        for index, (status, amount, currency, owner, company) in enumerate(
            listing_rows
        ):
            connection.execute(
                text(
                    "INSERT INTO listings (id, owner_id, company_id, slug, status, title, price_amount, currency, "
                    "revision, damaged, parts_only, description, contact_phone) "
                    "VALUES (:id, :owner, :company, :slug, :status, :title, :amount, :currency, "
                    "1, false, false, '', '+375291112233')"
                ),
                {
                    "id": listing_ids[index],
                    "owner": owner,
                    "company": company,
                    "slug": f"listing-{index}",
                    "status": status,
                    "title": f"Car {index}",
                    "amount": amount,
                    "currency": currency,
                },
            )
        for user_id, listing_id in (
            (user_ids[2], listing_ids[0]),
            (user_ids[2], listing_ids[1]),
            (user_ids[3], listing_ids[0]),
        ):
            connection.execute(
                text(
                    "INSERT INTO favorites (id, user_id, listing_id) VALUES (:id, :user, :listing)"
                ),
                {"id": uuid.uuid4(), "user": user_id, "listing": listing_id},
            )
        for index, search_id in enumerate(search_ids):
            connection.execute(
                text(
                    "INSERT INTO saved_searches (id, user_id, name, search_url, filters, status, revision, "
                    "notifications_enabled, notification_channel, notification_frequency) "
                    "VALUES (:id, :user, :name, '/cars?make=bmw', CAST(:filters AS jsonb), 'active', 1, true, 'web', 'daily')"
                ),
                {
                    "id": search_id,
                    "user": user_ids[2 + index],
                    "name": f"Search {index}",
                    "filters": json.dumps({"make": "bmw"}),
                },
            )
        conversation_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO conversations (id, listing_id, buyer_id, seller_id) VALUES (:id, :listing, :buyer, :seller)"
            ),
            {
                "id": conversation_id,
                "listing": listing_ids[0],
                "buyer": user_ids[2],
                "seller": user_ids[0],
            },
        )
        outbox_rows = (
            (
                "saved-search-1",
                search_ids[0],
                None,
                None,
                user_ids[2],
                "web",
                "delivered",
            ),
            (
                "saved-search-2",
                search_ids[1],
                None,
                None,
                user_ids[3],
                "email",
                "queued",
            ),
            (
                "conversation-1",
                None,
                conversation_id,
                listing_ids[0],
                user_ids[0],
                "web",
                "delivered",
            ),
        )
        for (
            key,
            search_id,
            conv_id,
            listing_id,
            user_id,
            channel,
            status,
        ) in outbox_rows:
            outbox_id = uuid.uuid4()
            connection.execute(
                text(
                    "INSERT INTO notification_outbox (id, dedupe_key, saved_search_id, conversation_id, listing_id, "
                    "user_id, channel, status, payload, attempts) VALUES (:id, :key, :search, :conv, :listing, "
                    ":user, :channel, :status, '{}'::jsonb, 0)"
                ),
                {
                    "id": outbox_id,
                    "key": key,
                    "search": search_id,
                    "conv": conv_id,
                    "listing": listing_id,
                    "user": user_id,
                    "channel": channel,
                    "status": status,
                },
            )
            if status == "delivered":
                connection.execute(
                    text(
                        "INSERT INTO user_notifications (id, outbox_id, user_id, saved_search_id, conversation_id, "
                        "listing_id, title, body, url) VALUES (:id, :outbox, :user, :search, :conv, :listing, "
                        "'Title', 'Body', '/x')"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "outbox": outbox_id,
                        "user": user_id,
                        "search": search_id,
                        "conv": conv_id,
                        "listing": listing_id,
                    },
                )
    return ids


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            t: connection.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            for t in SEEDED_TABLES
        }


def _listing_snapshot(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        return [
            tuple(r)
            for r in connection.execute(
                text(
                    "SELECT id, status, price_amount, currency, revision FROM listings ORDER BY slug"
                )
            )
        ]


def test_0032_upgrade_and_downgrade_guard_on_populated_0031_database(migration_db):
    engine = migration_db
    config = _alembic_config()

    # 1. Genuine 0031 schema
    command.upgrade(config, REV_0031)
    _strip_0032_objects(engine)
    _assert_schema_is_0031(engine)
    assert _revision(engine) == REV_0031

    # 2. Populated data
    ids = _seed(engine)
    counts_before = _counts(engine)
    listings_before = _listing_snapshot(engine)
    assert counts_before["listings"] == 5 and counts_before["favorites"] == 3
    assert (
        counts_before["notification_outbox"] == 3
        and counts_before["user_notifications"] == 2
    )

    # 3. Upgrade to head
    command.upgrade(config, "head")
    assert _revision(engine) == REV_0032
    inspector = inspect(engine)
    assert inspector.has_table("listing_price_events")
    event_checks = {
        c["name"] for c in inspector.get_check_constraints("listing_price_events")
    }
    assert event_checks == {
        "ck_listing_price_event_price",
        "ck_listing_price_event_previous_price",
        "ck_listing_price_event_type",
    }
    assert "uq_listing_price_event_revision" in {
        u["name"] for u in inspector.get_unique_constraints("listing_price_events")
    }
    assert {
        "ix_listing_price_events_listing_id",
        "ix_listing_price_events_listing_created",
    } <= {i["name"] for i in inspector.get_indexes("listing_price_events")}
    assert _counts(engine) == counts_before
    assert _listing_snapshot(engine) == listings_before
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM listing_price_events")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM favorites WHERE price_drop_notifications_enabled IS NOT FALSE"
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM notification_outbox WHERE price_event_id IS NOT NULL"
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM user_notifications WHERE price_event_id IS NOT NULL"
                )
            ).scalar_one()
            == 0
        )
        for table, constraint in (
            ("notification_outbox", "ck_notification_outbox_source"),
            ("user_notifications", "ck_user_notification_source"),
        ):
            definition = connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n AND conrelid = CAST(:t AS regclass)"
                ),
                {"n": constraint, "t": table},
            ).scalar_one()
            assert "price_event_id" in definition
        # Existing rows satisfy the new constraints (validated, not NOT VALID)
        assert (
            connection.execute(
                text(
                    "SELECT bool_and(convalidated) FROM pg_constraint WHERE conname IN "
                    "('ck_notification_outbox_source', 'ck_user_notification_source')"
                )
            ).scalar_one()
            is True
        )

    # New constraint semantics: a price-event source is accepted, a mixed source is rejected
    event_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO listing_price_events (id, listing_id, revision, event_type, price_amount, currency, "
                "previous_price_amount, previous_currency) VALUES (:id, :listing, 2, 'changed', 11000, 'USD', 12500, 'USD')"
            ),
            {"id": event_id, "listing": ids["listing"][0]},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO listing_price_events (id, listing_id, revision, event_type, price_amount, currency) "
                    "VALUES (:id, :listing, 3, 'changed', -1, 'USD')"
                ),
                {"id": uuid.uuid4(), "listing": ids["listing"][0]},
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_outbox (id, dedupe_key, saved_search_id, price_event_id, listing_id, user_id, "
                    "channel, status, payload, attempts) VALUES (:id, 'mixed', :search, :event, :listing, :user, "
                    "'web', 'queued', '{}'::jsonb, 0)"
                ),
                {
                    "id": uuid.uuid4(),
                    "search": ids["search"][0],
                    "event": event_id,
                    "listing": ids["listing"][0],
                    "user": ids["user"][2],
                },
            )

    # 4. Downgrade with no price events/opt-ins succeeds and restores 0031
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM listing_price_events"))
    command.downgrade(config, REV_0031)
    assert _revision(engine) == REV_0031
    _assert_schema_is_0031(engine)
    assert _counts(engine) == counts_before
    assert _listing_snapshot(engine) == listings_before

    # 5. Re-upgrade; guard blocks downgrade for events, opt-ins and event-linked deliveries
    command.upgrade(config, "head")
    assert _revision(engine) == REV_0032

    def assert_guard_blocks() -> None:
        with pytest.raises(RuntimeError, match="Refusing to downgrade"):
            command.downgrade(config, REV_0031)
        assert _revision(engine) == REV_0032
        assert inspect(engine).has_table("listing_price_events")
        assert "price_drop_notifications_enabled" in {
            c["name"] for c in inspect(engine).get_columns("favorites")
        }
        assert "price_event_id" in {
            c["name"] for c in inspect(engine).get_columns("notification_outbox")
        }
        assert "price_event_id" in {
            c["name"] for c in inspect(engine).get_columns("user_notifications")
        }

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO listing_price_events (id, listing_id, revision, event_type, price_amount, currency) "
                "VALUES (:id, :listing, 2, 'published', 12500, 'USD')"
            ),
            {"id": event_id, "listing": ids["listing"][0]},
        )
    assert_guard_blocks()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM listing_price_events")
            ).scalar_one()
            == 1
        )
    assert _counts(engine) == counts_before

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM listing_price_events"))
        connection.execute(
            text(
                "UPDATE favorites SET price_drop_notifications_enabled = true WHERE id = (SELECT id FROM favorites LIMIT 1)"
            )
        )
    assert_guard_blocks()

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE favorites SET price_drop_notifications_enabled = false")
        )
        connection.execute(
            text(
                "INSERT INTO listing_price_events (id, listing_id, revision, event_type) VALUES (:id, :listing, 2, 'removed')"
            ),
            {"id": event_id, "listing": ids["listing"][0]},
        )
        connection.execute(
            text(
                "INSERT INTO notification_outbox (id, dedupe_key, price_event_id, listing_id, user_id, channel, status, payload, attempts) "
                "VALUES (:id, 'price-1', :event, :listing, :user, 'web', 'queued', '{}'::jsonb, 0)"
            ),
            {
                "id": uuid.uuid4(),
                "event": event_id,
                "listing": ids["listing"][0],
                "user": ids["user"][2],
            },
        )
    assert_guard_blocks()
