import importlib
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config as config_module
from app import services
from app.listing_validation_policy import (
    is_listing_year_allowed,
    listing_validation_policy,
    maximum_listing_year,
    minimum_required_photos,
)
from app.main import app


def _settings(**overrides):
    values = {
        "listing_year_min": 1886,
        "listing_future_new_years": 1,
        "minimum_photos_new": 1,
        "minimum_photos_used": 1,
        "minimum_photos_damaged": 1,
        "minimum_photos_parts": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _listing(**overrides):
    values = {
        "id": uuid4(),
        "make_id": None,
        "manual_make": "BMW",
        "model_id": None,
        "manual_model": "3 Series",
        "year": 2020,
        "mileage_km": 1000,
        "price_amount": Decimal("10000.00"),
        "contact_phone": "+375291234567",
        "description": "Complete listing description",
        "fuel": "petrol",
        "transmission": "automatic",
        "drive": "rear",
        "condition": "used",
        "region_id": uuid4(),
        "city_id": None,
        "manual_city": "Минск",
        "engine_volume_l": Decimal("2.0"),
        "generation_id": None,
        "damaged": False,
        "parts_only": False,
        "title": "BMW 3 Series",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _PhotoDb:
    def __init__(self, photos):
        self.photos = photos

    def scalars(self, _statement):
        return _ScalarRows(self.photos)


def test_default_policy_preserves_one_ready_photo_and_current_year_behavior():
    policy = listing_validation_policy(settings=_settings(), current_year=2026)

    assert policy == {
        "current_year": 2026,
        "listing_year_min": 1886,
        "new_year_max": 2027,
        "used_year_max": 2026,
        "minimum_photos": {"new": 1, "used": 1, "damaged": 1, "parts": 1},
        "maximum_photos": 30,
        "category_codes": [
            "cars", "trucks", "buses", "motorcycles", "special_equipment",
            "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires",
        ],
        "category_submission_requirements": {
            "cars": [], "trucks": ["vehicle_type"], "buses": ["vehicle_type"],
            "motorcycles": ["vehicle_type"], "special_equipment": ["equipment_type"],
            "agricultural_equipment": ["equipment_type"], "trailers": ["trailer_type"],
            "watercraft": ["watercraft_type"], "parts": ["part_group"],
            "wheels": ["diameter_in", "width_in", "bolt_holes", "pcd_mm"],
            "tires": ["width_mm", "profile_percent", "diameter_in", "season"],
        },
    }


def test_custom_photo_counts_respect_parts_then_damage_then_condition_precedence():
    settings = _settings(
        minimum_photos_new=4,
        minimum_photos_used=2,
        minimum_photos_damaged=3,
        minimum_photos_parts=5,
    )

    assert minimum_required_photos(_listing(condition="new"), settings=settings) == 4
    assert minimum_required_photos(_listing(condition="used"), settings=settings) == 2
    assert minimum_required_photos(_listing(condition="new", damaged=True), settings=settings) == 3
    assert minimum_required_photos(_listing(condition="new", damaged=True, parts_only=True), settings=settings) == 5
    assert minimum_required_photos(_listing(condition="used", parts_only=True), settings=settings) == 5


def test_only_new_listings_can_use_configured_next_year():
    settings = _settings(listing_year_min=1900, listing_future_new_years=1)
    new_listing = _listing(condition="new")
    used_listing = _listing(condition="used")

    assert maximum_listing_year(new_listing, settings=settings, current_year=2026) == 2027
    assert maximum_listing_year(used_listing, settings=settings, current_year=2026) == 2026
    assert is_listing_year_allowed(2027, new_listing, settings=settings, current_year=2026)
    assert not is_listing_year_allowed(2027, used_listing, settings=settings, current_year=2026)
    assert not is_listing_year_allowed(1899, used_listing, settings=settings, current_year=2026)


def test_minimum_year_must_not_exclude_used_listings_even_when_new_year_is_allowed():
    settings = _settings(listing_year_min=2026, listing_future_new_years=1)
    new_listing = _listing(condition="new")
    used_listing = _listing(condition="used")

    policy = listing_validation_policy(settings=settings, current_year=2026)

    assert policy["listing_year_min"] == 2026
    assert policy["new_year_max"] == 2027
    assert policy["used_year_max"] == 2026
    assert is_listing_year_allowed(2027, new_listing, settings=settings, current_year=2026)
    assert is_listing_year_allowed(2026, used_listing, settings=settings, current_year=2026)


def test_policy_rejects_minimum_year_above_current_used_year_maximum():
    with pytest.raises(ValueError, match="listing_year_min exceeds the current used-year maximum"):
        listing_validation_policy(settings=_settings(listing_year_min=2027), current_year=2026)


def test_settings_startup_rejects_minimum_year_above_current_used_year_maximum(monkeypatch):
    monkeypatch.setattr(config_module, "_current_utc_year", lambda: 2026, raising=False)

    with pytest.raises(ValidationError, match="listing_year_min exceeds the current used-year maximum"):
        config_module.Settings(_env_file=None, listing_year_min=2027, listing_future_new_years=1)


@pytest.mark.parametrize(
    "minimum_year,future_new_years",
    [(2026, 1), (2026, 0)],
)
def test_settings_startup_accepts_a_nonempty_year_range(monkeypatch, minimum_year, future_new_years):
    monkeypatch.setattr(config_module, "_current_utc_year", lambda: 2026, raising=False)

    settings = config_module.Settings(
        _env_file=None,
        listing_year_min=minimum_year,
        listing_future_new_years=future_new_years,
    )

    assert settings.listing_year_min == minimum_year


def test_public_policy_endpoint_fails_closed_when_minimum_exceeds_used_year_max(monkeypatch):
    policy_module = importlib.import_module("app.listing_validation_policy")

    class FixedDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 1, 1, tzinfo=tz)

    monkeypatch.setattr(policy_module, "datetime", FixedDateTime)
    monkeypatch.setattr(policy_module, "get_settings", lambda: _settings(listing_year_min=2027))
    response = TestClient(app, raise_server_exceptions=False).get("/api/v1/listing-validation-policy")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "listing_year_min" not in response.json()


@pytest.mark.parametrize(
    "overrides",
    [
        {"listing_year_min": 1885},
        {"listing_year_min": 2101},
        {"listing_future_new_years": 2},
        {"minimum_photos_new": 0},
        {"minimum_photos_parts": 31},
    ],
)
def test_invalid_policy_bounds_are_rejected(overrides):
    with pytest.raises(ValueError):
        listing_validation_policy(settings=_settings(**overrides), current_year=2026)


def test_processing_photos_do_not_satisfy_the_ready_photo_minimum(monkeypatch):
    monkeypatch.setattr(services, "get_settings", lambda: _settings(minimum_photos_used=2))
    listing = _listing()
    photos = [
        SimpleNamespace(status="ready"),
        SimpleNamespace(status="processing"),
    ]

    with pytest.raises(HTTPException) as captured:
        services.validate_listing_for_submit(_PhotoDb(photos), listing)

    assert captured.value.status_code == 422
    detail = captured.value.detail
    assert "photos" in detail["field_errors"]
    assert "2" in detail["field_errors"]["photos"]


def test_enough_ready_photos_pass_validation_even_when_photo_maximum_is_not_reached(monkeypatch):
    monkeypatch.setattr(services, "get_settings", lambda: _settings(minimum_photos_used=2))
    listing = _listing()
    photos = [SimpleNamespace(status="ready"), SimpleNamespace(status="ready")]

    services.validate_listing_for_submit(_PhotoDb(photos), listing)
