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


def _capture_api_log():
    logger = logging.getLogger("avtorinok.api")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    return logger, handler, output


def test_unexpected_error_log_has_redacted_message_and_traceback_without_query():
    logger, handler, output = _capture_api_log()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/private-resource",
            "raw_path": b"/private-resource",
            "query_string": b"token=query-secret",
            "headers": [(b"cookie", b"session=cookie-secret"), (b"authorization", b"Bearer header-secret")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    request.state.request_id = "request-123"

    def failing_view(password_local="local-secret"):
        raise RuntimeError("lookup failed token=message-secret https://x.example/cb?code=url-secret")

    try:
        try:
            failing_view()
        except RuntimeError as error:
            response = asyncio.run(unexpected_error(request, error))
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "request-123"
    assert json.loads(response.body)["request_id"] == "request-123"
    record = json.loads(output.getvalue())
    assert record["event"] == "request_failed"
    assert record["request_id"] == "request-123"
    assert record["method"] == "GET"
    assert record["path"] == "/private-resource"
    assert record["error_type"] == "RuntimeError"
    assert record["error_message"].startswith("lookup failed token=[redacted]")
    assert "failing_view" in record["traceback"]
    assert "RuntimeError" in record["traceback"]
    for secret in ["query-secret", "message-secret", "url-secret", "cookie-secret", "header-secret", "local-secret"]:
        assert secret not in output.getvalue()


def test_unexpected_error_message_is_truncated():
    logger, handler, output = _capture_api_log()
    request = Request({"type": "http", "method": "GET", "path": "/x", "headers": [], "query_string": b""})
    request.state.request_id = "request-123"
    try:
        asyncio.run(unexpected_error(request, ValueError("x" * 2000)))
    finally:
        logger.removeHandler(handler)
        handler.close()
    record = json.loads(output.getvalue())
    assert len(record["error_message"]) <= 500


def test_log_event_renders_exc_info_true_as_traceback_field():
    from app.logging_config import log_event

    logger = logging.getLogger("avtorinok.test-exc-info")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    try:
        try:
            raise KeyError("missing password=pw-secret")
        except KeyError:
            log_event(logger, logging.ERROR, "worker_job_failed", exc_info=True, job_kind="photo.process")
        log_event(logger, logging.ERROR, "plain_event", job_kind="photo.process")
    finally:
        logger.removeHandler(handler)
        handler.close()
    failed, plain = [json.loads(line) for line in output.getvalue().splitlines()]
    assert failed["job_kind"] == "photo.process"
    assert "KeyError" in failed["traceback"]
    assert "test_log_event_renders_exc_info_true_as_traceback_field" in failed["traceback"]
    assert "pw-secret" not in output.getvalue()
    assert "exc_info" not in failed
    assert "traceback" not in plain


def test_log_event_exc_info_true_outside_exception_adds_no_traceback():
    from app.logging_config import log_event

    logger = logging.getLogger("avtorinok.test-exc-info")
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    try:
        log_event(logger, logging.ERROR, "no_active_exception", exc_info=True)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert "traceback" not in json.loads(output.getvalue())


def test_traceback_includes_redacted_chained_cause():
    from app.logging_config import format_safe_traceback

    try:
        try:
            raise OSError("socket token=inner-secret")
        except OSError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as outer:
        rendered = format_safe_traceback(outer)
    assert "OSError" in rendered and "RuntimeError" in rendered
    assert "inner-secret" not in rendered


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ("Bearer abc.def-secret", "abc.def-secret"),
        ("POST https://api.telegram.org/bot123456789:AAAbbbCCCdddEEEfffGGGhhhIIIjjjKKK/getUpdates", "AAAbbbCCCdddEEEfffGGGhhhIIIjjjKKK"),
        ("duplicate DETAIL: Key (email)=(user@example.com) already exists", "user@example.com"),
        ("insert failed [SQL: INSERT INTO users]\n[parameters: {'phone': '+375291234567'}]", "+375291234567"),
        ("call +375 29 123-45-67 failed", "123-45-67"),
    ],
)
def test_safe_exception_message_redacts_secrets(message, secret):
    from app.logging_config import safe_exception_message

    assert secret not in safe_exception_message(RuntimeError(message))


def test_incoming_valid_request_id_is_reused_in_header_and_log():
    logger, handler, output = _capture_api_log()
    try:
        response = TestClient(app).get("/health/live", headers={"X-Request-ID": "nginx-req.0001_ab"})
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert response.headers["x-request-id"] == "nginx-req.0001_ab"
    record = next(json.loads(line) for line in output.getvalue().splitlines())
    assert record["request_id"] == "nginx-req.0001_ab"


@pytest.mark.parametrize("incoming", ["short", "x" * 129, "bad id with spaces", "evil;id=12345", "a/b/c/d/e/f/g"])
def test_invalid_incoming_request_id_is_replaced(incoming):
    response = TestClient(app).get("/health/live", headers={"X-Request-ID": incoming})
    returned = response.headers["x-request-id"]
    assert returned != incoming
    assert len(returned) == 32
