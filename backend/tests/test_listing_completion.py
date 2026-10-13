import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import services
from app import worker

from app.api.saved_searches import _normalise_filters
from app.models import (
    BillingOrder,
    BillingTariff,
    Company,
    Listing,
    ListingPhoto,
    ListingPromotion,
    User,
)
from app.notification_service import saved_search_matches
from app.security import hash_password


PASSWORD = "listing-completion-test-password-123"


def test_promotion_badges_keep_partial_sqlite_fixture_support():
    engine = create_engine("sqlite:///:memory:")
    try:
        with Session(engine) as db:
            assert services._active_promotion_badges(db, [uuid.uuid4()]) == {}
    finally:
        engine.dispose()


def test_promotion_badges_skip_postgresql_schema_probe_and_propagate_missing_table(monkeypatch):
    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    class PostgresSessionStub:
        def get_bind(self):
            return bind

        def execute(self, _statement):
            raise OperationalError("SELECT listing_promotions", {}, RuntimeError("relation is missing"))

    def unexpected_inspection(_bind):
        raise AssertionError("PostgreSQL promotion lookup must not introspect the schema")

    monkeypatch.setattr(services, "sa_inspect", unexpected_inspection)
    with pytest.raises(OperationalError, match="relation is missing"):
        services._active_promotion_badges(PostgresSessionStub(), [uuid.uuid4()])


def _add_user(factory, *, label: str, role="user") -> User:
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


def _add_listing(factory, owner_id, *, title="Task 6 listing", status="active", **values):
    fields = {
        "owner_id": owner_id,
        "slug": f"listing-completion-{uuid.uuid4().hex}",
        "status": status,
        "revision": 1,
        "title": title,
        "description": "Task 6 listing used for API contract coverage.",
        "contact_phone": "+375291234567",
        "make_name_snapshot": "BMW",
        "model_name_snapshot": "3 Series",
        "year": 2020,
        "mileage_km": 60_000,
        "engine_volume_l": Decimal("2.0"),
        "power_hp": 190,
        "fuel": "diesel",
        "transmission": "automatic",
        "drive": "rear",
        "condition": "used",
        "damaged": False,
        "parts_only": False,
    }
    fields.update(values)
    listing = Listing(**fields)
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _login(integration, email: str) -> tuple[TestClient, str]:
    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _promotion(db, *, listing: Listing, service_code: str, now: datetime):
    tariff = BillingTariff(
        code=f"{service_code}-{uuid.uuid4().hex[:8]}",
        service_code=service_code,
        name=f"{service_code} test tariff",
        amount=Decimal("10.00"),
        currency="BYN",
        duration_days=7,
        status="active",
        revision=1,
    )
    db.add(tariff)
    db.flush()
    order = BillingOrder(
        user_id=listing.owner_id,
        listing_id=listing.id,
        tariff_id=tariff.id,
        service_code=service_code,
        tariff_code=tariff.code,
        tariff_revision=tariff.revision,
        amount=tariff.amount,
        currency=tariff.currency,
        duration_days=tariff.duration_days,
        provider="test",
        provider_reference=f"promotion-{uuid.uuid4().hex}",
        idempotency_key_digest=uuid.uuid4().hex * 2,
        request_digest=uuid.uuid4().hex * 2,
        status="paid",
        expires_at=now + timedelta(days=1),
        paid_at=now,
    )
    db.add(order)
    db.flush()
    db.add(ListingPromotion(
        order_id=order.id,
        listing_id=listing.id,
        service_code=service_code,
        tariff_code=tariff.code,
        tariff_revision=tariff.revision,
        amount=tariff.amount,
        currency=tariff.currency,
        duration_days=tariff.duration_days,
        status="active",
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(days=7),
    ))


