import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models import (
    AuditEvent,
    Base,
    Company,
    DealerTeamMember,
    ExchangeRate,
    Listing,
    ListingCategoryDetails,
    ListingStatusEvent,
    RateLimitBucket,
    User,
    UserSession,
)
from app.security import hash_password

PASSWORD = "valuation-test-password-123"

MAKE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "valuation-make")
MODEL_ID = uuid.uuid5(uuid.NAMESPACE_URL, "valuation-model")
BODY_TYPE_ID = uuid.uuid5(uuid.NAMESPACE_URL, "valuation-body")


@pytest.fixture
def valuation_api():
    import os

    from app.config import get_settings

    previous_env = {key: os.environ.get(key) for key in ("SESSION_COOKIE_SECURE", "SESSION_SECRET", "APP_ENV")}
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["SESSION_SECRET"] = "valuation-test-secret-with-over-32-characters!"
    os.environ["APP_ENV"] = "development"
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            UserSession.__table__,
            RateLimitBucket.__table__,
            Company.__table__,
            DealerTeamMember.__table__,
            AuditEvent.__table__,
            Listing.__table__,
            ListingCategoryDetails.__table__,
            ListingStatusEvent.__table__,
            ExchangeRate.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    previous_override = app.dependency_overrides.get("get_db")
    from app.db import get_db

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield {"client": client, "factory": factory}
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        engine.dispose()
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def add_owner(db, index: int) -> User:
    owner = User(
        email=f"valuation-seller-{index}-{uuid.uuid4().hex[:6]}@example.com",
        display_name=f"Seller {index}",
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    db.add(owner)
    db.flush()
    return owner


def add_cohort_listing(
    db,
    owner: User,
    amount: str,
    *,
    mileage: int = 100_000,
    year: int = 2020,
    generation_id=None,
) -> Listing:
    listing = Listing(
        owner_id=owner.id,
        slug=f"valuation-{uuid.uuid4().hex}",
        status="active",
        revision=1,
        title="Valuation cohort car",
        make_id=MAKE_ID,
        model_id=MODEL_ID,
        generation_id=generation_id,
        body_type_id=BODY_TYPE_ID,
        year=year,
        mileage_km=mileage,
        fuel="petrol",
        transmission="manual",
        condition="used",
        damaged=False,
        parts_only=False,
        description="",
        contact_phone="+375291234567",
        price_amount=Decimal(amount),
        currency="BYN",
    )
    db.add(listing)
    db.flush()
    return listing


def valuation_params(**overrides):
    params = {
        "make_id": str(MAKE_ID),
        "model_id": str(MODEL_ID),
        "body_type_id": str(BODY_TYPE_ID),
        "year": 2020,
        "mileage_km": 100_000,
        "condition": "used",
        "fuel": "petrol",
        "transmission": "manual",
    }
    params.update(overrides)
    return params


def test_public_valuation_high_confidence_from_full_cohort(valuation_api):
    factory = valuation_api["factory"]
    with factory() as db:
        owners = [add_owner(db, index) for index in range(5)]
        for index in range(12):
            add_cohort_listing(db, owners[index % 5], "10000.00")
        add_cohort_listing(db, owners[0], "12000.00")
        add_cohort_listing(db, owners[1], "8000.00", mileage=150_000)
        db.commit()

    response = valuation_api["client"].get(
        "/api/v1/market/valuation", params=valuation_params()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "high"
    assert body["median_byn"] == "10000.00"
    # The 150_000 km listing is excluded by the +-10% mileage tolerance.
    assert body["sample_size"] == 13
    assert body["seller_count"] == 5
    assert (
        Decimal(body["p25_byn"])
        <= Decimal(body["median_byn"])
        <= Decimal(body["p75_byn"])
    )


def test_public_valuation_low_confidence_on_small_cohort(valuation_api):
    factory = valuation_api["factory"]
    with factory() as db:
        owners = [add_owner(db, index) for index in range(3)]
        for index in range(4):
            add_cohort_listing(db, owners[index % 3], "10000.00")
        db.commit()

    response = valuation_api["client"].get(
        "/api/v1/market/valuation", params=valuation_params()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "low"
    assert body["median_byn"] == "10000.00"
    assert body["sample_size"] == 4
    assert body["seller_count"] == 3


def test_public_valuation_reports_none_without_data(valuation_api):
    response = valuation_api["client"].get(
        "/api/v1/market/valuation", params=valuation_params()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "none"
    assert body["median_byn"] is None
    assert body["sample_size"] == 0


def test_public_valuation_requires_fresh_rate_for_usd_mix(valuation_api):
    factory = valuation_api["factory"]
    with factory() as db:
        owners = [add_owner(db, index) for index in range(5)]
        for index in range(10):
            add_cohort_listing(db, owners[index % 5], "10000.00")
        stale = Listing(
            owner_id=owners[0].id,
            slug=f"valuation-usd-{uuid.uuid4().hex}",
            status="active",
            revision=1,
            title="USD cohort car",
            make_id=MAKE_ID,
            model_id=MODEL_ID,
            body_type_id=BODY_TYPE_ID,
            year=2020,
            mileage_km=100_000,
            fuel="petrol",
            transmission="manual",
            condition="used",
            price_amount=Decimal("4000.00"),
            currency="USD",
            description="",
            contact_phone="",
        )
        db.add(stale)
        db.add(
            ExchangeRate(
                currency="USD",
                rate_date=(datetime.now(UTC) - timedelta(days=30))
                .date()
                .isoformat(),
                official_rate=Decimal("3.000000"),
                scale=1,
                source="test",
                fetched_at=datetime.now(UTC) - timedelta(days=30),
            )
        )
        db.commit()

    response = valuation_api["client"].get(
        "/api/v1/market/valuation", params=valuation_params()
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unsupported_rate"


def test_market_price_estimate_serves_authenticated_seller(valuation_api):
    factory = valuation_api["factory"]
    with factory() as db:
        owners = [add_owner(db, index) for index in range(5)]
        for index in range(10):
            add_cohort_listing(db, owners[index % 5], "10000.00")
        seller = User(
            email=f"estimate-seller-{uuid.uuid4().hex[:6]}@example.com",
            display_name="Estimate seller",
            password_hash=hash_password(PASSWORD),
            role="user",
            status="active",
        )
        db.add(seller)
        db.commit()
        seller_email = seller.email

    client = valuation_api["client"]
    login = client.post(
        "/api/v1/auth/login", json={"email": seller_email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    csrf = login.json()["csrf_token"]

    response = client.post(
        "/api/v1/listings/market-price-estimate",
        json={
            "seller_type": "private",
            "make_id": str(MAKE_ID),
            "model_id": str(MODEL_ID),
            "body_type_id": str(BODY_TYPE_ID),
            "year": 2020,
            "mileage_km": 100_000,
            "condition": "used",
            "fuel": "petrol",
            "transmission": "manual",
            "damaged": False,
            "parts_only": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["median_byn"] == "10000.00"
    assert body["sample_size"] == 10

    anonymous = valuation_api["client"].post(
        "/api/v1/listings/market-price-estimate",
        json={
            "seller_type": "private",
            "make_id": str(MAKE_ID),
            "model_id": str(MODEL_ID),
            "body_type_id": str(BODY_TYPE_ID),
            "year": 2020,
            "mileage_km": 100_000,
            "condition": "used",
            "fuel": "petrol",
            "transmission": "manual",
        },
    )
    # The CSRF gate rejects an anonymous POST before authentication.
    assert anonymous.status_code == 403
