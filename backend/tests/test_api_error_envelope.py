import json
import logging
from io import StringIO

from fastapi.testclient import TestClient

from app.logging_config import JsonLogFormatter
from app.main import app


def test_unknown_api_path_uses_error_envelope_and_request_header() -> None:
    response = TestClient(app).get("/api/v1/unknown-p0-route")

    assert response.status_code == 404
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert set(response.json()) == {"code", "message", "field_errors", "request_id"}
    assert response.json()["message"] == "Not Found"


def test_api_method_not_allowed_uses_error_envelope_and_request_header() -> None:
    response = TestClient(app).post("/api/v1/catalog/makes")

    assert response.status_code == 405
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert response.headers["allow"] == "GET"
    assert set(response.json()) == {"code", "message", "field_errors", "request_id"}
    assert response.json()["message"] == "Method Not Allowed"


def test_unexpected_error_response_log_and_header_share_request_id() -> None:
    logger = logging.getLogger("avtorinok.api")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())

    @app.get("/api/v1/__p0_error_envelope_test")
    def _raise_unexpected_error() -> None:
        raise RuntimeError("secret-error-text")

    test_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/api/v1/__p0_error_envelope_test"
    )

    logger.addHandler(handler)
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/__p0_error_envelope_test"
        )
    finally:
        logger.removeHandler(handler)
        handler.close()
        app.routes.remove(test_route)
        app.openapi_schema = None

    request_id = response.headers["x-request-id"]
    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An unexpected error occurred",
        "field_errors": {},
        "request_id": request_id,
    }
    record = next(json.loads(line) for line in output.getvalue().splitlines())
    assert record["event"] == "request_failed"
    assert record["request_id"] == request_id
    assert "secret-error-text" not in output.getvalue()
