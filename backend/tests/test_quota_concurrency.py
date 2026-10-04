import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Company, Listing, ListingPhoto, LocationCity, LocationRegion, User
from app.security import hash_password


PASSWORD = "quota-concurrency-test-password"


def _add_user(factory) -> tuple[uuid.UUID, str]:
    email = f"quota-{uuid.uuid4().hex[:10]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name="Quota test seller",
            password_hash=hash_password(PASSWORD),
            role="user",
            status="active",
        )
        db.add(user)
        db.commit()
        return user.id, email


def _login(app, email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _add_company(factory, owner_id: uuid.UUID) -> Company:
    company = Company(
        owner_id=owner_id,
        name="Quota test dealer",
        slug=f"quota-dealer-{uuid.uuid4().hex[:10]}",
        unp=str(uuid.uuid4().int)[:9],
        address="Minsk, Test street 1",
        phone="+375291234567",
        status="approved",
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        return company


def _add_listing(factory, owner_id: uuid.UUID, *, status: str, company_id: uuid.UUID | None = None, submit_ready: bool = False) -> uuid.UUID:
    region_id = city_id = None
    if submit_ready:
        with factory() as db:
            region = LocationRegion(slug=f"quota-region-{uuid.uuid4().hex[:10]}", name="Test Region")
            db.add(region)
            db.flush()
            city = LocationCity(region_id=region.id, slug=f"quota-city-{uuid.uuid4().hex[:10]}", name="Test City")
            db.add(city)
            db.flush()
            region_id, city_id = region.id, city.id
            db.commit()

    listing_id = uuid.uuid4()
    with factory() as db:
        listing = Listing(
            id=listing_id,
            owner_id=owner_id,
            company_id=company_id,
            slug=f"quota-listing-{uuid.uuid4().hex}",
            status=status,
            revision=1,
            manual_make="Test make" if submit_ready else None,
            manual_model="Test model" if submit_ready else None,
            title="Quota concurrency test",
            year=2020 if submit_ready else None,
            mileage_km=1000 if submit_ready else None,
            fuel="petrol" if submit_ready else None,
            transmission="manual" if submit_ready else None,
            drive="rear" if submit_ready else None,
            condition="used" if submit_ready else None,
            damaged=False,
            parts_only=False,
            description="Complete data for a submission test" if submit_ready else "",
            contact_phone="+375291234567" if submit_ready else "",
            price_amount="10000.00" if submit_ready else None,
            currency="BYN" if submit_ready else None,
            region_id=region_id,
            city_id=city_id,
        )
        db.add(listing)
        if submit_ready:
            db.add(ListingPhoto(
                id=uuid.uuid4(),
                listing_id=listing_id,
                storage_name=uuid.uuid4().hex,
                original_name=f"{uuid.uuid4().hex}.upload",
                status="ready",
                position=0,
                is_cover=True,
                width=64,
                height=48,
                idempotency_key=f"quota-photo-{uuid.uuid4().hex}",
            ))
        db.commit()
    return listing_id


def _race_actions(monkeypatch, integration, owner_email: str, actions: list[tuple[str, uuid.UUID]], expected_statuses: tuple[int, int]):
    import app.api.listings as listings_api

    first_client, first_csrf = _login(integration["client"].app, owner_email)
    second_client, second_csrf = _login(integration["client"].app, owner_email)
    count_fn = listings_api.active_quota_count
    first_counted = Event()
    release_first = Event()
    second_counted = Event()
    call_lock = Lock()
    count_calls = 0

    def gated_count(db, owner_id, company_id):
        nonlocal count_calls
        count = count_fn(db, owner_id, company_id)
        with call_lock:
            count_calls += 1
            current_call = count_calls
        if current_call == 1:
            first_counted.set()
            if not release_first.wait(10):
                raise AssertionError("test did not release the first quota check")
        elif current_call == 2:
            second_counted.set()
        return count

    monkeypatch.setattr(listings_api, "active_quota_count", gated_count)

    def send(client, csrf, action):
        kind, listing_id = action
        action_path = "submit" if kind == "submit" else "resume"
        path = f"/api/v1/listings/{listing_id}/{action_path}"
        headers = {"X-CSRF-Token": csrf}
        if kind == "submit":
            headers["Idempotency-Key"] = f"quota-submit-{listing_id}"
        return client.post(path, json={"expected_revision": 1}, headers=headers)

    first_action_started = Event()
    second_action_started = Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: (first_action_started.set(), send(first_client, first_csrf, actions[0]))[1])
        assert first_action_started.wait(5)
        assert first_counted.wait(5), "first request never reached the quota check"
        second = pool.submit(lambda: (second_action_started.set(), send(second_client, second_csrf, actions[1]))[1])
        try:
            assert second_action_started.wait(5)
            assert not second_counted.wait(0.75), "second request reached quota count before the first committed"
        finally:
            release_first.set()
        responses = (first.result(timeout=10), second.result(timeout=10))

    assert tuple(sorted(response.status_code for response in responses)) == tuple(sorted(expected_statuses))
    return responses


@pytest.fixture
def quota_settings():
    try:
        with pytest.MonkeyPatch.context() as patcher:
            def set_values(**values):
                for name, value in values.items():
                    patcher.setenv(name, str(value))
                get_settings.cache_clear()

            yield set_values
    finally:
        get_settings.cache_clear()


def test_concurrent_submissions_are_serialized_at_private_quota_one(integration, monkeypatch, quota_settings):
    quota_settings(PRIVATE_LISTING_QUOTA=1)
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory)
    draft_ids = [
        _add_listing(factory, owner_id, status="draft", submit_ready=True)
        for _ in range(2)
    ]

    _race_actions(
        monkeypatch,
        integration,
        owner_email,
        [("submit", draft_ids[0]), ("submit", draft_ids[1])],
        (200, 409),
    )
    with factory() as db:
        counted = db.scalar(select(func.count(Listing.id)).where(
            Listing.owner_id == owner_id,
            Listing.company_id.is_(None),
            Listing.status.in_(["active", "pending_review"]),
        ))
        assert counted == 1


