from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.listings import _apply_fields
from app.models import CatalogBodyVariant, CatalogGeneration, CatalogMake, CatalogModel, Listing, User
from app.schemas import ListingForm
from app.services import serialize_listing, serialize_listings, validate_listing_for_submit
from fastapi import HTTPException


@pytest.mark.parametrize("vin", ["!" * 17, "\u0410" * 17, "I" * 17])
def test_vin_rejects_non_vin_characters(vin):
    with pytest.raises(ValueError, match="VIN must contain 17 valid characters"):
        ListingForm(vin=vin)


def test_vin_accepts_seventeen_ascii_alphanumeric_characters_without_ioq():
    assert ListingForm(vin="1HGCM82633A004352").vin == "1HGCM82633A004352"


def test_contact_phone_is_returned_only_for_explicit_seller_serialization():
    owner_id = uuid4()
    phone = "+375291234567"
    listing = Listing(
        id=uuid4(),
        owner_id=owner_id,
        slug="listing-private-contact",
        status="draft",
        revision=1,
        title="Honda Civic",
        description="",
        contact_phone=phone,
        make_name_snapshot="Honda",
        model_name_snapshot="Civic",
        damaged=False,
        parts_only=False,
    )
    owner = SimpleNamespace(id=owner_id, display_name="Seller")

    class SessionStub:
        def get(self, model, _identity):
            return owner if model is User else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [])

    db = SessionStub()
    seller_view = serialize_listing(db, listing, public=False, include_contact=True)
    assert seller_view["contact_phone"] == phone
    seller_list_item = serialize_listings(db, [listing], public=False, include_contact=True)[0]
    assert seller_list_item["contact_phone"] == phone
    seller_bulk_items = serialize_listings(db, [listing, listing], public=False, include_contact=True)
    assert [item["contact_phone"] for item in seller_bulk_items] == [phone, phone]
    assert "contact_phone" not in serialize_listing(db, listing, public=False)
    assert "contact_phone" not in serialize_listing(db, listing, public=True)


def test_seller_listing_serialization_returns_generation_specific_body_variant():
    owner_id = uuid4()
    generation_id = uuid4()
    body_variant_id = uuid4()
    generation = CatalogGeneration(
        id=generation_id,
        model_id=uuid4(),
        slug="generation-2020",
        name="Generation 2020",
        year_from=2020,
        year_to=None,
    )
    body_variant = CatalogBodyVariant(
        id=body_variant_id,
        generation_id=generation_id,
        slug="sedan",
        name="Sedan",
        source_name="Catalog supplier",
        source_metadata={"supplier_record": "private-source-value"},
    )
    listing = Listing(
        id=uuid4(),
        owner_id=owner_id,
        slug="listing-body-variant",
        status="draft",
        revision=1,
        title="Honda Civic",
        description="",
        make_name_snapshot="Honda",
        model_name_snapshot="Civic",
        generation_id=generation_id,
        body_variant_id=body_variant_id,
        damaged=False,
        parts_only=False,
    )
    owner = SimpleNamespace(id=owner_id, display_name="Seller")

    class SessionStub:
        def get(self, model, _identity):
            return {
                User: owner,
                CatalogGeneration: generation,
                CatalogBodyVariant: body_variant,
            }.get(model)

        def scalars(self, statement):
            model = statement.column_descriptions[0]["entity"]
            records = {
                User: [owner],
                CatalogGeneration: [generation],
                CatalogBodyVariant: [body_variant],
            }
            return SimpleNamespace(all=lambda: records.get(model, []))

    db = SessionStub()
    serialized = serialize_listing(db, listing, public=False)

    assert serialized["body_variant_id"] == str(body_variant_id)
    assert serialized["body_variant"] == {
        "id": str(body_variant_id),
        "slug": "sedan",
        "name": "Sedan",
        "aliases": [],
        "generation_id": str(generation_id),
    }
    public_serialized = serialize_listing(db, listing, public=True)
    assert public_serialized["body_variant_id"] == str(body_variant_id)
    assert public_serialized["body_variant"] == serialized["body_variant"]
    assert "source_name" not in public_serialized["body_variant"]
    assert "source_metadata" not in public_serialized["body_variant"]
    second_listing = Listing(
        id=uuid4(),
        owner_id=owner_id,
        slug="listing-body-variant-2",
        status="draft",
        revision=1,
        title="Honda Civic 2",
        description="",
        make_name_snapshot="Honda",
        model_name_snapshot="Civic",
        generation_id=generation_id,
        body_variant_id=body_variant_id,
        damaged=False,
        parts_only=False,
    )
    serialized_batch = serialize_listings(db, [listing, second_listing], public=False)
    assert [item["body_variant_id"] for item in serialized_batch] == [str(body_variant_id), str(body_variant_id)]
    assert [item["body_variant"]["name"] for item in serialized_batch] == ["Sedan", "Sedan"]


