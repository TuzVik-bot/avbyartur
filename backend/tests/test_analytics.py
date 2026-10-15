from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.analytics_schemas import ContactClickEventIn
from app.analytics_service import record_contact_click

def payload(**overrides):
    values = {"listing_id": uuid4(), "channel": "phone", "occurred_at": datetime.now(timezone.utc), "dedup_id": uuid4()}
    values.update(overrides)
    return ContactClickEventIn.model_validate(values)

class FakeDb:
    def __init__(self, listing=None, existing=None):
        self.listing, self.existing = listing, existing
        self.added, self.commits, self.rollbacks, self.calls = [], 0, 0, 0
    def scalar(self, _query):
        self.calls += 1
        return self.listing if self.calls == 1 else self.existing
    def add(self, row): self.added.append(row)
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1

def test_contact_click_records_allowlisted_fields_and_deduplicates():
    listing_id, dedup_id = uuid4(), uuid4()
    db = FakeDb(SimpleNamespace(id=listing_id, status="active"))
    assert record_contact_click(db, payload(listing_id=listing_id, dedup_id=dedup_id, channel="viber")) == {"accepted": True, "recorded": True, "duplicate": False}
    row = db.added[0]
    assert (row.listing_id, row.channel, row.dedup_id) == (listing_id, "viber", str(dedup_id))
    assert not hasattr(row, "phone") and not hasattr(row, "vin") and not hasattr(row, "email")
    assert db.commits == 1

def test_contact_click_ignores_inactive_listing():
    db = FakeDb(SimpleNamespace(id=uuid4(), status="draft"))
    assert record_contact_click(db, payload()) == {"accepted": True, "recorded": False, "duplicate": False}
    assert db.added == [] and db.commits == 0

def test_contact_click_dedup_id_does_not_add_a_second_event():
    db = FakeDb(SimpleNamespace(id=uuid4(), status="active"), existing=object())
    assert record_contact_click(db, payload()) == {"accepted": True, "recorded": False, "duplicate": True}
    assert db.added == [] and db.commits == 0

def test_schema_rejects_unknown_channel_and_naive_timestamp():
    with pytest.raises(ValidationError): payload(channel="email")
    with pytest.raises(ValidationError): payload(occurred_at=datetime.now())


def test_endpoint_fails_open_when_analytics_storage_fails(monkeypatch):
    from starlette.requests import Request
    from app.api import analytics

    captured = []
    class BrokenDb(FakeDb):
        def rollback(self): self.rollbacks += 1
    def fail_rate_limit(*_args, **_kwargs): raise RuntimeError("storage unavailable")
    monkeypatch.setattr(analytics, "consume_rate_limit", fail_rate_limit)
    monkeypatch.setattr(analytics, "capture_safe_error", lambda component, error: captured.append((component, error)))
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http", "query_string": b""})
    db = BrokenDb()
    assert analytics.contact_click(payload(), request, db, "granted") == {"accepted": True, "recorded": False}
    assert db.rollbacks == 1 and captured == [("analytics", "RuntimeError")]


def test_endpoint_fails_closed_without_explicit_consent(monkeypatch):
    from starlette.requests import Request
    from app.api import analytics

    monkeypatch.setattr(analytics, "consume_rate_limit", lambda *_args, **_kwargs: pytest.fail("must not process without consent"))
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http", "query_string": b""})
    db = FakeDb()
    assert analytics.contact_click(payload(), request, db) == {"accepted": True, "recorded": False}
    assert db.added == [] and db.commits == 0


