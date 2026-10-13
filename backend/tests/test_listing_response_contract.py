from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.main import app
from app.models import Listing, User
from app.services import serialize_listing

UNSAFE_PUBLIC_PROPERTIES = {"contact_phone", "phone", "vin", "moderation_reason"}


def _component(openapi: dict, reference: str) -> dict:
    prefix = "#/components/schemas/"
    assert reference.startswith(prefix)
    return openapi["components"]["schemas"][reference.removeprefix(prefix)]


def _all_property_names(
    openapi: dict, schema: dict, seen: set[str] | None = None
) -> set[str]:
    seen = seen or set()
    reference = schema.get("$ref")
    if reference:
        if reference in seen:
            return set()
        seen.add(reference)
        return _all_property_names(openapi, _component(openapi, reference), seen)

    names = set(schema.get("properties", {}))
    for value in schema.get("properties", {}).values():
        names.update(_all_property_names(openapi, value, seen))
    for keyword in ("items", "anyOf", "oneOf", "allOf"):
        value = schema.get(keyword)
        if isinstance(value, dict):
            names.update(_all_property_names(openapi, value, seen))
        elif isinstance(value, list):
            for item in value:
                names.update(_all_property_names(openapi, item, seen))
    return names


def test_public_listing_search_documents_typed_listing_items() -> None:
    openapi = app.openapi()
    response = openapi["paths"]["/api/v1/listings"]["get"]["responses"]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/ListingSearchOut"
    search_schema = _component(openapi, response_schema["$ref"])
    assert search_schema["properties"]["items"]["type"] == "array"
    item_schema = search_schema["properties"]["items"]["items"]
    assert item_schema["$ref"] == "#/components/schemas/ListingPublicOut"
    assert (
        search_schema["properties"]["pagination"]["$ref"]
        == "#/components/schemas/ListingPaginationOut"
    )

    public_properties = _all_property_names(openapi, item_schema)
    assert UNSAFE_PUBLIC_PROPERTIES.isdisjoint(public_properties)
    listing_schema = _component(openapi, item_schema["$ref"])
    updated_at = listing_schema["properties"]["updated_at"]
    assert updated_at["type"] == "string"
    assert updated_at["format"] == "date-time"
    assert "updated_at" in listing_schema["required"]


def test_public_listing_contract_includes_publication_and_market_fields_and_count_route() -> None:
    openapi = app.openapi()
    listing_schema = _component(openapi, "#/components/schemas/ListingPublicOut")

    published_at = listing_schema["properties"]["published_at"]
    published_variants = published_at.get("anyOf", [published_at])
    published_timestamp = next(variant for variant in published_variants if variant.get("type") == "string")
    assert published_timestamp["format"] == "date-time"
    price_property = listing_schema["properties"]["price"]
    price_ref = price_property.get("$ref") or next(
        variant["$ref"] for variant in price_property.get("anyOf", []) if "$ref" in variant
    )
    price_schema = _component(openapi, price_ref)
    assert "market_comparison" in price_schema["properties"]
    comparison = price_schema["properties"]["market_comparison"]
    comparison_variants = comparison.get("anyOf", [comparison])
    assert any(variant.get("type") == "null" for variant in comparison_variants)
    comparison_ref = next(variant["$ref"] for variant in comparison_variants if "$ref" in variant)
    comparison_schema = _component(openapi, comparison_ref)
    assert comparison_schema["properties"]["label"]["enum"] == ["below_market", "above_market"]
    assert comparison_schema["properties"]["median_byn"]["type"] == "string"
    assert comparison_schema["properties"]["sample_size"]["type"] == "integer"
    assert comparison_schema["properties"]["seller_count"]["type"] == "integer"
    assert comparison_schema["properties"]["as_of"]["format"] == "date-time"
    rate_date_variants = comparison_schema["properties"]["rate_date"].get("anyOf", [])
    assert any(variant.get("type") == "string" for variant in rate_date_variants)
    assert any(variant.get("type") == "null" for variant in rate_date_variants)

    count_response = openapi["paths"]["/api/v1/listings/count"]["get"]["responses"]["200"]
    count_schema = _component(
        openapi, count_response["content"]["application/json"]["schema"]["$ref"]
    )
    assert count_schema["properties"]["total"]["type"] == "integer"
    listing_parameters = {
        parameter["name"] for parameter in openapi["paths"]["/api/v1/listings"]["get"]["parameters"]
    }
    count_parameters = {
        parameter["name"] for parameter in openapi["paths"]["/api/v1/listings/count"]["get"]["parameters"]
    }
    assert count_parameters == listing_parameters
    listing_route_order = list(openapi["paths"])
    assert listing_route_order.index("/api/v1/listings/count") < listing_route_order.index(
        "/api/v1/listings/{listing_id}"
    )


