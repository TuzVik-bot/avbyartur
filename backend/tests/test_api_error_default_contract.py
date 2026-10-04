from app.main import app


def test_api_operations_document_default_api_error_response() -> None:
    schema = app.openapi()
    api_operations = []

    for path, path_item in schema["paths"].items():
        if path != "/api/v1" and not path.startswith("/api/v1/"):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            api_operations.append((path, method))
            default_response = operation["responses"]["default"]
            assert default_response["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ApiErrorOut"
            }

    assert api_operations
    ready_response = schema["paths"]["/health/ready"]["get"]["responses"]["503"]
    assert ready_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