def test_listing_serialization_omits_body_variant_from_another_generation():
    owner_id = uuid4()
    listing_generation = CatalogGeneration(
        id=uuid4(),
        model_id=uuid4(),
        slug="current-generation",
        name="Current Generation",
    )
    body_variant = CatalogBodyVariant(
        id=uuid4(),
        generation_id=uuid4(),
        slug="foreign-sedan",
        name="Foreign Sedan",
    )
    listing = Listing(
        id=uuid4(),
        owner_id=owner_id,
        slug="listing-foreign-body-variant",
        status="draft",
        revision=1,
        title="Honda Civic",
        description="",
        make_name_snapshot="Honda",
        model_name_snapshot="Civic",
        generation_id=listing_generation.id,
        body_variant_id=body_variant.id,
        damaged=False,
        parts_only=False,
    )
    owner = SimpleNamespace(id=owner_id, display_name="Seller")

    class SessionStub:
        def get(self, model, identity):
            return {
                (User, owner.id): owner,
                (CatalogGeneration, listing_generation.id): listing_generation,
                (CatalogBodyVariant, body_variant.id): body_variant,
            }.get((model, identity))

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [])

    serialized = serialize_listing(SessionStub(), listing, public=False)

    assert serialized["body_variant_id"] is None
    assert serialized["body_variant"] is None


def test_listing_update_rejects_body_variant_from_another_generation():
    make = CatalogMake(id=uuid4(), slug="honda", name="Honda")
    model = CatalogModel(id=uuid4(), make_id=make.id, slug="civic", name="Civic")
    generation = CatalogGeneration(
        id=uuid4(),
        model_id=model.id,
        slug="generation-2020",
        name="Generation 2020",
        year_from=2020,
        year_to=None,
    )
    body_variant = CatalogBodyVariant(
        id=uuid4(),
        generation_id=uuid4(),
        slug="sedan",
        name="Sedan",
    )
    listing = Listing(
        id=uuid4(),
        owner_id=uuid4(),
        slug="listing-wrong-body-variant-generation",
        status="draft",
        revision=1,
        title="Honda Civic",
        description="",
        make_id=make.id,
        model_id=model.id,
        generation_id=generation.id,
        damaged=False,
        parts_only=False,
    )

    class SessionStub:
        def get(self, model_type, identity):
            records = {
                (CatalogMake, make.id): make,
                (CatalogModel, model.id): model,
                (CatalogGeneration, generation.id): generation,
                (CatalogBodyVariant, body_variant.id): body_variant,
            }
            return records.get((model_type, identity))

    with pytest.raises(HTTPException) as exc:
        _apply_fields(
            SessionStub(),
            listing,
            {"body_variant_id": body_variant.id},
            SimpleNamespace(id=listing.owner_id),
            creating=False,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_catalog_reference"
    assert exc.value.detail["field_errors"]["body_variant_id"] == "Invalid body variant"


def test_submission_rejects_vehicle_year_outside_selected_generation():
    generation_id = uuid4()
    generation = CatalogGeneration(
        id=generation_id,
        model_id=uuid4(),
        slug="generation-2018-2022",
        name="Generation 2018-2022",
        year_from=2018,
        year_to=2022,
    )
    listing = Listing(
        id=uuid4(),
        owner_id=uuid4(),
        slug="listing-year-generation-check",
        status="draft",
        revision=1,
        title="Toyota Corolla 2017",
        description="Vehicle year and generation validation",
        contact_phone="+375291234567",
        manual_make="Toyota",
        manual_model="Corolla",
        generation_id=generation_id,
        year=2017,
        mileage_km=0,
        price_amount=Decimal("10000.00"),
        currency="BYN",
        fuel="petrol",
        transmission="manual",
        drive="front",
        condition="used",
        region_id=uuid4(),
        manual_city="Minsk",
        damaged=False,
        parts_only=False,
    )

    class SessionStub:
        def get(self, model, _identity):
            return generation if model is CatalogGeneration else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(status="ready")])

    with pytest.raises(HTTPException) as exc:
        validate_listing_for_submit(SessionStub(), listing)

    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "validation_error"
    assert "year" in exc.value.detail["field_errors"]
    assert "generation_id" in exc.value.detail["field_errors"]


def test_submission_accepts_vehicle_year_within_selected_generation():
    generation_id = uuid4()
    generation = CatalogGeneration(
        id=generation_id,
        model_id=uuid4(),
        slug="generation-2018-2022",
        name="Generation 2018-2022",
        year_from=2018,
        year_to=2022,
    )
    listing = Listing(
        id=uuid4(),
        owner_id=uuid4(),
        slug="listing-year-generation-valid",
        status="draft",
        revision=1,
        title="Toyota Corolla 2020",
        description="Vehicle year and generation validation",
        contact_phone="+375291234567",
        manual_make="Toyota",
        manual_model="Corolla",
        generation_id=generation_id,
        year=2020,
        mileage_km=0,
        price_amount=Decimal("10000.00"),
        currency="BYN",
        fuel="petrol",
        transmission="manual",
        drive="front",
        condition="used",
        region_id=uuid4(),
        manual_city="Minsk",
        damaged=False,
        parts_only=False,
    )

    class SessionStub:
        def get(self, model, _identity):
            return generation if model is CatalogGeneration else None

        def scalars(self, _statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(status="ready")])

    validate_listing_for_submit(SessionStub(), listing)
