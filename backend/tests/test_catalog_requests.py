"""Durable seller requests for catalog modifications that are not listed yet."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import (
    AuditEvent,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Company,
    DealerTeamMember,
    Listing,
    ListingPhoto,
    LocationRegion,
    User,
)
from app.security import hash_password


PASSWORD = "catalog-request-test-password-123"


def _add_user(factory, label: str, role: str = "user") -> User:
    user = User(
        email=f"{label}-{uuid.uuid4().hex[:12]}@example.com",
        display_name=label,
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _hierarchy(factory, label: str):
    suffix = uuid.uuid4().hex[:10]
    with factory() as db:
        make = CatalogMake(slug=f"{label}-{suffix}", name=f"{label} Марка", aliases=[])
        db.add(make)
        db.flush()
        model = CatalogModel(
            make_id=make.id,
            slug=f"{label}-{suffix}",
            name=f"{label} Модель",
            aliases=[],
        )
        db.add(model)
        db.flush()
        generation = CatalogGeneration(
            model_id=model.id,
            slug=f"{label}-{suffix}",
            name=f"{label} поколение",
            year_from=2000,
            year_to=2010,
        )
        db.add(generation)
        db.flush()
        body_variant = CatalogBodyVariant(
            generation_id=generation.id,
            slug=f"{label}-{suffix}",
            name="Седан",
        )
        db.add(body_variant)
        db.flush()
        modification = CatalogModification(
            generation_id=generation.id,
            slug=f"{label}-{suffix}",
            name=f"{label} 2.0 AT",
            source_name="Owner-provided",
            source_metadata={"source_id": f"local-{suffix}"},
        )
        db.add(modification)
        db.commit()
        result = {
            "make_id": make.id,
            "model_id": model.id,
            "generation_id": generation.id,
            "body_variant_id": body_variant.id,
            "modification_id": modification.id,
        }
    return result


def _add_listing(
    factory,
    owner_id,
    hierarchy,
    *,
    company_id=None,
    status="draft",
    revision=4,
    known_generation=True,
    wrong_make_id=None,
    manual_identity=False,
):
    suffix = uuid.uuid4().hex
    with factory() as db:
        region = LocationRegion(slug=f"catalog-request-{suffix}", name="Минск")
        db.add(region)
        db.flush()
        listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"catalog-request-{suffix}",
            status=status,
            revision=revision,
            title="Автомобиль для проверки каталога",
            description="Описание объявления для интеграционного сценария.",
            contact_phone="+375291234567",
            make_id=wrong_make_id or hierarchy["make_id"],
            model_id=hierarchy["model_id"],
            generation_id=hierarchy["generation_id"] if known_generation else None,
            body_variant_id=hierarchy["body_variant_id"] if known_generation else None,
            modification_id=None,
            make_name_snapshot="Тестовая марка",
            model_name_snapshot="Тестовая модель",
            manual_make="Ручная марка" if manual_identity else None,
            manual_model="Ручная модель" if manual_identity else None,
            year=2005,
            mileage_km=125000,
            fuel="petrol",
            transmission="automatic",
            drive="front",
            condition="used",
            engine_volume_l=Decimal("2.0"),
            power_hp=150,
            damaged=False,
            parts_only=False,
            price_amount=Decimal("10000.00"),
            currency="BYN",
            region_id=region.id,
            manual_city="Минск",
            vin="WVWZZZ1JZXW000001",
        )
        db.add(listing)
        db.flush()
        db.add(
            ListingPhoto(
                listing_id=listing.id,
                storage_name=f"{suffix}.webp",
                original_name=f"{suffix}.jpg",
                status="ready",
                position=0,
                width=32,
                height=32,
            )
        )
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _client_and_csrf(integration, user: User):
    client = TestClient(integration["client"].app, base_url="http://testserver")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    return client, login.json()["csrf_token"]


def _headers(csrf: str, key: str = "catalog-request-key-1"):
    return {"X-CSRF-Token": csrf, "Idempotency-Key": key}


def _create_request(client, csrf, listing, *, key="catalog-request-key-1", **overrides):
    body = {
        "expected_listing_revision": listing.revision,
        "manual_modification_name": "2.0 TDI quattro",
        "note": "Номер двигателя и вариант коробки указаны продавцом.",
        **overrides,
    }
    return client.post(
        f"/api/v1/me/listings/{listing.id}/catalog-requests",
        json=body,
        headers=_headers(csrf, key),
    )


def _review(client, csrf, request_id, *, modification_id, **overrides):
    body = {
        "expected_revision": 1,
        "decision": "resolve",
        "reason": "Совпадение подтверждено по существующей записи каталога.",
        "resolved_modification_id": str(modification_id),
        **overrides,
    }
    return client.post(
        f"/api/v1/moderation/catalog-requests/{request_id}/review",
        json=body,
        headers={"X-CSRF-Token": csrf},
    )


def test_missing_modification_request_is_durable_idempotent_and_does_not_block_listing(integration):
    factory = integration["SessionLocal"]
    hierarchy = _hierarchy(factory, "required")
    seller = _add_user(factory, "catalog-seller")
    listing = _add_listing(factory, seller.id, hierarchy)
    client, csrf = _client_and_csrf(integration, seller)

    response = _create_request(client, csrf, listing)
    assert response.status_code == 201, response.text
    request = response.json()["request"]
    assert request["status"] == "pending"
    assert request["revision"] == 1
    assert request["listing_id"] == str(listing.id)
    assert request["manual_modification_name"] == "2.0 TDI quattro"
    assert request["snapshot"]["catalog"]["generation"]["id"] == str(hierarchy["generation_id"])
    assert request["snapshot"]["manual_parameters"] == {
        "year": 2005,
        "mileage_km": 125000,
        "engine_volume_l": "2.0",
        "power_hp": 150,
        "fuel": "petrol",
        "transmission": "automatic",
        "drive": "front",
    }
    assert "vin" not in request["snapshot"]["manual_parameters"]
    assert "contact_phone" not in request["snapshot"]["manual_parameters"]
    assert "description" not in request["snapshot"]

    replay = _create_request(client, csrf, listing)
    assert replay.status_code == 200, replay.text
    assert replay.json()["request"]["id"] == request["id"]
    assert _create_request(client, csrf, listing, manual_modification_name="different").status_code == 409
    assert _create_request(client, csrf, listing, key="catalog-request-key-2").status_code == 409

    with factory() as db:
        stored_listing = db.get(Listing, listing.id)
        assert stored_listing.status == "draft"
        assert stored_listing.modification_id is None

    submitted = client.post(
        f"/api/v1/listings/{listing.id}/submit",
        json={"expected_revision": listing.revision},
        headers=_headers(csrf, "listing-submit-key"),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["listing"]["status"] == "pending_review"
    assert submitted.json()["listing"].get("modification") is None

    owner_view = client.get(f"/api/v1/me/listings/{listing.id}/catalog-requests")
    assert owner_view.status_code == 200, owner_view.text
    assert owner_view.json()["items"][0]["id"] == request["id"]


def test_request_requires_csrf_fresh_revision_and_valid_catalog_hierarchy(integration):
    factory = integration["SessionLocal"]
    first = _hierarchy(factory, "hierarchy-first")
    other = _hierarchy(factory, "hierarchy-other")
    seller = _add_user(factory, "catalog-hierarchy-seller")
    listing = _add_listing(factory, seller.id, first)
    client, csrf = _client_and_csrf(integration, seller)
    path = f"/api/v1/me/listings/{listing.id}/catalog-requests"
    body = {
        "expected_listing_revision": listing.revision,
        "manual_modification_name": "Уточнённая версия",
    }

    assert client.post(path, json=body, headers={"Idempotency-Key": "csrf-missing"}).status_code == 403
    assert client.post(
        path,
        json={**body, "expected_listing_revision": listing.revision - 1},
        headers=_headers(csrf, "stale-listing"),
    ).status_code == 409

    with factory() as db:
        row = db.get(Listing, listing.id)
        row.make_id = other["make_id"]
        db.commit()
    invalid = _create_request(client, csrf, listing, key="invalid-hierarchy")
    assert invalid.status_code == 422


def test_company_catalog_request_access_is_scoped_to_active_write_membership(integration):
    factory = integration["SessionLocal"]
    hierarchy = _hierarchy(factory, "company")
    company_owner = _add_user(factory, "catalog-company-owner")
    seller = _add_user(factory, "catalog-company-seller")
    viewer = _add_user(factory, "catalog-company-viewer")
    outsider = _add_user(factory, "catalog-company-outsider")
    with factory() as db:
        company = Company(
            owner_id=company_owner.id,
            name="Каталогный дилер",
            slug=f"catalog-company-{uuid.uuid4().hex[:10]}",
            unp=f"{uuid.uuid4().int % 1_000_000_000:09d}",
            address="Минск",
            phone="+375291234567",
            status="approved",
        )
        db.add(company)
        db.flush()
        db.add_all([
            DealerTeamMember(company_id=company.id, user_id=seller.id, role="seller", status="active", granted_by=company_owner.id),
            DealerTeamMember(company_id=company.id, user_id=viewer.id, role="viewer", status="active", granted_by=company_owner.id),
        ])
        db.commit()
        db.refresh(company)
        company_id = company.id

    listing = _add_listing(factory, company_owner.id, hierarchy, company_id=company_id)
    seller_client, seller_csrf = _client_and_csrf(integration, seller)
    accepted = _create_request(seller_client, seller_csrf, listing, key="company-seller")
    assert accepted.status_code == 201, accepted.text

    viewer_client, viewer_csrf = _client_and_csrf(integration, viewer)
    assert _create_request(viewer_client, viewer_csrf, listing, key="company-viewer").status_code == 403
    outsider_client, outsider_csrf = _client_and_csrf(integration, outsider)
    assert _create_request(outsider_client, outsider_csrf, listing, key="company-outsider").status_code == 404
    assert outsider_client.get(f"/api/v1/me/listings/{listing.id}/catalog-requests").status_code == 404


def test_moderator_can_resolve_only_to_existing_matching_catalog_suggestion_with_audit(integration):
    factory = integration["SessionLocal"]
    hierarchy = _hierarchy(factory, "review")
    seller = _add_user(factory, "catalog-review-seller")
    moderator = _add_user(factory, "catalog-review-moderator", role="moderator")
    listing = _add_listing(factory, seller.id, hierarchy)
    seller_client, seller_csrf = _client_and_csrf(integration, seller)
    created = _create_request(seller_client, seller_csrf, listing)
    request_id = created.json()["request"]["id"]

    assert seller_client.get("/api/v1/moderation/catalog-requests").status_code == 403
    moderator_client, moderator_csrf = _client_and_csrf(integration, moderator)
    queue = moderator_client.get("/api/v1/moderation/catalog-requests")
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"][0]["id"] == request_id

    matches = moderator_client.get(
        f"/api/v1/moderation/catalog-requests/{request_id}/matches",
        params={"q": "2.0 AT"},
    )
    assert matches.status_code == 200, matches.text
    assert matches.json()["items"][0]["id"] == str(hierarchy["modification_id"])
    assert matches.json()["items"][0]["name"] == "review 2.0 AT"
    assert matches.json()["items"][0]["generation"]["name"] == "review поколение"

    for literal in ("%", "_"):
        literal_matches = moderator_client.get(
            f"/api/v1/moderation/catalog-requests/{request_id}/matches",
            params={"q": literal},
        )
        assert literal_matches.status_code == 200, literal_matches.text
        assert literal_matches.json()["items"] == []

    stale = _review(
        moderator_client,
        moderator_csrf,
        request_id,
        modification_id=hierarchy["modification_id"],
        expected_revision=99,
    )
    assert stale.status_code == 409

    resolved = _review(
        moderator_client,
        moderator_csrf,
        request_id,
        modification_id=hierarchy["modification_id"],
    )
    assert resolved.status_code == 200, resolved.text
    result = resolved.json()["request"]
    assert result["status"] == "resolved"
    assert result["revision"] == 2
    assert result["review_reason"] == "Совпадение подтверждено по существующей записи каталога."
    assert result["resolved_modification"]["id"] == str(hierarchy["modification_id"])

    with factory() as db:
        stored_listing = db.get(Listing, listing.id)
        assert stored_listing.modification_id is None
        audit = db.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "catalog_request",
                AuditEvent.entity_id == uuid.UUID(request_id),
            )
        )
        assert audit is not None
        assert audit.action == "catalog_request_resolved"
        assert audit.details["reason"] == result["review_reason"]
        assert audit.details["resolved_modification_id"] == str(hierarchy["modification_id"])

    assert moderator_client.post(
        f"/api/v1/moderation/catalog-requests/{request_id}/review",
        json={"expected_revision": 2, "decision": "reject", "reason": "Повтор"},
        headers={"X-CSRF-Token": moderator_csrf},
    ).status_code == 409


def test_missing_generation_uses_known_model_to_find_and_resolve_suggestion(integration):
    factory = integration["SessionLocal"]
    hierarchy = _hierarchy(factory, "generationless")
    seller = _add_user(factory, "catalog-generationless-seller")
    moderator = _add_user(factory, "catalog-generationless-moderator", role="moderator")
    listing = _add_listing(factory, seller.id, hierarchy, known_generation=False)
    seller_client, seller_csrf = _client_and_csrf(integration, seller)
    created = _create_request(seller_client, seller_csrf, listing, key="generationless-request")
    request_id = created.json()["request"]["id"]
    assert created.json()["request"]["snapshot"]["catalog"]["generation"] is None

    moderator_client, moderator_csrf = _client_and_csrf(integration, moderator)
    matches = moderator_client.get(
        f"/api/v1/moderation/catalog-requests/{request_id}/matches",
        params={"q": "2.0 AT"},
    )
    assert matches.status_code == 200, matches.text
    assert [item["id"] for item in matches.json()["items"]] == [str(hierarchy["modification_id"])]
    resolved = _review(
        moderator_client,
        moderator_csrf,
        request_id,
        modification_id=hierarchy["modification_id"],
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["request"]["resolved_modification"]["id"] == str(hierarchy["modification_id"])


def test_review_rejects_wrong_hierarchy_and_manual_identity_match_without_evidence(integration):
    factory = integration["SessionLocal"]
    first = _hierarchy(factory, "manual-first")
    other = _hierarchy(factory, "manual-other")
    seller = _add_user(factory, "catalog-manual-seller")
    moderator = _add_user(factory, "catalog-manual-moderator", role="moderator")
    listing = _add_listing(factory, seller.id, first)
    seller_client, seller_csrf = _client_and_csrf(integration, seller)
    created = _create_request(seller_client, seller_csrf, listing, key="wrong-hierarchy-request")
    request_id = created.json()["request"]["id"]
    moderator_client, moderator_csrf = _client_and_csrf(integration, moderator)

    wrong = _review(
        moderator_client,
        moderator_csrf,
        request_id,
        modification_id=other["modification_id"],
    )
    assert wrong.status_code == 422

    manual_listing = _add_listing(factory, seller.id, first, known_generation=False, manual_identity=True)
    with factory() as db:
        row = db.get(Listing, manual_listing.id)
        row.make_id = None
        row.model_id = None
        db.commit()
    manual = _create_request(seller_client, seller_csrf, manual_listing, key="manual-identity-request")
    manual_id = manual.json()["request"]["id"]
    no_match = moderator_client.get(
        f"/api/v1/moderation/catalog-requests/{manual_id}/matches",
        params={"q": "2.0 AT"},
    )
    assert no_match.status_code == 200
    assert no_match.json()["items"] == []
    cannot_resolve = _review(
        moderator_client,
        moderator_csrf,
        manual_id,
        modification_id=first["modification_id"],
    )
    assert cannot_resolve.status_code == 422

    rejected = moderator_client.post(
        f"/api/v1/moderation/catalog-requests/{manual_id}/review",
        json={"expected_revision": 1, "decision": "reject", "reason": "Нет точной структуры для безопасного сопоставления."},
        headers={"X-CSRF-Token": moderator_csrf},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["request"]["status"] == "rejected"


def test_catalog_request_creation_is_rate_limited_per_account(integration):
    factory = integration["SessionLocal"]
    hierarchy = _hierarchy(factory, "rate-limit")
    seller = _add_user(factory, "catalog-rate-limit-seller")
    listings = [_add_listing(factory, seller.id, hierarchy) for _ in range(11)]
    client, csrf = _client_and_csrf(integration, seller)

    responses = [
        _create_request(
            client,
            csrf,
            listing,
            key=f"rate-limit-{index}",
            note=f"Различающийся запрос {index}",
        )
        for index, listing in enumerate(listings)
    ]
    assert [response.status_code for response in responses[:10]] == [201] * 10
    assert responses[10].status_code == 429
