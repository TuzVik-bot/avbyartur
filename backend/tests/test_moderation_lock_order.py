from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import moderation
from app.models import Listing, User


class FakeSession:
    def __init__(self, owner_id, listing_owner_id=None):
        self.owner_id = owner_id
        self.listing_owner_id = listing_owner_id or owner_id
        self.calls = []
        self.owner = SimpleNamespace(id=owner_id, status="active")
        self.listing = SimpleNamespace(id=uuid4(), owner_id=self.listing_owner_id, company_id=None)

    def scalar(self, statement):
        expression = statement.column_descriptions[0]["expr"]
        if expression is Listing.owner_id:
            self.calls.append("read-owner-id")
            return self.owner_id
        if expression is Listing.company_id:
            self.calls.append("read-company-id")
            return None
        if expression is User:
            assert statement._for_update_arg is not None
            self.calls.append("lock-owner")
            return self.owner
        if expression is Listing:
            assert statement._for_update_arg is not None
            self.calls.append("lock-listing")
            return self.listing
        raise AssertionError(f"Unexpected query entity: {expression}")


def test_moderation_locks_owner_before_listing():
    owner_id = uuid4()
    db = FakeSession(owner_id)

    result = moderation._lock_listing_owner_first(db, uuid4())

    assert result is db.listing
    assert db.calls == ["read-owner-id", "read-company-id", "lock-owner", "lock-listing"]


def test_moderation_rejects_listing_owner_change_after_owner_lock():
    owner_id = uuid4()
    db = FakeSession(owner_id, listing_owner_id=uuid4())

    with pytest.raises(HTTPException) as error:
        moderation._lock_listing_owner_first(db, uuid4())

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "revision_conflict"
    assert db.calls == ["read-owner-id", "read-company-id", "lock-owner", "lock-listing"]
