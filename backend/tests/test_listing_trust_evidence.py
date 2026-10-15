import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.listing_trust_schemas import ListingTrustEvidenceInput
from app.models import AuditEvent, Listing, ListingTrustEvidence, User
from app.security import hash_password

PASSWORD = "listing-trust-evidence-test-password-123"


def _user(factory, role: str) -> User:
    suffix = uuid.uuid4().hex
    user = User(
        email=f"trust-{role}-{suffix}@example.com", display_name=f"Trust {role}",
        password_hash=hash_password(PASSWORD), role=role, status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _login(integration, user: User):
    client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def test_evidence_contract_requires_public_fields_and_rejects_personal_identifiers():
    with pytest.raises(ValidationError):
        ListingTrustEvidenceInput(
            expected_revision=1, label=" ", summary="checked", source="Registry",
            checked_at=date(2026, 10, 10), scope="documents",
        )
    with pytest.raises(ValidationError):
        ListingTrustEvidenceInput(
            expected_revision=1, label="VIN", summary="WVWZZZ1JZXW000001", source="Registry",
            checked_at=date(2026, 10, 10), scope="VIN",
        )
    with pytest.raises(ValidationError):
        ListingTrustEvidenceInput(
            expected_revision=1, label="Contact", summary="+375 (29) 123.45.67", source="Registry",
            checked_at=date(2026, 10, 10), scope="contact details",
        )
    with pytest.raises(ValidationError):
        ListingTrustEvidenceInput(
            expected_revision=1, label="Contact", summary="seller@example.com", source="Registry",
            checked_at=date(2026, 10, 10), scope="contact details",
        )
    with pytest.raises(ValidationError):
        ListingTrustEvidenceInput(
            expected_revision=1, label="VIN", summary="Checked", source="со слов продавца",
            checked_at=date(2026, 10, 10), scope="VIN",
        )


def test_evidence_is_moderator_only_revision_bound_audited_and_detail_only(integration):
    factory = integration["SessionLocal"]
    owner = _user(factory, "user")
    moderator = _user(factory, "moderator")
    suffix = uuid.uuid4().hex
    listing = Listing(
        owner_id=owner.id, slug=f"trust-{suffix}", status="active", revision=4,
        title="Trust evidence test vehicle", description="Test listing description",
        contact_phone="+375291234567", damaged=False, parts_only=False,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        listing_id = listing.id

    client, csrf = _login(integration, moderator)
    payload = {
        "expected_revision": 4, "label": "Документы сверены",
        "summary": "Сверены регистрационные документы автомобиля",
        "source": "Реестр регистрационных документов", "checked_at": "2026-10-10",
        "scope": "регистрационные документы",
    }
    path = f"/api/v1/moderation/listings/{listing_id}/evidence"
    assert client.post(path, json=payload).status_code == 403
    created = client.post(path, json=payload, headers=csrf)
    assert created.status_code == 201, created.text
    evidence_id = created.json()["id"]

    public_detail = client.get(f"/api/v1/listings/{listing_id}")
    assert public_detail.status_code == 200, public_detail.text
    assert public_detail.json()["listing"]["verified_evidence"][0]["summary"] == payload["summary"]
    search = client.get("/api/v1/listings")
    assert search.status_code == 200
    assert all("verified_evidence" not in item for item in search.json()["items"])

    with factory() as db:
        row = db.get(Listing, listing_id)
        row.revision = 5
        db.commit()
    stale_detail = client.get(f"/api/v1/listings/{listing_id}")
    assert stale_detail.json()["listing"]["verified_evidence"] == []

    remove_path = f"{path}/{evidence_id}"
    assert client.delete(remove_path).status_code == 403
    assert client.delete(remove_path, headers=csrf).status_code == 204
    with factory() as db:
        row = db.get(ListingTrustEvidence, uuid.UUID(evidence_id))
        assert row is not None and row.removed_at is not None
        events = db.scalars(select(AuditEvent).where(
            AuditEvent.entity_type == "listing_trust_evidence", AuditEvent.entity_id == row.id,
        )).all()
        assert {event.action for event in events} == {"created", "removed"}


def test_evidence_rejects_stale_revision(integration):
    factory = integration["SessionLocal"]
    owner = _user(factory, "user")
    moderator = _user(factory, "moderator")
    listing = Listing(
        owner_id=owner.id, slug=f"trust-stale-{uuid.uuid4().hex}", status="active", revision=2,
        title="Stale evidence test vehicle", description="Test listing description",
        contact_phone="+375291234567", damaged=False, parts_only=False,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        listing_id = listing.id
    client, csrf = _login(integration, moderator)
    response = client.post(
        f"/api/v1/moderation/listings/{listing_id}/evidence",
        json={"expected_revision": 1, "label": "Documents checked", "summary": "Verified",
              "source": "Registry", "checked_at": "2026-10-10", "scope": "Documents"},
        headers=csrf,
    )
    assert response.status_code == 409, response.text