def test_concurrent_submit_and_resume_stay_within_private_quota_five(integration, monkeypatch, quota_settings):
    quota_settings(PRIVATE_LISTING_QUOTA=5)
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory)
    for status in ("active", "active", "pending_review", "pending_review"):
        _add_listing(factory, owner_id, status=status)
    resume_id = _add_listing(factory, owner_id, status="paused")
    submit_id = _add_listing(factory, owner_id, status="draft", submit_ready=True)

    _race_actions(
        monkeypatch,
        integration,
        owner_email,
        [("resume", resume_id), ("submit", submit_id)],
        (200, 409),
    )
    with factory() as db:
        counted = db.scalar(select(func.count(Listing.id)).where(
            Listing.owner_id == owner_id,
            Listing.company_id.is_(None),
            Listing.status.in_(["active", "pending_review"]),
        ))
        assert counted == 5


def test_concurrent_company_resumes_are_serialized_at_quota_one(integration, monkeypatch, quota_settings):
    quota_settings(COMPANY_LISTING_QUOTA=1)
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory)
    company = _add_company(factory, owner_id)
    listing_ids = [
        _add_listing(factory, owner_id, company_id=company.id, status="paused")
        for _ in range(2)
    ]

    _race_actions(
        monkeypatch,
        integration,
        owner_email,
        [("resume", listing_ids[0]), ("resume", listing_ids[1])],
        (200, 409),
    )
    with factory() as db:
        counted = db.scalar(select(func.count(Listing.id)).where(
            Listing.owner_id == owner_id,
            Listing.company_id == company.id,
            Listing.status.in_(["active", "pending_review"]),
        ))
        assert counted == 1