def test_analytics_http_boundary_serializes_contact_event_and_rejects_extra_fields(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import analytics
    from app.db import get_db

    api = FastAPI()
    api.include_router(analytics.router)
    def override_db():
        yield FakeDb()
    api.dependency_overrides[get_db] = override_db
    from app.main import validation_error
    from fastapi.exceptions import RequestValidationError
    api.add_exception_handler(RequestValidationError, validation_error)
    monkeypatch.setattr(analytics, "consume_rate_limit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(analytics, "record_contact_click", lambda *_args: {"accepted": True, "recorded": True, "duplicate": False})
    client = TestClient(api)
    body = payload().model_dump(mode="json")
    response = client.post("/api/v1/analytics/events", json=body, headers={"X-Analytics-Consent": "granted"})
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "recorded": True}
    invalid = client.post("/api/v1/analytics/events", json={**body, "phone": "+375291234567"}, headers={"X-Analytics-Consent": "granted"})
    assert invalid.status_code == 422
    assert "+375291234567" not in invalid.text


def test_postgres_contact_event_unique_constraint_and_migration_schema(integration):
    from sqlalchemy import inspect, select
    from sqlalchemy.exc import IntegrityError
    from app.analytics_models import ContactClickEvent
    from app.models import Listing
    from test_admin_management import add_user

    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine, factory = integration["engine"], integration["SessionLocal"]
    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "0029_contact_click_analytics.py"
    spec = importlib.util.spec_from_file_location("task10_contact_click_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    # integration fixture has validated a disposable *_test PostgreSQL database.
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS contact_click_events CASCADE")
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
        inspector = inspect(connection)
        assert inspector.has_table("contact_click_events")
        constraints = inspector.get_unique_constraints("contact_click_events")
        assert any(item["name"] == "uq_contact_click_dedup" for item in constraints)
    owner = add_user(factory)
    listing = Listing(owner_id=owner.id, slug=f"analytics-{uuid4().hex}", status="active", title="Analytics test")
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        event = ContactClickEvent(listing_id=listing.id, channel="phone", dedup_id=str(uuid4()), occurred_at=datetime.now(timezone.utc))
        db.add(event)
        db.commit()
        duplicate = ContactClickEvent(listing_id=listing.id, channel="phone", dedup_id=event.dedup_id, occurred_at=datetime.now(timezone.utc))
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(ContactClickEvent.id).where(ContactClickEvent.dedup_id == event.dedup_id)) is not None


def test_frontend_error_http_boundary_is_allowlisted_and_visible_to_monitor(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import analytics
    from app.db import get_db
    from app.main import validation_error
    from fastapi.exceptions import RequestValidationError

    api = FastAPI()
    api.include_router(analytics.router)
    api.add_exception_handler(RequestValidationError, validation_error)
    def override_db():
        yield FakeDb()
    api.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(analytics, "consume_rate_limit", lambda *_args, **_kwargs: None)
    delivered = []
    monkeypatch.setattr(analytics, "capture_safe_error", lambda component, error, **kwargs: delivered.append((component, error, kwargs)) or True)
    client = TestClient(api)
    response = client.post("/api/v1/analytics/errors", json={"error_type": "TypeError", "release_id": "abc123", "breadcrumbs": ["contact_click"]})
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "recorded": True}
    assert delivered == [("frontend", "TypeError", {"release_id": "abc123", "breadcrumbs": ["contact_click"]})]
    unsafe = client.post("/api/v1/analytics/errors", json={"error_type": "TypeError", "release_id": "abc123", "breadcrumbs": ["contact_click"], "message": "private@example.com"})
    assert unsafe.status_code == 422
    assert "private@example.com" not in unsafe.text


def test_safe_monitoring_keeps_release_and_fixed_breadcrumbs_only(monkeypatch):
    import json
    import sentry_sdk
    from pydantic import SecretStr
    from app import error_monitoring
    from app.config import Settings

    monkeypatch.setattr(error_monitoring, "get_settings", lambda: Settings(_env_file=None, sentry_dsn=SecretStr("https://public@sentry.example/1")))
    captured = []
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda event: captured.append(event) or "accepted-id")
    result = error_monitoring.capture_safe_error("frontend", "TypeError", release_id="release-2026.10", breadcrumbs=["contact_click", "https://private.example?token=secret"])
    assert result is True
    encoded = json.dumps(captured[0])
    assert "release-2026.10" in encoded and "contact_click" in encoded
    assert "private.example" not in encoded and "secret" not in encoded
    assert captured[0]["breadcrumbs"]["values"] == [{"category": "contact_click", "message": "contact_click", "level": "info"}]


def test_only_contact_click_dedup_integrity_conflict_is_suppressed(monkeypatch):
    from starlette.requests import Request
    from sqlalchemy.exc import IntegrityError
    from app.api import analytics

    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http", "query_string": b""})
    monkeypatch.setattr(analytics, "consume_rate_limit", lambda *_args, **_kwargs: None)
    reported = []
    monkeypatch.setattr(analytics, "capture_safe_error", lambda component, error: reported.append((component, error)))
    db = FakeDb()
    duplicate = IntegrityError("insert", {}, Exception("duplicate key violates unique constraint \"uq_contact_click_dedup\""))
    monkeypatch.setattr(analytics, "record_contact_click", lambda *_args: (_ for _ in ()).throw(duplicate))
    assert analytics.contact_click(payload(), request, db, "granted") == {"accepted": True, "recorded": False}
    assert reported == []

    foreign_key = IntegrityError("insert", {}, Exception("foreign key constraint failed"))
    monkeypatch.setattr(analytics, "record_contact_click", lambda *_args: (_ for _ in ()).throw(foreign_key))
    assert analytics.contact_click(payload(), request, db, "granted") == {"accepted": True, "recorded": False}
    assert reported == [("analytics", "IntegrityError")]


def test_contact_click_endpoint_reports_skipped_listing_as_not_recorded(monkeypatch):
    from starlette.requests import Request
    from app.api import analytics

    monkeypatch.setattr(analytics, "consume_rate_limit", lambda *_args, **_kwargs: None)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http", "query_string": b""})
    assert analytics.contact_click(payload(), request, FakeDb(SimpleNamespace(id=uuid4(), status="draft")), "granted") == {"accepted": True, "recorded": False}
