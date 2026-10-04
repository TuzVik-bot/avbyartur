import pytest
from fastapi import HTTPException
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from pydantic import ValidationError


def test_category_details_accepts_truck_capacity_and_rejects_unknown_fields():
    from app.listing_categories import ListingCategoryDetailsInput

    details = ListingCategoryDetailsInput.model_validate(
        {
            "category_code": "trucks",
            "details": {
                "vehicle_type": "tractor_unit",
                "payload_kg": 18_500,
                "gross_weight_kg": 44_000,
                "axle_configuration": "6x4",
            },
        }
    )

    assert details.category_code == "trucks"
    assert details.details["payload_kg"] == 18_500

    with pytest.raises(ValidationError):
        ListingCategoryDetailsInput.model_validate(
            {
                "category_code": "trucks",
                "details": {"payload_kg": -1, "unexpected": "value"},
            }
        )


def test_category_details_must_match_its_listing_category():
    from app.schemas import ListingForm

    with pytest.raises(ValidationError):
        ListingForm.model_validate(
            {
                "category_code": "tires",
                "category_details": {
                    "category_code": "trucks",
                    "details": {"payload_kg": 1_000},
                },
            }
        )


def test_legacy_listing_form_defaults_to_cars_and_preserves_explicit_category():
    from app.schemas import ListingForm

    assert ListingForm().category_code == "cars"
    assert ListingForm(category_code="watercraft").category_code == "watercraft"


def test_category_change_requires_confirmation_and_replaces_incompatible_details():
    from app.api.listings import _apply_fields
    from app.models import Listing, ListingCategoryDetails

    class Db:
        def get(self, _model, _identity):
            return None

    listing = Listing(
        category_code="cars",
        make_id=uuid4(),
        model_id=uuid4(),
        generation_id=uuid4(),
        body_type_id=uuid4(),
        body_variant_id=uuid4(),
        modification_id=uuid4(),
        manual_make="BMW",
        manual_model="3 Series",
        make_name_snapshot="BMW",
        model_name_snapshot="3 Series",
        generation_name_snapshot="G20",
        fuel="petrol",
        transmission="automatic",
        drive="rear",
        engine_volume_l=2,
        power_hp=258,
        vin="1HGCM82633A004352",
        equipment=["abs"],
    )
    listing.category_details = ListingCategoryDetails(category_code="cars", details={})

    with pytest.raises(HTTPException) as exc:
        _apply_fields(Db(), listing, {"category_code": "trucks"}, None, creating=False)

    assert exc.value.detail["code"] == "category_change_confirmation_required"

    _apply_fields(
        Db(),
        listing,
        {
            "category_code": "trucks",
            "confirm_category_change": True,
            "category_details": {
                "category_code": "trucks",
                "details": {"payload_kg": 18_500},
            },
        },
        None,
        creating=False,
    )

    assert listing.category_code == "trucks"
    assert listing.category_details.category_code == "trucks"
    assert listing.category_details.details == {"payload_kg": 18_500}
    for field in (
        "make_id", "model_id", "generation_id", "body_type_id", "body_variant_id",
        "modification_id", "manual_make", "manual_model", "make_name_snapshot",
        "model_name_snapshot", "generation_name_snapshot", "fuel", "transmission",
        "drive", "engine_volume_l", "power_hp", "vin", "equipment",
    ):
        assert getattr(listing, field) is None


def test_category_details_use_a_database_foreign_key_for_listing_category_match():
    from app.models import Listing, ListingCategoryDetails

    foreign_keys = ListingCategoryDetails.__table__.foreign_key_constraints
    assert any(
        {element.parent.name for element in constraint.elements} == {"listing_id", "category_code"}
        and {element.column.name for element in constraint.elements} == {"id", "category_code"}
        and constraint.referred_table is Listing.__table__
        for constraint in foreign_keys
    )


def test_listing_patch_does_not_replace_category_when_category_is_omitted():
    from app.schemas import ListingPatch

    payload = ListingPatch(expected_revision=4, title="Updated title")

    assert "category_code" not in payload.model_dump(exclude_unset=True)


