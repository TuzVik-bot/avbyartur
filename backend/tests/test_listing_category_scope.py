from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    Company,
    ExchangeRate,
    Listing,
    ListingCategoryDetails,
    ListingPhoto,
    ListingStatusEvent,
    User,
)


@pytest.fixture
def category_scope_api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__, Company.__table__, Listing.__table__,
            ListingCategoryDetails.__table__, ListingPhoto.__table__,
            ExchangeRate.__table__, ListingStatusEvent.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield {"client": client, "engine": engine, "SessionLocal": factory}
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        engine.dispose()


def _add_listing(db, owner: User, category_code: str) -> Listing:
    listing = Listing(
        owner_id=owner.id,
        slug=f"category-scope-{category_code}-{uuid4().hex}",
        status="active",
        category_code=category_code,
        revision=1,
        title=f"{category_code} listing",
        description="",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        price_amount=Decimal("10000.00"),
        currency="BYN",
    )
    db.add(listing)
    db.flush()
    return listing


def test_cars_search_count_and_legacy_saved_search_are_category_scoped(category_scope_api):
    from app.notification_service import saved_search_matches

    factory = category_scope_api["SessionLocal"]
    with factory() as db:
        owner = User(
            email=f"category-scope-{uuid4().hex}@example.com",
            display_name="Seller",
            password_hash="unused",
            role="user",
            status="active",
        )
        db.add(owner)
        db.flush()
        car = _add_listing(db, owner, "cars")
        truck = _add_listing(db, owner, "trucks")
        truck.category_details = ListingCategoryDetails(
            category_code="trucks", details={"vehicle_type": "tractor_unit"}
        )
        db.commit()
        car_id, truck_id = str(car.id), str(truck.id)

        legacy_saved_search = SimpleNamespace(search_url="/cars")
        assert saved_search_matches(db, legacy_saved_search, car) is True
        assert saved_search_matches(db, legacy_saved_search, truck) is False

        explicit_truck_search = SimpleNamespace(
            search_url="/cars?category_code=trucks"
        )
        assert saved_search_matches(db, explicit_truck_search, truck) is True
        assert saved_search_matches(db, explicit_truck_search, car) is False

    client = category_scope_api["client"]
    cars_response = client.get("/api/v1/listings")
    cars_count = client.get("/api/v1/listings/count")
    assert cars_response.status_code == 200, cars_response.text
    assert cars_count.status_code == 200, cars_count.text
    assert [item["id"] for item in cars_response.json()["items"]] == [car_id]
    assert cars_count.json() == {"total": 1}

    trucks_response = client.get(
        "/api/v1/listings", params={"category_code": "trucks"}
    )
    trucks_count = client.get(
        "/api/v1/listings/count", params={"category_code": "trucks"}
    )
    assert trucks_response.status_code == 200, trucks_response.text
    assert trucks_count.status_code == 200, trucks_count.text
    assert [item["id"] for item in trucks_response.json()["items"]] == [truck_id]
    assert trucks_count.json() == {"total": 1}

    subtype_params = {"category_code": "trucks", "subtype": "tractor_unit"}
    subtype_response = client.get("/api/v1/listings", params=subtype_params)
    subtype_count = client.get("/api/v1/listings/count", params=subtype_params)
    assert subtype_response.status_code == 200, subtype_response.text
    assert subtype_count.status_code == 200, subtype_count.text
    assert [item["id"] for item in subtype_response.json()["items"]] == [truck_id]
    assert subtype_count.json() == {"total": 1}

    details_params = {
        "category_code": "trucks",
        "details": '{"vehicle_type":"tractor_unit"}',
    }
    details_response = client.get("/api/v1/listings", params=details_params)
    details_count = client.get("/api/v1/listings/count", params=details_params)
    assert details_response.status_code == 200, details_response.text
    assert details_count.status_code == 200, details_count.text
    assert [item["id"] for item in details_response.json()["items"]] == [truck_id]
    assert details_count.json() == {"total": 1}


def test_search_filters_accept_only_supported_explicit_categories():
    from pydantic import ValidationError

    from app.listing_schemas import ListingSearchFilters

    assert ListingSearchFilters(category_code="trucks").category_code == "trucks"

    with pytest.raises(ValidationError, match="category_code"):
        ListingSearchFilters(category_code="aircraft")
