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
    assert record_contact_click(db, payload(listing_id=listing_id, dedup_id=dedup_id, channel="viber")) == {"accepted": True, "duplicate": False}
    row = db.added[0]
    assert (row.listing_id, row.channel, row.dedup_id) == (listing_id, "viber", str(dedup_id))
    assert not hasattr(row, "phone") and not hasattr(row, "vin") and not hasattr(row, "email")
    assert db.commits == 1

def test_contact_click_ignores_inactive_listing():
    db = FakeDb(SimpleNamespace(id=uuid4(), status="draft"))
    assert record_contact_click(db, payload()) == {"accepted": True, "duplicate": False}
    assert db.added == [] and db.commits == 0

def test_contact_click_dedup_id_does_not_add_a_second_event():
    db = FakeDb(SimpleNamespace(id=uuid4(), status="active"), existing=object())
    assert record_contact_click(db, payload()) == {"accepted": True, "duplicate": True}
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
