from app.main import app


def _response_schema(openapi: dict, path: str, method: str) -> dict:
    response = openapi["paths"][path][method]["responses"]["200"]
    return response["content"]["application/json"]["schema"]


def test_media_routes_document_named_response_models() -> None:
    openapi = app.openapi()
    routes = {
        ("/api/v1/listings/{listing_id}/photos", "post"): "PhotoUploadResponse",
        ("/api/v1/listings/{listing_id}/photos", "get"): "ListingPhotoStatusesResponse",
        ("/api/v1/listings/{listing_id}/photos/{photo_id}", "delete"): "PhotoMutationResponse",
        ("/api/v1/listings/{listing_id}/photos/reorder", "post"): "PhotoMutationResponse",
        ("/api/v1/listings/{listing_id}/photos/{photo_id}/cover", "post"): "PhotoMutationResponse",
    }

    for (path, method), model_name in routes.items():
        assert _response_schema(openapi, path, method) == {
            "$ref": f"#/components/schemas/{model_name}"
        }


def test_media_response_models_expose_only_public_photo_metadata() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]

    upload = components["PhotoUploadResponse"]["properties"]
    assert set(upload) == {"id", "status", "url"}
    assert upload["url"]["type"] == "string"
    assert components["PhotoUploadResponse"]["properties"]["status"]["enum"] == [
        "processing", "ready", "failed",
    ]

    status_response = components["ListingPhotoStatusesResponse"]["properties"]
    assert status_response["items"]["items"] == {
        "$ref": "#/components/schemas/ListingPhotoStatusOut"
    }
    status_item = components["ListingPhotoStatusOut"]["properties"]
    assert set(status_item) == {"id", "status", "position", "is_cover", "url"}
    url_schema = status_item["url"]
    assert {"type": "null"} in url_schema["anyOf"]
    assert {"type": "string"} in url_schema["anyOf"]

    mutation = components["PhotoMutationResponse"]
    assert set(mutation["properties"]) == {"ok"}
    assert mutation["properties"]["ok"]["const"] is True

    forbidden_fields = {"storage_name", "original_name", "filename", "storage_key"}
    for model_name in ("PhotoUploadResponse", "ListingPhotoStatusOut"):
        assert forbidden_fields.isdisjoint(components[model_name]["properties"])


def test_photo_upload_keeps_idempotency_header_required() -> None:
    operation = app.openapi()["paths"]["/api/v1/listings/{listing_id}/photos"]["post"]
    header = next(parameter for parameter in operation["parameters"] if parameter["name"] == "Idempotency-Key")

    assert header["in"] == "header"
    assert header["required"] is True
