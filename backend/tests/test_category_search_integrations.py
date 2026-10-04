"""Category boundaries across public search, subscriptions and dealer feeds."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import models
from app.api.saved_searches import SavedSearchCreate, _normalise_filters, _validate_category_pair
from app.category_search import detail_filters
from app.feed_schemas import DealerFeedRecord
from app.feed_services import _normalized_record, parse_feed_bytes
from app.listing_change_audit import snapshot_listing_fields
from app.main import app
from app.notification_service import saved_search_email_content, saved_search_matches


def test_old_saved_search_matches_only_cars_even_without_filters():
    saved = SimpleNamespace(filters={})
    assert saved_search_matches(None, saved, models.Listing(category_code="cars"))
    assert not saved_search_matches(None, saved, models.Listing(category_code="tires"))


def test_non_car_saved_search_matches_only_its_category_and_details():
    saved = SimpleNamespace(filters={"category_code": "tires", "details": {"width_mm": 205, "season": "winter"}})
    matching = models.Listing(category_code="tires")
    matching.category_details = models.ListingCategoryDetails(category_code="tires", details={"width_mm": 205, "season": "winter"})
    assert saved_search_matches(None, saved, matching)
    assert not saved_search_matches(None, saved, models.Listing(category_code="cars"))
    matching.category_details.details = {"width_mm": 215, "season": "winter"}
    assert not saved_search_matches(None, saved, matching)


def test_saved_search_category_url_and_filter_contract():
    assert SavedSearchCreate(name="Cars", url="/cars", filters={}).url == "/cars"
    assert SavedSearchCreate(
        name="Machines", url="/special-equipment?category_code=special_equipment",
        filters={"category_code": "special_equipment"},
    ).url.startswith("/special-equipment")
    with pytest.raises(ValueError):
        SavedSearchCreate(name="Wrong", url="/cars?category_code=tires", filters={"category_code": "tires"})
    with pytest.raises(ValueError):
        _normalise_filters({"category_code": "cars", "details": {"season": "winter"}})
    _validate_category_pair(
        "/tires?category_code=tires&width_mm=205",
        {"category_code": "tires", "width_mm": "205"},
    )
    with pytest.raises(ValueError):
        _validate_category_pair("/tires?category_code=tires", {})


def test_notification_link_cannot_point_to_another_category():
    with pytest.raises(ValueError, match="invalid_notification_url"):
        saved_search_email_content(
            {"url": "/tires?category_code=cars", "body": "Tires"},
            "https://cars.example.test",
        )
    _, body = saved_search_email_content(
        {"url": "/tires?category_code=tires", "body": "Tires"},
        "https://cars.example.test",
    )
    assert "https://cars.example.test/tires?category_code=tires" in body
    for invalid in ("https://phishing.example/", "//phishing.example/", "cars?q=audi", "/unknown"):
        with pytest.raises(ValueError, match="invalid_notification_url"):
            saved_search_email_content({"url": invalid}, "https://cars.example.test")


def test_details_filter_validates_every_category_field():
    assert detail_filters("trucks", {"details": '{"payload_kg":18500,"axle_configuration":"6x4"}'}) == {
        "payload_kg": 18500, "axle_configuration": "6x4"
    }
    with pytest.raises(ValueError):
        detail_filters("trucks", {"details": {"season": "winter"}})


def test_subtype_dictionary_exposes_only_internal_codes():
    response = TestClient(app).get("/api/v1/catalog/category-subtypes?category_code=trucks")
    assert response.status_code == 200
    assert response.json() == {
        "category_code": "trucks", "field": "vehicle_type", "entry_mode": "codes",
        "items": [{"code": code} for code in ("truck", "tractor_unit", "van", "other")],
    }
    manual = TestClient(app).get("/api/v1/catalog/category-subtypes?category_code=parts")
    assert manual.json() == {"category_code": "parts", "field": "part_group", "entry_mode": "manual", "items": []}


def test_dealer_feed_keeps_legacy_cars_and_requires_explicit_new_category():
    assert _normalized_record({"dealer_external_id": "legacy-1"})[1].category_code == "cars"
    with pytest.raises(ValueError):
        DealerFeedRecord.model_validate({"dealer_external_id": "tire-1", "category_code": "tires"})
    external_id, form, _, source_fields = _normalized_record({
        "dealer_external_id": "tire-1", "category_code": "tires",
        "category_details": {"category_code": "tires", "details": {"width_mm": 205, "profile_percent": 55, "diameter_in": 16, "season": "winter"}},
    })
    assert external_id == "tire-1"
    assert form.category_code == "tires"
    assert "category_details" in source_fields


def test_csv_feed_accepts_json_category_details():
    rows = parse_feed_bytes(
        b'dealer_external_id,category_code,category_details\ntire-1,tires,"{""category_code"":""tires"",""details"":{""width_mm"":205}}"\n',
        feed_format="csv", field_mapping=None,
    )
    assert rows[0]["values"]["category_details"]["details"] == {"width_mm": 205}


def test_edit_history_snapshots_category_and_sanitizes_details():
    listing = models.Listing(category_code="parts", title="Part", description="", contact_phone="")
    listing.category_details = models.ListingCategoryDetails(category_code="parts", details={"part_group": "Filters", "compatibility": "help@example.test"})
    snapshot = snapshot_listing_fields(None, listing)
    assert snapshot.fields["category_code"] == "parts"
    assert snapshot.fields["category_details"] == {"part_group": "Filters", "compatibility": "[email]"}


def test_public_search_isolated_by_category(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        owner = models.User(email="category-search-owner@example.test", display_name="Owner", status="active")
        db.add(owner)
        db.flush()
        for code in ("cars", "tires"):
            listing = models.Listing(owner_id=owner.id, slug=f"category-search-{code}", status="active", revision=1,
                category_code=code, title="Winter", description="", contact_phone="", damaged=False, parts_only=False)
            if code == "tires":
                listing.manual_make = "ManualTireBrand"
                listing.manual_model = "ManualTireModel"
                listing.category_details = models.ListingCategoryDetails(category_code=code, details={"width_mm": 205, "season": "winter"})
            db.add(listing)
        db.commit()
    client = TestClient(app)
    cars = client.get("/api/v1/listings")
    tires = client.get("/api/v1/listings?category_code=tires&details=%7B%22width_mm%22%3A205%7D")
    assert cars.status_code == tires.status_code == 200
    assert cars.json()["pagination"]["total"] == tires.json()["pagination"]["total"] == 1
    assert cars.json()["items"][0]["category_code"] == "cars"
    assert tires.json()["items"][0]["category_code"] == "tires"
    manual = client.get("/api/v1/listings?category_code=tires&q=ManualTireBrand")
    assert manual.status_code == 200
    assert manual.json()["pagination"]["total"] == 1
