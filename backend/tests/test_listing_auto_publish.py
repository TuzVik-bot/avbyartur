from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api import listings
from app.config import Settings
from app.models import AuditEvent, ListingStatusEvent


@pytest.fixture
def submission(monkeypatch):
    listing = SimpleNamespace(id=uuid4(), owner_id=uuid4(), company_id=None,
        status="draft", revision=3, submitted_revision=None,
        moderation_reason="old rejection", moderated_at=None)
    user = SimpleNamespace(id=listing.owner_id)
    db = Mock()
    db.scalar.return_value = None
    db.scalars.return_value.all.return_value = [SimpleNamespace(status="ready")]
    for name in ("lock_owner", "check_revision", "validate_listing_for_submit"):
        monkeypatch.setattr(listings, name, Mock())
    monkeypatch.setattr(listings, "require_owned_listing", Mock(return_value=listing))
    monkeypatch.setattr(listings, "active_quota_count", Mock(return_value=0))
    monkeypatch.setattr(listings, "quota_limit", Mock(return_value=5))
    monkeypatch.setattr(listings, "serialize_listing", lambda db, value, **kwargs: {"status": value.status})
    monkeypatch.setattr(listings, "enqueue_saved_search_match", Mock())
    monkeypatch.setattr(listings, "record_active_listing_price_state", Mock())
    monkeypatch.setattr(listings, "get_settings", lambda: SimpleNamespace(listing_auto_publish_enabled=True))
    return listing, user, db


def submit(context):
    listing, user, db = context
    return listings.submit_listing(listing.id, SimpleNamespace(expected_revision=3), user, None, db, "submit-1")


def test_auto_publish_default_is_disabled():
    assert Settings(_env_file=None).listing_auto_publish_enabled is False


def test_auto_publish_can_be_enabled_from_environment(monkeypatch):
    monkeypatch.setenv("LISTING_AUTO_PUBLISH_ENABLED", "true")
    assert Settings(_env_file=None).listing_auto_publish_enabled is True


@pytest.mark.parametrize("initial_status", ["draft", "rejected"])
def test_enabled_submission_publishes_with_history_audit_and_notifications(submission, initial_status):
    listing, user, db = submission
    listing.status = initial_status
    assert submit(submission)["listing"]["status"] == "active"
    assert listing.revision == 4
    assert listing.submitted_revision == 3
    assert listing.moderated_at is not None
    assert listing.moderation_reason is None
    added = [call.args[0] for call in db.add.call_args_list]
    event = next(value for value in added if isinstance(value, ListingStatusEvent))
    assert (event.from_status, event.to_status, event.revision) == (initial_status, "active", 4)
    assert event.actor_id == user.id
    assert event.reason == "auto_publish_enabled"
    audit = next(value for value in added if isinstance(value, AuditEvent))
    assert audit.action == "auto_published"
    assert audit.actor_id == user.id
    assert audit.details == {"revision": 3, "reason": "auto_publish_enabled"}
    listings.enqueue_saved_search_match.assert_called_once_with(db, listing)
    listings.record_active_listing_price_state.assert_called_once_with(db, listing)
    db.commit.assert_called_once()


def test_disabled_submission_keeps_manual_review(submission, monkeypatch):
    monkeypatch.setattr(listings, "get_settings", lambda: SimpleNamespace(listing_auto_publish_enabled=False))
    listing, _, db = submission
    assert submit(submission)["listing"]["status"] == "pending_review"
    assert listing.revision == 3
    assert listing.moderated_at is None
    listings.enqueue_saved_search_match.assert_not_called()
    listings.record_active_listing_price_state.assert_not_called()


def test_duplicate_submission_has_no_second_publication(submission):
    listing, _, db = submission
    listing.status = "active"
    listing.revision = 4
    db.scalar.return_value = SimpleNamespace(resource_id=listing.id)
    db.get.return_value = listing
    assert submit(submission)["listing"]["status"] == "active"
    listings.validate_listing_for_submit.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
    listings.enqueue_saved_search_match.assert_not_called()


@pytest.mark.parametrize("failure", ["processing", "failed", "validation", "quota", "company", "revision", "owner"])
def test_auto_publication_preserves_submission_guards(submission, failure):
    listing, _, db = submission
    if failure in {"processing", "failed"}:
        db.scalars.return_value.all.return_value = [SimpleNamespace(status=failure)]
    elif failure == "validation":
        listings.validate_listing_for_submit.side_effect = HTTPException(422, "invalid")
    elif failure == "quota":
        listings.active_quota_count.return_value = 5
    elif failure == "revision":
        listings.check_revision.side_effect = HTTPException(409, "revision_conflict")
    elif failure == "owner":
        listings.require_owned_listing.side_effect = HTTPException(403, "forbidden")
    else:
        listing.company_id = uuid4()
        db.scalar.side_effect = [None, SimpleNamespace(status="pending")]
    with pytest.raises(HTTPException):
        submit(submission)
    assert listing.status == "draft"
    assert listing.revision == 3
    db.add.assert_not_called()
    db.commit.assert_not_called()
    listings.enqueue_saved_search_match.assert_not_called()