def test_public_listing_search_and_detail_return_updated_at(integration) -> None:
    factory = integration["SessionLocal"]
    owner_id = uuid4()
    listing_id = uuid4()
    updated_at = datetime.now(UTC).replace(microsecond=456789)
    created_at = updated_at - timedelta(days=2)
    title = f"Timestamp Regression {uuid4().hex[:8]}"
    with factory() as db:
        db.add(User(
            id=owner_id,
            display_name="Timestamp Seller",
            password_hash=None,
            role="user",
            status="active",
        ))
        db.flush()
        db.add(Listing(
            id=listing_id,
            owner_id=owner_id,
            slug=f"timestamp-regression-{uuid4().hex}",
            status="active",
            revision=2,
            title=title,
            description="Listing updated timestamp API regression.",
            contact_phone="+375291234567",
            make_name_snapshot="Mazda",
            model_name_snapshot="3",
            year=2020,
            damaged=False,
            parts_only=False,
            created_at=created_at,
            updated_at=updated_at,
        ))
        db.commit()

    client = integration["client"]
    detail = client.get(f"/api/v1/listings/{listing_id}")
    assert detail.status_code == 200, detail.text
    detail_listing = detail.json()["listing"]
    assert datetime.fromisoformat(detail_listing["updated_at"]) == updated_at
    assert detail_listing["updated_at"] != detail_listing["created_at"]

    search = client.get("/api/v1/listings", params={"q": title})
    assert search.status_code == 200, search.text
    result = next(item for item in search.json()["items"] if item["id"] == str(listing_id))
    assert datetime.fromisoformat(result["updated_at"]) == updated_at


def test_listing_serialization_falls_back_to_created_at_for_missing_updated_at() -> None:
    owner_id = uuid4()
    created_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    listing = Listing(
        id=uuid4(),
        owner_id=owner_id,
        slug=f"missing-updated-at-{uuid4().hex}",
        status="active",
        revision=1,
        title="Timestamp fallback",
        description="",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        created_at=created_at,
        updated_at=None,
    )
    owner = SimpleNamespace(id=owner_id, display_name="Timestamp Seller")

    class SessionStub:
        def get(self, model, _identity):
            return owner if model is User else None

        def scalars(self, _statement):
            return SimpleNamespace(all=list)

    serialized = serialize_listing(SessionStub(), listing)

    assert datetime.fromisoformat(serialized["updated_at"]) == created_at


