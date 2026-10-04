import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.api import listings as listings_api
from app.models import Company, ContactReveal, Listing, RateLimitBucket, User, UserSession
from app.security import hash_password, secret_hash


PASSWORD = "guest-contact-test-password-123"
PHONE = "+375291234567"


def _add_user(factory, *, status: str = "active") -> User:
    email = f"guest-contact-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password(PASSWORD),
        role="user",
        status=status,
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _add_listing(factory, owner_id, *, status: str = "active", company_id=None) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        company_id=company_id,
        slug=f"guest-contact-{uuid.uuid4().hex}",
        status=status,
        revision=1,
        title="Guest contact test listing",
        description="Isolated integration fixture.",
        contact_phone=PHONE,
        damaged=False,
        parts_only=False,
        make_name_snapshot="Mazda",
        model_name_snapshot="3",
        year=2018,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _client(integration, ip: str = "198.51.100.40") -> TestClient:
    return TestClient(
        integration["client"].app,
        base_url="http://testserver",
        client=(ip, 51000),
    )


def _enable_guest_contact(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr(
        listings_api,
        "get_settings",
        lambda: SimpleNamespace(
            public_guest_contact_enabled=enabled,
            session_cookie_secure=False,
            session_cookie_name="avtorinok_session",
        ),
    )


def _bootstrap_guest(client: TestClient) -> str:
    response = client.get("/api/v1/listings/public-capabilities")
    assert response.status_code == 200, response.text
    token = response.headers.get("x-guest-contact-token")
    assert token
    return token


def test_guest_contact_is_disabled_by_default_and_advertised_as_a_capability(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, False)
    client = _client(integration)

    capability = client.get("/api/v1/listings/public-capabilities")
    assert capability.status_code == 200, capability.text
    assert capability.json() == {"guest_contact_reveal_enabled": False}
    assert capability.headers["cache-control"] == "no-store"
    assert capability.headers.get("x-guest-contact-token") is None
    assert "avtorinok_guest_contact_proof" not in client.cookies
    assert "avtorinok_guest_contact_device" not in client.cookies

    denied = client.post(f"/api/v1/listings/{listing.id}/phone-reveal")
    assert denied.status_code == 401, denied.text
    with factory() as db:
        assert db.scalar(select(ContactReveal.id)) is None


def test_guest_can_reveal_only_by_post_and_contact_event_has_no_user_or_raw_ip(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration, "198.51.100.41")

    capability = client.get("/api/v1/listings/public-capabilities")
    assert capability.json() == {
        "guest_contact_reveal_enabled": True
    }
    token = capability.headers.get("x-guest-contact-token")
    assert token
    assert capability.headers.get("set-cookie")
    assert "httponly" in capability.headers["set-cookie"].lower()
    assert "samesite=strict" in capability.headers["set-cookie"].lower()
    public_detail = client.get(f"/api/v1/listings/{listing.id}")
    assert public_detail.status_code == 200, public_detail.text
    assert PHONE not in public_detail.text

    reveal = client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers={"X-Guest-Contact-Token": token},
    )
    assert reveal.status_code == 200, reveal.text
    assert reveal.json() == {"phone": PHONE}
    assert reveal.headers["cache-control"] == "no-store, private, max-age=0"
    assert reveal.headers["pragma"] == "no-cache"

    with factory() as db:
        event = db.scalar(select(ContactReveal))
        assert event is not None
        assert event.listing_id == listing.id
        assert event.user_id is None
        bucket_hashes = db.scalars(select(RateLimitBucket.key_hash)).all()
        assert len(bucket_hashes) == 3
        assert all(len(value) == 64 for value in bucket_hashes)
        assert all("198.51.100.41" not in value for value in bucket_hashes)


def test_public_capabilities_reuses_valid_guest_proof(integration, monkeypatch):
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration)
    clock = {"now": datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)}

    class ControlledDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            moment = clock["now"]
            return moment if tz is None else moment.astimezone(tz)

    monkeypatch.setattr(listings_api, "datetime", ControlledDatetime)

    first = client.get("/api/v1/listings/public-capabilities")
    first_proof = first.headers.get("x-guest-contact-token")
    first_device = client.cookies.get("avtorinok_guest_contact_device")
    assert first.status_code == 200, first.text
    assert first_proof
    assert client.cookies.get("avtorinok_guest_contact_proof") == first_proof
    assert first_device

    clock["now"] += timedelta(seconds=10)
    second = client.get("/api/v1/listings/public-capabilities")

    assert second.status_code == 200, second.text
    assert second.headers.get("x-guest-contact-token") == first_proof
    assert client.cookies.get("avtorinok_guest_contact_proof") == first_proof
    assert client.cookies.get("avtorinok_guest_contact_device") == first_device