def test_listing_options_and_additional_fields_round_trip(integration):
    factory = integration["SessionLocal"]
    seller = _add_user(factory, label="listing-fields-seller")
    client, csrf = _login(integration, seller.email)

    options = client.get("/api/v1/listing-options")
    assert options.status_code == 200, options.text
    body = options.json()
    assert set(body) == {"colors", "customs_statuses", "technical_conditions", "body_conditions", "equipment"}
    assert {item["code"] for item in body["colors"]} == {
        "black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "beige", "orange", "purple", "other"
    }
    assert {item["code"] for item in body["customs_statuses"]} == {
        "cleared_rb", "eaeu_import", "uncleared", "unknown"
    }

    created = client.post(
        "/api/v1/listings/drafts",
        headers={"Idempotency-Key": "task6-listing-fields", "X-CSRF-Token": csrf},
        json={
            "seller_type": "private",
            "title": "BMW with extended fields",
            "manual_make": "BMW",
            "manual_model": "3 Series",
            "year": 2020,
            "mileage_km": 60_000,
            "color": "blue",
            "customs_status": "cleared_rb",
            "technical_condition": "good",
            "body_condition": "minor_damage",
            "exchange": True,
            "bargaining": True,
            "credit": False,
            "leasing": True,
            "equipment": ["abs", "esp", "air_conditioning"],
            "district": "  Минск  Центральный  ",
            "call_hours": "10:00–19:00",
        },
    )
    assert created.status_code == 200, created.text
    listing = created.json()["listing"]
    assert {key: listing[key] for key in (
        "color", "customs_status", "technical_condition", "body_condition", "exchange",
        "bargaining", "credit", "leasing", "equipment", "district", "call_hours",
    )} == {
        "color": "blue",
        "customs_status": "cleared_rb",
        "technical_condition": "good",
        "body_condition": "minor_damage",
        "exchange": True,
        "bargaining": True,
        "credit": False,
        "leasing": True,
        "equipment": ["abs", "esp", "air_conditioning"],
        "district": "Минск Центральный",
        "call_hours": "10:00–19:00",
    }
    assert listing["revision"] == 1

    patched = client.patch(
        f"/api/v1/listings/{listing['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"expected_revision": 1, "color": "red", "equipment": ["rear_camera"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["listing"]["revision"] == 2
    assert patched.json()["listing"]["color"] == "red"
    assert patched.json()["listing"]["equipment"] == ["rear_camera"]


def test_search_filters_and_related_listings_use_new_listing_data(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="listing-search-owner")
    matching = _add_listing(
        factory,
        owner.id,
        title="Matching BMW listing",
        color="blue",
        customs_status="cleared_rb",
        technical_condition="good",
        body_condition="good",
        exchange=True,
        bargaining=False,
        credit=True,
        leasing=False,
        equipment=["abs", "esp"],
        district="Центральный",
        call_hours="10:00–19:00",
        vin="1HGCM82633A004352",
    )
    _add_listing(
        factory,
        owner.id,
        title="Does not match",
        color="red",
        customs_status="unknown",
        technical_condition="needs_repair",
        body_condition="repaired",
        exchange=False,
        bargaining=True,
        credit=False,
        leasing=True,
        equipment=["airbags"],
        district="Фрунзенский",
        vin=None,
    )
    with factory() as db:
        photo = ListingPhoto(
            listing_id=matching.id,
            storage_name=f"{uuid.uuid4().hex}",
            original_name=f"{uuid.uuid4().hex}.webp",
            status="ready",
            position=0,
            is_cover=True,
            width=800,
            height=600,
        )
        db.add(photo)
        db.commit()

    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.get(
        "/api/v1/listings",
        params=[
            ("color", "blue"),
            ("customs_status", "cleared_rb"),
            ("technical_condition", "good"),
            ("body_condition", "good"),
            ("exchange", "true"),
            ("credit", "true"),
            ("equipment", "abs"),
            ("equipment", "esp"),
            ("district", "Центральный"),
            ("has_vin", "true"),
            ("has_photos", "true"),
            ("engine_volume_min", "1.8"),
            ("engine_volume_max", "2.2"),
            ("power_min", "180"),
            ("power_max", "200"),
        ],
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(matching.id)]
    assert items[0]["equipment"] == ["abs", "esp"]

    related = client.get(f"/api/v1/listings/{matching.id}/related")
    assert related.status_code == 200, related.text
    related_ids = [item["id"] for item in related.json()["items"]]
    assert str(matching.id) not in related_ids
    assert all(item["status"] == "active" for item in related.json()["items"])


def test_saved_search_sanitization_and_matching_cover_new_filters(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="listing-saved-search-owner")
    listing = _add_listing(
        factory,
        owner.id,
        color="blue",
        customs_status="cleared_rb",
        technical_condition="good",
        body_condition="good",
        exchange=True,
        bargaining=True,
        credit=False,
        leasing=True,
        equipment=["abs", "esp"],
        district="Центральный",
        call_hours="10:00–19:00",
        vin="1HGCM82633A004352",
    )
    with factory() as db:
        db.add(ListingPhoto(
            listing_id=listing.id,
            storage_name=f"{uuid.uuid4().hex}",
            original_name=f"{uuid.uuid4().hex}.webp",
            status="ready",
            position=0,
            is_cover=True,
            width=800,
            height=600,
        ))
        db.flush()
        filters = _normalise_filters({
            "color": "blue",
            "customs_status": "cleared_rb",
            "technical_condition": "good",
            "body_condition": "good",
            "exchange": "true",
            "bargaining": True,
            "credit": "false",
            "leasing": True,
            "equipment": ["abs", "abs", "esp"],
            "district": "  Центральный  ",
            "call_hours": "10:00–19:00",
            "has_vin": "yes",
            "has_photos": "1",
            "engine_volume_min": "1.8",
            "engine_volume_max": "2.2",
            "power_min": 180,
            "power_max": 200,
        })
        assert filters["exchange"] is True
        assert filters["credit"] is False
        assert filters["equipment"] == ["abs", "esp"]
        assert filters["district"] == "Центральный"
        assert filters["engine_volume_min"] == 1.8
        with pytest.raises(ValueError, match="Unsupported color"):
            _normalise_filters({"color": "neon"})
        assert saved_search_matches(db, SimpleNamespace(filters=filters), db.get(Listing, listing.id))


def test_public_detail_views_feed_owner_scoped_analytics(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="listing-analytics-owner")
    outsider = _add_user(factory, label="listing-analytics-outsider")
    listing = _add_listing(factory, owner.id, title="Measured truck", category_code="trucks")
    owner_client, _ = _login(integration, owner.email)
    outsider_client, _ = _login(integration, outsider.email)
    anonymous = TestClient(integration["client"].app, base_url="http://testserver")

    assert anonymous.get(f"/api/v1/listings/{listing.id}").status_code == 200
    assert owner_client.get(f"/api/v1/listings/{listing.id}").status_code == 200
    today = date.today().isoformat()
    analytics = owner_client.get(
        f"/api/v1/listings/{listing.id}/analytics",
        params={"date_from": today, "date_to": today},
    )
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["listing_id"] == str(listing.id)
    assert analytics.json()["category_code"] == "trucks"
    assert analytics.json()["views"] == 1

    denied = outsider_client.get(f"/api/v1/listings/{listing.id}/analytics")
    assert denied.status_code == 404


def test_paid_promotions_are_badged_and_boost_only_newest_sort(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="listing-promotion-owner")
    boosted = _add_listing(factory, owner.id, title="Older boosted listing", year=2018, price_amount=Decimal("20000"), currency="USD")
    newest = _add_listing(factory, owner.id, title="Newest unpromoted listing", year=2022, price_amount=Decimal("10000"), currency="USD")
    now = datetime.now(UTC)
    with factory() as db:
        persisted = db.get(Listing, boosted.id)
        persisted.created_at = now - timedelta(days=10)
        db.flush()
        _promotion(db, listing=persisted, service_code="top", now=now)
        newest_persisted = db.get(Listing, newest.id)
        newest_persisted.created_at = now - timedelta(days=1)
        db.commit()

    client = TestClient(integration["client"].app, base_url="http://testserver")
    promoted = client.get("/api/v1/listings", params={"sort": "newest"})
    assert promoted.status_code == 200, promoted.text
    ids = [item["id"] for item in promoted.json()["items"]]
    assert ids.index(str(boosted.id)) < ids.index(str(newest.id))
    promoted_item = next(item for item in promoted.json()["items"] if item["id"] == str(boosted.id))
    assert promoted_item["promotion_badges"] == ["top"]

    year_sorted = client.get("/api/v1/listings", params={"sort": "year_desc"})
    assert year_sorted.status_code == 200, year_sorted.text
    year_ids = [item["id"] for item in year_sorted.json()["items"]]
    assert year_ids.index(str(newest.id)) < year_ids.index(str(boosted.id))


def test_public_company_listing_dto_includes_extended_listing_fields(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="company-listing-dto-owner")
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    with factory() as db:
        company = Company(
            owner_id=owner.id,
            name=f"Dealer {suffix}",
            slug=f"dealer-{suffix}",
            unp=str(suffix),
            address="Minsk",
            phone="+375291234567",
            status="approved",
            revision=1,
        )
        db.add(company)
        db.commit()
        company_id, slug = company.id, company.slug

    listing = _add_listing(
        factory,
        owner.id,
        company_id=company_id,
        color="blue",
        customs_status="cleared_rb",
        technical_condition="good",
        body_condition="minor_damage",
        exchange=True,
        bargaining=True,
        credit=False,
        leasing=True,
        equipment=["abs", "esp"],
        district="Центральный",
        call_hours="10:00–19:00",
    )
    response = TestClient(integration["client"].app, base_url="http://testserver").get(f"/api/v1/dealers/{slug}")
    assert response.status_code == 200, response.text
    item = response.json()["listings"]["items"][0]
    assert item["id"] == str(listing.id)
    assert {key: item[key] for key in (
        "color", "customs_status", "technical_condition", "body_condition", "exchange",
        "bargaining", "credit", "leasing", "equipment", "district", "call_hours", "promotion_badges",
    )} == {
        "color": "blue",
        "customs_status": "cleared_rb",
        "technical_condition": "good",
        "body_condition": "minor_damage",
        "exchange": True,
        "bargaining": True,
        "credit": False,
        "leasing": True,
        "equipment": ["abs", "esp"],
        "district": "Центральный",
        "call_hours": "10:00–19:00",
        "promotion_badges": [],
    }


def test_perceptual_hash_is_stable_for_a_small_visual_change():
    original = Image.new("RGB", (256, 256), "gray")
    drawing = ImageDraw.Draw(original)
    drawing.rectangle((32, 32, 220, 210), fill="navy")
    drawing.ellipse((70, 70, 180, 180), fill="silver")
    edited = original.copy()
    ImageDraw.Draw(edited).rectangle((12, 12, 20, 20), fill="red")

    hash_function = getattr(worker, "perceptual_hash", None)
    assert callable(hash_function), "photo worker should expose its perceptual hash function"
    original_hash = hash_function(original)
    edited_hash = hash_function(edited)
    assert len(original_hash) == len(edited_hash) == 16
    assert hash_function(original.copy()) == original_hash
    assert (int(original_hash, 16) ^ int(edited_hash, 16)).bit_count() <= 8


def test_photo_worker_persists_perceptual_hash(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="photo-hash-owner")
    listing = _add_listing(factory, owner.id, status="draft")
    original_name = f"{uuid.uuid4().hex}.png"
    storage_name = uuid.uuid4().hex
    with factory() as db:
        photo = ListingPhoto(
            listing_id=listing.id,
            storage_name=storage_name,
            original_name=original_name,
            status="processing",
            position=0,
            is_cover=True,
            width=0,
            height=0,
        )
        db.add(photo)
        db.commit()
        photo_id = photo.id

    quarantine = integration["media_root"] / ".quarantine"
    quarantine.mkdir(mode=0o700, exist_ok=True)
    source = Image.new("RGB", (256, 256), "slategray")
    ImageDraw.Draw(source).rectangle((32, 48, 224, 208), fill="royalblue")
    source.save(quarantine / original_name, format="PNG")
    worker._make_variants(photo_id)

    with factory() as db:
        processed = db.get(ListingPhoto, photo_id)
        assert processed.status == "ready"
        assert len(processed.perceptual_hash) == 16


def test_similar_photo_risk_signal_is_advisory_and_sanitized(integration):
    factory = integration["SessionLocal"]
    seller = _add_user(factory, label="photo-risk-seller")
    other_seller = _add_user(factory, label="photo-risk-other-seller")
    moderator = _add_user(factory, label="photo-risk-moderator", role="moderator")
    target = _add_listing(factory, seller.id, title="Photo risk target", status="pending_review")
    other = _add_listing(factory, other_seller.id, title="Photo risk match")

    base = Image.new("RGB", (256, 256), "gray")
    ImageDraw.Draw(base).rectangle((24, 32, 228, 220), fill="navy")
    edited = base.copy()
    ImageDraw.Draw(edited).rectangle((10, 10, 18, 18), fill="red")
    hash_function = getattr(worker, "perceptual_hash", None)
    assert callable(hash_function), "photo worker should expose its perceptual hash function"
    hashes = [hash_function(base), hash_function(edited)]

    with factory() as db:
        for listing, photo_hash in zip((target, other), hashes, strict=True):
            db.add(ListingPhoto(
                listing_id=listing.id,
                storage_name=f"{uuid.uuid4().hex}",
                original_name=f"{uuid.uuid4().hex}.webp",
                status="ready",
                position=0,
                is_cover=True,
                width=256,
                height=256,
                perceptual_hash=photo_hash,
            ))
        db.commit()

    client, _ = _login(integration, moderator.email)
    queue = client.get("/api/v1/moderation/listings", params={"status": "pending_review", "page_size": 100})
    assert queue.status_code == 200, queue.text
    item = next(row for row in queue.json()["items"] if row["id"] == str(target.id))
    signal = next(row for row in item["risk_signals"] if row["code"] == "similar_photo")
    assert signal["severity"] == "medium"
    assert signal["related_count"] == 1
    assert all(photo_hash not in str(signal) for photo_hash in hashes)
    with factory() as db:
        assert db.get(Listing, target.id).status == "pending_review"
