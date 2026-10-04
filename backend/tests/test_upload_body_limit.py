import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.main import UploadBodyLimitMiddleware


def _scope(path: str, *, headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }


def _run(middleware, scope: dict, chunks: list[bytes]) -> tuple[list[dict], int]:
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    receive_count = 0
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal receive_count
        receive_count += 1
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent, receive_count


def _app_that_reads_body():
    async def app(scope, receive, send):
        body_size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            body_size += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(body_size).encode()})

    return app


def test_photo_upload_body_limit_rejects_chunked_body_before_passing_oversize_chunk():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, receive_count = _run(
        middleware,
        _scope("/api/v1/listings/123/photos"),
        [b"123456", b"789012", b"unread"],
    )

    assert receive_count == 2
    assert sent[0]["status"] == 413
    assert dict(sent[0]["headers"])[b"x-request-id"]
    body = json.loads(sent[1]["body"])
    assert body["code"] == "request_body_too_large"
    assert body["request_id"] == dict(sent[0]["headers"])[b"x-request-id"].decode()


def test_photo_upload_body_limit_rejects_declared_size_without_reading_body():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, receive_count = _run(
        middleware,
        _scope("/api/v1/listings/123/photos", headers=[(b"content-length", b"11")]),
        [b"unread"],
    )

    assert receive_count == 0
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["code"] == "request_body_too_large"


def test_photo_upload_body_limit_does_not_apply_to_other_routes():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, receive_count = _run(
        middleware,
        _scope("/api/v1/listings"),
        [b"123456", b"789012"],
    )

    assert receive_count == 2
    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"12"


def test_app_rejects_chunked_upload_body_before_multipart_parsing(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(upload_max_bytes=10))

    response = TestClient(main.app).post(
        "/api/v1/listings/00000000-0000-0000-0000-000000000000/photos",
        content=iter([b"x" * (64 * 1024), b"x" * 11]),
        headers={"Content-Type": "multipart/form-data; boundary=unused"},
    )

    assert response.status_code == 413, response.text
    assert response.json()["code"] == "request_body_too_large"
    assert response.json()["request_id"] == response.headers["x-request-id"]