def test_guest_contact_rejects_missing_paused_and_blocked_listings(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    paused = _add_listing(factory, owner.id, status="paused")
    blocked = _add_listing(factory, owner.id, status="blocked")
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration)
    token = _bootstrap_guest(client)

    missing = client.post(
        f"/api/v1/listings/{uuid.uuid4()}/phone-reveal",
        headers={"X-Guest-Contact-Token": token},
    )
    paused_response = client.post(
        f"/api/v1/listings/{paused.id}/phone-reveal",
        headers={"X-Guest-Contact-Token": token},
    )
    blocked_response = client.post(
        f"/api/v1/listings/{blocked.id}/phone-reveal",
        headers={"X-Guest-Contact-Token": token},
    )

    assert missing.status_code == 404
    assert paused_response.status_code == 404
    assert blocked_response.status_code == 404
    with factory() as db:
        assert db.scalar(select(ContactReveal.id)) is None
        assert db.scalar(select(RateLimitBucket.key_hash)) is None


def test_guest_contact_limits_by_ip_and_ignores_untrusted_forwarded_for(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    first = _add_listing(factory, owner.id)
    second = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_IP_LIMIT", 1)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_LISTING_LIMIT", 10)
    client = _client(integration, "198.51.100.42")
    token = _bootstrap_guest(client)

    first_reveal = client.post(
        f"/api/v1/listings/{first.id}/phone-reveal",
        headers={"X-Forwarded-For": "203.0.113.1", "X-Guest-Contact-Token": token},
    )
    second_reveal = client.post(
        f"/api/v1/listings/{second.id}/phone-reveal",
        headers={"X-Forwarded-For": "203.0.113.2", "X-Guest-Contact-Token": token},
    )

    assert first_reveal.status_code == 200, first_reveal.text
    assert second_reveal.status_code == 429, second_reveal.text


def test_guest_contact_limits_repeated_reveals_per_ip_and_listing(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    first = _add_listing(factory, owner.id)
    second = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_IP_LIMIT", 10)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_LISTING_LIMIT", 1)
    client = _client(integration, "198.51.100.43")
    token = _bootstrap_guest(client)

    first_reveal = client.post(f"/api/v1/listings/{first.id}/phone-reveal", headers={"X-Guest-Contact-Token": token})
    repeated_reveal = client.post(f"/api/v1/listings/{first.id}/phone-reveal", headers={"X-Guest-Contact-Token": token})
    other_listing = client.post(f"/api/v1/listings/{second.id}/phone-reveal", headers={"X-Guest-Contact-Token": token})

    assert first_reveal.status_code == 200, first_reveal.text
    assert repeated_reveal.status_code == 429, repeated_reveal.text
    assert other_listing.status_code == 200, other_listing.text


def test_guest_contact_limit_is_shared_per_listing_across_ips(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_IP_LIMIT", 10)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_LISTING_LIMIT", 1)

    first_visitor = _client(integration, "198.51.100.44")
    second_visitor = _client(integration, "198.51.100.45")
    first_token = _bootstrap_guest(first_visitor)
    second_token = _bootstrap_guest(second_visitor)
    first_reveal = first_visitor.post(f"/api/v1/listings/{listing.id}/phone-reveal", headers={"X-Guest-Contact-Token": first_token})
    second_reveal = second_visitor.post(f"/api/v1/listings/{listing.id}/phone-reveal", headers={"X-Guest-Contact-Token": second_token})

    assert first_reveal.status_code == 200, first_reveal.text
    assert second_reveal.status_code == 429, second_reveal.text


def test_authenticated_reveals_still_require_csrf_when_guest_mode_is_enabled(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    visitor = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": visitor.email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    path = f"/api/v1/listings/{listing.id}/phone-reveal"

    without_csrf = client.post(path)
    assert without_csrf.status_code == 403, without_csrf.text
    with_csrf = client.post(path, headers={"X-CSRF-Token": login.json()["csrf_token"]})
    assert with_csrf.status_code == 200, with_csrf.text
    assert with_csrf.json() == {"phone": PHONE}
    with factory() as db:
        event = db.scalar(select(ContactReveal))
        assert event is not None
        assert event.listing_id == listing.id
        assert event.user_id == visitor.id


def test_guest_simple_cross_site_post_cannot_consume_any_quota(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration)
    _bootstrap_guest(client)

    attack = client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers={"Origin": "https://attacker.example"},
    )

    assert attack.status_code == 403, attack.text
    assert attack.json()["code"] == "guest_contact_proof_required"
    with factory() as db:
        assert db.scalar(select(ContactReveal.id)) is None
        assert db.scalar(select(RateLimitBucket.key_hash)) is None