def test_listing_detail_documents_public_and_private_variants_and_preserves_410() -> (
    None
):
    openapi = app.openapi()
    operation = openapi["paths"]["/api/v1/listings/{listing_id}"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    assert response_schema["$ref"] == "#/components/schemas/ListingDetailOut"
    detail_schema = _component(openapi, response_schema["$ref"])
    listing_schema = detail_schema["properties"]["listing"]
    variants = listing_schema.get("anyOf", listing_schema.get("oneOf", []))
    variant_refs = {variant["$ref"] for variant in variants}
    assert variant_refs == {
        "#/components/schemas/ListingPublicOut",
        "#/components/schemas/ListingOwnerOut",
    }

    public_variant = next(
        ref for ref in variant_refs if ref.endswith("/ListingPublicOut")
    )
    owner_variant = next(
        ref for ref in variant_refs if ref.endswith("/ListingOwnerOut")
    )
    assert UNSAFE_PUBLIC_PROPERTIES.isdisjoint(
        _all_property_names(openapi, {"$ref": public_variant})
    )
    owner_properties = _all_property_names(openapi, {"$ref": owner_variant})
    assert {"contact_phone", "vin", "moderation_reason"}.issubset(owner_properties)
    assert "phone" not in owner_properties
    owner_schema = _component(openapi, owner_variant)
    assert {"contact_phone", "vin", "moderation_reason"}.isdisjoint(
        owner_schema["required"]
    )

    assert operation["responses"]["410"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorOut"
    }


def test_owner_listing_collection_documents_private_listing_items() -> None:
    openapi = app.openapi()
    response = openapi["paths"]["/api/v1/me/listings"]["get"]["responses"]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/ListingOwnerSearchOut"
    owner_search = _component(openapi, response_schema["$ref"])
    item_schema = owner_search["properties"]["items"]["items"]
    assert item_schema["$ref"] == "#/components/schemas/ListingOwnerOut"
    owner_properties = _all_property_names(openapi, item_schema)
    assert {"contact_phone", "vin", "moderation_reason"}.issubset(owner_properties)


def test_listing_write_endpoints_document_owner_listing_responses() -> None:
    openapi = app.openapi()
    routes = (
        ("/api/v1/listings/drafts", "post"),
        ("/api/v1/listings/{listing_id}", "patch"),
        ("/api/v1/listings/{listing_id}/submit", "post"),
        ("/api/v1/listings/{listing_id}/pause", "post"),
        ("/api/v1/listings/{listing_id}/resume", "post"),
        ("/api/v1/listings/{listing_id}/sold", "post"),
    )

    for path, method in routes:
        operation = openapi["paths"][path][method]
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema["$ref"] == "#/components/schemas/ListingOwnerDetailOut"
        wrapper = _component(openapi, response_schema["$ref"])
        assert (
            wrapper["properties"]["listing"]["$ref"]
            == "#/components/schemas/ListingOwnerOut"
        )


def test_favorite_mutations_document_typed_success_responses() -> None:
    openapi = app.openapi()
    path = "/api/v1/me/favorites/{listing_id}"

    for method in ("put", "delete"):
        response_schema = openapi["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema["$ref"] == "#/components/schemas/FavoriteToggleOut"
        favorite_schema = _component(openapi, response_schema["$ref"])
        assert favorite_schema["properties"]["ok"]["const"] is True


def test_favorites_collection_documents_public_listing_items() -> None:
    openapi = app.openapi()
    response = openapi["paths"]["/api/v1/me/favorites"]["get"]["responses"]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/ListingFavoritesOut"
    favorites_schema = _component(openapi, response_schema["$ref"])
    item_schema = favorites_schema["properties"]["items"]["items"]
    assert item_schema["$ref"] == "#/components/schemas/ListingPublicOut"
    assert UNSAFE_PUBLIC_PROPERTIES.isdisjoint(
        _all_property_names(openapi, item_schema)
    )


def test_phone_reveal_documents_only_its_authenticated_phone_response() -> None:
    openapi = app.openapi()
    response = openapi["paths"]["/api/v1/listings/{listing_id}/phone-reveal"]["post"][
        "responses"
    ]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/PhoneRevealOut"
    phone_schema = _component(openapi, response_schema["$ref"])
    assert set(phone_schema["properties"]) == {"phone"}
    assert phone_schema["properties"]["phone"]["type"] == "string"


def test_listing_report_documents_exact_created_report_result() -> None:
    openapi = app.openapi()
    response = openapi["paths"]["/api/v1/listings/{listing_id}/reports"]["post"][
        "responses"
    ]["200"]
    response_schema = response["content"]["application/json"]["schema"]

    assert response_schema["$ref"] == "#/components/schemas/ListingReportOut"
    report_schema = _component(openapi, response_schema["$ref"])
    assert set(report_schema["properties"]) == {"id", "status", "revision"}
    assert report_schema["properties"]["id"]["format"] == "uuid"
    assert report_schema["properties"]["status"]["const"] == "open"
    assert report_schema["required"] == ["id", "status", "revision"]
