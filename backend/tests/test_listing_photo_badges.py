from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Listing
from app.photo_badge_schemas import ListingPhotoBadgesInput
from app.schemas import ListingForm
from pydantic import ValidationError
from test_moderation_risk_signals import _add_user, _add_listing, _moderator_client

BADGES = ["verified", "free_history", "best_price"]


def setup(integration, role="admin", status="active"):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    actor = _add_user(factory, role=role)
    listing = _add_listing(factory, owner.id, status=status)
    client = _moderator_client(integration, actor.email)
    headers = {"x-csrf-token": client.cookies.get("avtorinok_csrf")}
    return client, headers, listing, owner


def test_admin_badges_persist_are_public_and_audited(integration):
    client, headers, listing, _ = setup(integration)
    url = f"/api/v1/moderation/listings/{listing.id}/photo-badges"
    response = client.put(url, headers=headers, json={"expected_revision": 1, "photo_badges": BADGES})
    assert response.status_code == 200, response.text
    assert response.json()["listing"]["photo_badges"] == BADGES
    assert response.json()["listing"]["revision"] == 2
    public = integration["client"].get(f"/api/v1/listings/{listing.id}")
    assert public.status_code == 200, public.text
    assert public.json()["listing"]["photo_badges"] == BADGES
    search = integration["client"].get("/api/v1/listings")
    assert next(row for row in search.json()["items"] if row["id"] == str(listing.id))["photo_badges"] == BADGES
    with integration["SessionLocal"]() as db:
        assert db.get(Listing, listing.id).photo_badges == BADGES
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "photo_badges_updated"))
        assert audit.details["before"] == []
        assert audit.details["after"] == BADGES
    stale = client.put(url, headers=headers, json={"expected_revision": 1, "photo_badges": []})
    assert stale.status_code == 409
    removed = client.put(url, headers=headers, json={"expected_revision": 2, "photo_badges": []})
    assert removed.status_code == 200
    assert removed.json()["listing"]["photo_badges"] == []


@pytest.mark.parametrize("role", ["user", "moderator"])
def test_only_admin_can_assign_badges(integration, role):
    client, headers, listing, _ = setup(integration, role)
    response = client.put(f"/api/v1/moderation/listings/{listing.id}/photo-badges", headers=headers,
                          json={"expected_revision": 1, "photo_badges": BADGES})
    assert response.status_code == 403


def test_badges_require_csrf_and_known_unique_values(integration):
    client, headers, listing, _ = setup(integration)
    url = f"/api/v1/moderation/listings/{listing.id}/photo-badges"
    assert client.put(url, json={"expected_revision": 1, "photo_badges": BADGES}).status_code == 403
    for invalid in [["unknown"], ["verified", "verified"], BADGES + ["verified"]]:
        assert client.put(url, headers=headers, json={"expected_revision": 1, "photo_badges": invalid}).status_code == 422


def test_pending_badge_change_preserves_approval_and_seller_edit_clears_badges(integration):
    client, headers, listing, owner = setup(integration, status="pending_review")
    changed = client.put(f"/api/v1/moderation/listings/{listing.id}/photo-badges", headers=headers,
                         json={"expected_revision": 1, "photo_badges": BADGES})
    assert changed.status_code == 200, changed.text
    approved = client.post(f"/api/v1/moderation/listings/{listing.id}/approve", headers=headers,
                           json={"expected_revision": 2})
    assert approved.status_code == 200, approved.text
    seller = _moderator_client(integration, owner.email)
    edited = seller.patch(f"/api/v1/listings/{listing.id}", headers={"x-csrf-token": seller.cookies.get("avtorinok_csrf")},
                          json={"expected_revision": 3, "description": "Updated seller description"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["listing"]["photo_badges"] == []
    forged = seller.patch(f"/api/v1/listings/{listing.id}", headers={"x-csrf-token": seller.cookies.get("avtorinok_csrf")},
                          json={"expected_revision": 4, "photo_badges": BADGES})
    assert forged.status_code == 422


def test_badge_input_normalizes_order_and_seller_form_rejects_badges():
    payload = ListingPhotoBadgesInput(expected_revision=1, photo_badges=["best_price", "verified"])
    assert payload.photo_badges == ["verified", "best_price"]
    with pytest.raises(ValidationError, match="only be changed by an administrator"):
        ListingForm.model_validate({"photo_badges": ["verified"]})