def test_guest_device_limit_stops_mass_reveals_across_listings_and_survives_bootstrap(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    first = _add_listing(factory, owner.id)
    second = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_IP_LIMIT", 10)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_DEVICE_LIMIT", 1)
    monkeypatch.setattr(listings_api, "GUEST_PHONE_REVEAL_LISTING_LIMIT", 10)
    client = _client(integration, "198.51.100.46")
    first_token = _bootstrap_guest(client)

    first_reveal = client.post(
        f"/api/v1/listings/{first.id}/phone-reveal",
        headers={"X-Guest-Contact-Token": first_token},
    )
    refreshed_token = _bootstrap_guest(client)
    second_reveal = client.post(
        f"/api/v1/listings/{second.id}/phone-reveal",
        headers={"X-Guest-Contact-Token": refreshed_token},
    )

    assert first_reveal.status_code == 200, first_reveal.text
    assert second_reveal.status_code == 429, second_reveal.text
    with factory() as db:
        assert db.scalar(select(func.count(ContactReveal.id))) == 1
        assert db.scalar(select(func.count(RateLimitBucket.key_hash))) == 3


@pytest.mark.parametrize("target", ["listing", "owner", "company"])
def test_guest_reveal_rechecks_listing_owner_and_company_after_rate_commits(integration, monkeypatch, target):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    company = Company(
        owner_id=owner.id,
        name="Guest phone test dealer",
        slug=f"guest-phone-{uuid.uuid4().hex[:12]}",
        unp=f"{uuid.uuid4().int % 1_000_000_000:09d}",
        address="Test address",
        phone=PHONE,
        status="approved",
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        company_id = company.id
    listing = _add_listing(factory, owner.id, company_id=company_id)
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration, "198.51.100.47")
    token = _bootstrap_guest(client)
    limits_committed = Event()
    resume_request = Event()
    consume = listings_api.consume_rate_limit

    def pause_after_global_limit_commit(db, namespace, subject, limit, period):
        consume(db, namespace, subject, limit, period)
        if namespace == "guest-phone-reveal-listing":
            limits_committed.set()
            assert resume_request.wait(5), "test did not release the API request"

    monkeypatch.setattr(listings_api, "consume_rate_limit", pause_after_global_limit_commit)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(
            client.post,
            f"/api/v1/listings/{listing.id}/phone-reveal",
            headers={"X-Guest-Contact-Token": token},
        )
        assert limits_committed.wait(5), "guest rate limits did not commit"
        with factory() as db:
            if target == "listing":
                db.get(Listing, listing.id).status = "paused"
            elif target == "owner":
                db.get(User, owner.id).status = "blocked"
            else:
                db.get(Company, company_id).status = "pending"
            db.commit()
        resume_request.set()
        response = request.result(timeout=5)

    assert response.status_code == 404, response.text
    with factory() as db:
        assert db.scalar(select(ContactReveal.id)) is None


@pytest.mark.parametrize("mutation", ["block_actor", "revoke_session", "expire_session"])
def test_authenticated_reveal_rechecks_actor_and_session_after_rate_commit(integration, monkeypatch, mutation):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    visitor = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    _enable_guest_contact(monkeypatch, True)
    client = _client(integration, "198.51.100.48")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": visitor.email, "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    raw_session = client.cookies.get("avtorinok_session")
    assert raw_session
    token_hash = secret_hash(raw_session)
    limits_committed = Event()
    resume_request = Event()
    consume = listings_api.consume_rate_limit

    def pause_after_account_limit_commit(db, namespace, subject, limit, period):
        consume(db, namespace, subject, limit, period)
        if namespace == "phone-reveal":
            limits_committed.set()
            assert resume_request.wait(5), "test did not release the authenticated API request"

    monkeypatch.setattr(listings_api, "consume_rate_limit", pause_after_account_limit_commit)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(
            client.post,
            f"/api/v1/listings/{listing.id}/phone-reveal",
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert limits_committed.wait(5), "authenticated reveal limit did not commit"
        with factory() as db:
            if mutation == "block_actor":
                db.get(User, visitor.id).status = "blocked"
            else:
                session = db.get(UserSession, token_hash)
                assert session is not None
                if mutation == "revoke_session":
                    session.revoked_at = datetime.now(timezone.utc)
                else:
                    session.expires_at = datetime.now(timezone.utc)
            db.commit()
        resume_request.set()
        response = request.result(timeout=5)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "invalid_session"
    with factory() as db:
        assert db.scalar(select(ContactReveal.id)) is None