def test_parts_submission_keeps_common_rules_without_car_only_requirements(monkeypatch):
    from app import services

    monkeypatch.setattr(
        services,
        "get_settings",
        lambda: SimpleNamespace(
            listing_year_min=1886,
            listing_future_new_years=1,
            minimum_photos_new=1,
            minimum_photos_used=1,
            minimum_photos_damaged=1,
            minimum_photos_parts=1,
        ),
    )

    listing = SimpleNamespace(
        id=uuid4(),
        category_code="parts",
        category_details=SimpleNamespace(
            category_code="parts",
            details={"part_group": "engine", "quantity": 1},
        ),
        title="Engine assembly",
        description="Used engine assembly in working condition",
        contact_phone="+375291234567",
        price_amount=Decimal("1000.00"),
        condition="used",
        region_id=uuid4(),
        city_id=None,
        manual_city="Минск",
        damaged=False,
        parts_only=False,
        year=None,
        mileage_km=None,
        make_id=None,
        model_id=None,
        manual_make=None,
        manual_model=None,
        fuel=None,
        transmission=None,
        drive=None,
        engine_volume_l=None,
        generation_id=None,
    )

    class Db:
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(status="ready")])

    services.validate_listing_for_submit(Db(), listing)


def test_transport_submit_requires_make_model_year_and_category_minimum(monkeypatch):
    from app import services

    monkeypatch.setattr(
        services,
        "get_settings",
        lambda: SimpleNamespace(
            listing_year_min=1886,
            listing_future_new_years=1,
            minimum_photos_new=1,
            minimum_photos_used=1,
            minimum_photos_damaged=1,
            minimum_photos_parts=1,
        ),
    )
    listing = SimpleNamespace(
        id=uuid4(),
        category_code="trucks",
        category_details=SimpleNamespace(category_code="trucks", details={}),
        title="Truck",
        description="Truck for sale",
        contact_phone="+375291234567",
        price_amount=Decimal("1000.00"),
        condition="used",
        region_id=uuid4(),
        city_id=None,
        manual_city="Минск",
        damaged=False,
        parts_only=False,
        year=None,
        mileage_km=None,
        make_id=None,
        model_id=None,
        manual_make=None,
        manual_model=None,
        fuel=None,
        transmission=None,
        drive=None,
        engine_volume_l=None,
        generation_id=None,
    )

    class Db:
        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(status="ready")])

    with pytest.raises(HTTPException) as exc:
        services.validate_listing_for_submit(Db(), listing)

    errors = exc.value.detail["field_errors"]
    assert {"make_id", "model_id", "year", "category_details.vehicle_type"} <= errors.keys()


@pytest.mark.parametrize(
    ("category_code", "details"),
    [
        ("cars", {}),
        ("trucks", {"vehicle_type": "truck"}),
        ("buses", {"vehicle_type": "bus"}),
        ("motorcycles", {"vehicle_type": "motorcycle"}),
        ("special_equipment", {"equipment_type": "excavator"}),
        ("agricultural_equipment", {"equipment_type": "tractor"}),
        ("trailers", {"trailer_type": "flatbed"}),
        ("watercraft", {"watercraft_type": "boat"}),
        ("parts", {"part_group": "engine"}),
        ("wheels", {"diameter_in": 17, "width_in": 7.5, "bolt_holes": 5, "pcd_mm": 114.3}),
        ("tires", {"width_mm": 225, "profile_percent": 45, "diameter_in": 17, "season": "summer"}),
    ],
)
def test_each_category_has_a_minimum_submit_details_contract(category_code, details):
    from app.listing_categories import category_submission_errors

    assert category_submission_errors(category_code, details) == {}


@pytest.mark.parametrize(
    "category_code",
    [
        "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment",
        "trailers", "watercraft", "parts", "wheels", "tires",
    ],
)
def test_non_car_category_rejects_missing_submit_details(category_code):
    from app.listing_categories import category_submission_errors

    assert category_submission_errors(category_code, {})


@pytest.mark.parametrize(
    ("category_code", "details"),
    [
        ("wheels", {"diameter_in": 0}),
        ("tires", {"width_mm": 0}),
    ],
)
def test_required_wheel_and_tire_dimensions_must_be_positive(category_code, details):
    from app.listing_categories import ListingCategoryDetailsInput

    with pytest.raises(ValidationError):
        ListingCategoryDetailsInput(category_code=category_code, details=details)


@pytest.mark.parametrize(
    ("category_code", "details"),
    [
        ("wheels", {"diameter_in": 0, "width_in": 7.5, "bolt_holes": 5, "pcd_mm": 114.3}),
        ("tires", {"width_mm": 225, "profile_percent": 45, "diameter_in": 0, "season": "summer"}),
    ],
)
def test_submit_rejects_non_positive_stored_required_dimensions(category_code, details):
    from app.listing_categories import category_submission_errors

    assert category_submission_errors(category_code, details)
