from app.main import app


def test_documented_validation_errors_match_runtime_envelope() -> None:
    schema = app.openapi()
    validation_responses = []

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            response = operation.get("responses", {}).get("422")
            if response is None:
                continue
            validation_responses.append((path, method))
            assert response["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ApiErrorOut"
            }

    assert validation_responses
    error_schema = schema["components"]["schemas"]["ApiErrorOut"]
    assert set(error_schema["required"]) == {
        "code",
        "message",
        "field_errors",
        "request_id",
    }
    assert error_schema["properties"]["field_errors"]["additionalProperties"] == {
        "type": "string"
    }


def test_idempotency_required_posts_document_required_header() -> None:
    schema = app.openapi()
    paths = (
        "/api/v1/listings/drafts",
        "/api/v1/listings/{listing_id}/submit",
        "/api/v1/listings/{listing_id}/photos",
        "/api/v1/conversations",
        "/api/v1/conversations/{conversation_id}/messages",
        "/api/v1/conversations/{conversation_id}/read",
        "/api/v1/conversations/{conversation_id}/block",
    )

    for path in paths:
        operation = schema["paths"][path]["post"]
        header = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "Idempotency-Key"
        )

        assert header["in"] == "header"
        assert header["required"] is True
        assert header["schema"]["type"] == "string"
        assert "nullable" not in header["schema"]
        assert "anyOf" not in header["schema"]
