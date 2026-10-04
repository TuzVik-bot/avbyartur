import json
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    CatalogMake,
    CatalogModel,
    Listing,
    ListingStatusEvent,
    User,
)
from app.security import hash_password

PASSWORD = "moderation-risk-test-password-123"


def _add_user(factory, *, role: str = "user") -> User:
    email = f"risk-{role}-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name=email.split("@")[0],
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


def _add_listing(
    factory,
    owner_id,
    *,
    status: str = "pending_review",
    **overrides,
) -> Listing:
    values = {
        "owner_id": owner_id,
        "slug": f"moderation-risk-{uuid.uuid4().hex}",
        "status": status,
        "revision": 1,
        "submitted_revision": 1 if status == "pending_review" else None,
        "title": "Moderation risk test listing",
        "description": "A test listing with ordinary vehicle information.",
        "contact_phone": f"+37529{uuid.uuid4().int % 10_000_000:07d}",
        "damaged": False,
        "parts_only": False,
    }
    values.update(overrides)
    listing = Listing(**values)
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _moderator_client(integration, email: str):
    client = TestClient(integration["client"].app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


def _risk_codes(item: dict) -> set[str]:
    return {signal["code"] for signal in item["risk_signals"]}


def test_moderation_risk_signal_contract_is_typed_and_stable():
    components = app.openapi()["components"]["schemas"]
    signal = components["ModerationRiskSignalOut"]
    assert set(signal["properties"]) == {
        "code",
        "severity",
        "summary",
        "related_count",
    }
    assert set(signal["properties"]["code"]["enum"]) == {
        "duplicate_vin",
        "similar_photo",
        "repeated_phone",
        "repeated_description",
        "external_link",
        "contact_token",
        "unusually_low_price",
        "high_submission_velocity",
        "configured_stop_word",
        "suspicious_city_change",
        "suspicious_seller_change",
    }
    assert set(signal["properties"]["severity"]["enum"]) == {
        "low",
        "medium",
        "high",
    }
    risk_signals = components["ModerationListingOut"]["properties"]["risk_signals"]
    assert risk_signals["type"] == "array"
    assert risk_signals["items"]["$ref"] == "#/components/schemas/ModerationRiskSignalOut"


def _queue_items_by_id(client, listing_ids: set[str]) -> dict[str, dict]:
    first = client.get(
        "/api/v1/moderation/listings",
        params={"page": 1, "page_size": 100},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    found = {row["id"]: row for row in body["items"] if row["id"] in listing_ids}
    for page in range(2, body["pagination"]["pages"] + 1):
        response = client.get(
            "/api/v1/moderation/listings",
            params={"page": page, "page_size": 100},
        )
        assert response.status_code == 200, response.text
        found.update(
            {
                row["id"]: row
                for row in response.json()["items"]
                if row["id"] in listing_ids
            }
        )
        if found.keys() >= listing_ids:
            break
    assert found.keys() >= listing_ids
    return found


def test_moderation_queue_reports_sanitized_duplicate_and_text_signals(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    other_owner = _add_user(factory)
    moderator = _add_user(factory, role="moderator")
    description = (
        "Редкая комплектация, автомобиль обслужен и готов к продаже. "
        "Звоните +375 (29) 123-45-67, пишите seller@example.by или @cars_seller. "
        "Дополнительные фотографии и подробная история обслуживания доступны. "
        "Состояние кузова хорошее, документы готовы к переоформлению. "
        "Осмотр проводится по предварительной договоренности."
    )
    vin = "1HGCM82633A004352"
    target = _add_listing(
        factory,
        owner.id,
        description=description,
        contact_phone="+375 (29) 123-45-67",
        vin=vin,
    )
    _add_listing(
        factory,
        other_owner.id,
        status="active",
        description="  " + description.replace(" ", "  "),
        contact_phone="+375291234567",
        vin=vin.lower(),
    )
    client = _moderator_client(integration, moderator.email)

    item = _queue_items_by_id(client, {str(target.id)})[str(target.id)]
    by_code = {signal["code"]: signal for signal in item["risk_signals"]}

    assert set(by_code) >= {
        "duplicate_vin",
        "repeated_phone",
        "repeated_description",
        "external_link",
        "contact_token",
    }
    assert by_code["duplicate_vin"]["related_count"] == 1
    assert by_code["duplicate_vin"]["severity"] == "high"
    assert by_code["external_link"]["severity"] == "low"
    serialized_signals = json.dumps(item["risk_signals"], ensure_ascii=False)
    assert vin not in serialized_signals
    assert "123-45-67" not in serialized_signals
    assert "seller@example.by" not in serialized_signals
    assert "cars_seller" not in serialized_signals


def _add_priced_model_group(factory, owner_id, *, peer_count: int, model_id):
    candidate = _add_listing(
        factory,
        owner_id,
        model_id=model_id,
        year=2018,
        currency="USD",
        price_amount=Decimal(2000),
    )
    for index in range(peer_count):
        _add_listing(
            factory,
            owner_id,
            model_id=model_id,
            year=2018,
            currency="USD",
            price_amount=Decimal(10000 + index * 1000),
        )
    return candidate


def _create_model(factory):
    make = CatalogMake(
        slug=f"risk-make-{uuid.uuid4().hex}",
        name="Risk Test Make",
        aliases=[],
    )
    with factory() as db:
        db.add(make)
        db.flush()
        model = CatalogModel(
            make_id=make.id,
            slug=f"risk-model-{uuid.uuid4().hex}",
            name="Risk Test Model",
            aliases=[],
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        db.expunge(model)
    return model


def test_low_price_signal_uses_same_model_year_currency_peers_and_minimum_count(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    moderator = _add_user(factory, role="moderator")
    model = _create_model(factory)
    enough_peers = _add_priced_model_group(
        factory,
        owner.id,
        peer_count=5,
        model_id=model.id,
    )
    model_with_too_few_peers = _create_model(factory)
    too_few_peers = _add_priced_model_group(
        factory,
        owner.id,
        peer_count=4,
        model_id=model_with_too_few_peers.id,
    )
    client = _moderator_client(integration, moderator.email)

    rows = _queue_items_by_id(
        client,
        {str(enough_peers.id), str(too_few_peers.id)},
    )
    enough = rows[str(enough_peers.id)]
    too_few = rows[str(too_few_peers.id)]

    low_price = next(
        signal
        for signal in enough["risk_signals"]
        if signal["code"] == "unusually_low_price"
    )
    assert low_price["related_count"] == 5
    assert "5 объявлениям" in low_price["summary"]
    assert "unusually_low_price" not in _risk_codes(too_few)


def test_high_submission_velocity_is_advisory_and_counts_distinct_recent_listings(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    moderator = _add_user(factory, role="moderator")
    listings = [
        _add_listing(factory, owner.id)
        for _ in range(5)
    ]
    with factory() as db:
        db.add_all(
            ListingStatusEvent(
                listing_id=listing.id,
                actor_id=owner.id,
                from_status="draft",
                to_status="pending_review",
                revision=1,
            )
            for listing in listings
        )
        db.commit()
    client = _moderator_client(integration, moderator.email)

    rows = _queue_items_by_id(client, {str(listing.id) for listing in listings})
    signal = next(
        signal
        for signal in rows[str(listings[0].id)]["risk_signals"]
        if signal["code"] == "high_submission_velocity"
    )

    assert signal["related_count"] == 5
    assert "60" in signal["summary"]
    with factory() as db:
        persisted = db.get(Listing, listings[0].id)
        assert persisted is not None
        assert persisted.status == "pending_review"
        assert db.scalar(
            select(ListingStatusEvent.id).where(
                ListingStatusEvent.listing_id == listings[0].id,
                ListingStatusEvent.to_status == "blocked",
            )
        ) is None
