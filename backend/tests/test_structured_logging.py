import asyncio
import json
import logging
from io import StringIO

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.logging_config import JsonLogFormatter
from app.main import app, unexpected_error


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/health/live?private_value=do-not-log", 200),
        ("/api/v1/listings?page=0&token=do-not-log", 422),
    ],
)
def test_http_request_log_is_json_and_correlates_with_response(path, expected_status):
    logger = logging.getLogger("avtorinok.api")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    try:
        response = TestClient(app).get(path)
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert response.status_code == expected_status
    request_id = response.headers["x-request-id"]
    if expected_status == 422:
        assert response.json()["request_id"] == request_id

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    request_log = next(
        record for record in records if record["event"] == "http_request"
    )
    assert set(request_log) == {
        "duration_ms", "event", "level", "logger", "method", "path",
        "request_id", "status_code", "timestamp",
    }
    assert request_log["event"] == "http_request"
    assert request_log["level"] == "info"
    assert request_log["logger"] == "avtorinok.api"
    assert request_log["method"] == "GET"
    assert request_log["path"] == path.split("?", 1)[0]
    assert request_log["request_id"] == request_id
    assert request_log["status_code"] == expected_status
    assert isinstance(request_log["duration_ms"], (int, float))
    assert request_log["duration_ms"] >= 0
    assert request_log["timestamp"].endswith("Z")
    assert "do-not-log" not in output.getvalue()


def test_uvicorn_access_logs_are_disabled_to_avoid_unstructured_query_logging():
    assert logging.getLogger("uvicorn.access").disabled is True


def test_unexpected_error_log_keeps_request_id_but_omits_exception_text():
    logger = logging.getLogger("avtorinok.api")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/private-resource",
            "raw_path": b"/private-resource",
            "query_string": b"token=query-secret",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    request.state.request_id = "request-123"
    try:
        response = asyncio.run(
            unexpected_error(request, RuntimeError("password-secret"))
        )
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert response.status_code == 500
    assert response.body
    assert response.headers["x-request-id"] == "request-123"
    assert json.loads(response.body)["request_id"] == "request-123"
    record = json.loads(output.getvalue())
    assert record["event"] == "request_failed"
    assert record["request_id"] == "request-123"
    assert record["method"] == "GET"
    assert record["path"] == "/private-resource"
    assert record["error_type"] == "RuntimeError"
    assert "password-secret" not in output.getvalue()
    assert "query-secret" not in output.getvalue()
