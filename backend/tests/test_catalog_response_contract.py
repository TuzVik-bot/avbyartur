from app.main import app

CATALOG_READ_PATHS = (
    "/api/v1/catalog/makes",
    "/api/v1/catalog/models",
    "/api/v1/catalog/generations",
    "/api/v1/catalog/body-types",
    "/api/v1/catalog/body-variants",
    "/api/v1/catalog/modifications",
    "/api/v1/locations/regions",
    "/api/v1/locations/cities",
)


def _resolve_schema(schema: dict, components: dict) -> dict:
    reference = schema.get("$ref")
    if reference is not None:
        name = reference.rsplit("/", maxsplit=1)[-1]
        return components[name]
    if "anyOf" in schema:
        non_null = next(option for option in schema["anyOf"] if option.get("type") != "null")
        return _resolve_schema(non_null, components)
    return schema


def test_catalog_read_routes_document_typed_item_arrays() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]

    for path in CATALOG_READ_PATHS:
        response_schema = openapi["paths"][path]["get"]["responses"]["200"]
        response_schema = response_schema["content"]["application/json"]["schema"]
        response_model = _resolve_schema(response_schema, components)
        items_schema = response_model["properties"]["items"]

        assert items_schema["type"] == "array", path
        item_schema = _resolve_schema(items_schema["items"], components)
        assert item_schema["type"] == "object", path
        assert {"id", "slug", "name"}.issubset(item_schema["properties"]), path


def test_modification_route_documents_optional_drom_details() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    response_schema = openapi["paths"]["/api/v1/catalog/modifications"]["get"]["responses"]["200"]
    response_model = _resolve_schema(
        response_schema["content"]["application/json"]["schema"], components
    )
    items_schema = response_model["properties"]["items"]
    item_schema = _resolve_schema(items_schema["items"], components)

    assert {"id", "slug", "name", "aliases", "source", "specs"}.issubset(
        item_schema["properties"]
    )
    assert "source" not in item_schema.get("required", [])
    assert "specs" not in item_schema.get("required", [])

    source_schema = _resolve_schema(item_schema["properties"]["source"], components)
    assert set(source_schema["required"]) == {"name", "id", "url"}

    specs_schema = _resolve_schema(item_schema["properties"]["specs"], components)
    assert set(specs_schema["required"]) == {
        "engine_code",
        "frame_code",
        "engine_l",
        "power_hp",
        "fuel",
        "transmission",
        "drive",
        "production_period_raw",
        "summary_raw",
    }
