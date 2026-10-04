"""Reject oversized multipart and JSON feeds before their parsers allocate."""

import json

from app.main import UploadBodyLimitMiddleware
from test_upload_body_limit import _app_that_reads_body, _run, _scope


def test_chunked_feed_upload_is_bounded_before_oversize_chunk_reaches_parser():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, reads = _run(middleware, _scope("/api/v1/dealer/feeds/example/imports"),
                       [b"123456", b"789012", b"unread"])
    assert reads == 2
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["code"] == "feed_body_too_large"


def test_declared_oversize_json_feed_is_rejected_without_reading_body():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, reads = _run(middleware, _scope("/api/v1/dealer/feeds/example/api-imports", headers=[(b"content-length", b"11")]), [b"unread"])
    assert reads == 0
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["code"] == "feed_body_too_large"


def test_small_feed_body_and_unrelated_dealer_route_are_not_rejected():
    middleware = UploadBodyLimitMiddleware(_app_that_reads_body(), max_body_bytes=10)
    sent, _ = _run(middleware, _scope("/api/v1/dealer/feeds/example/imports"), [b"12345"])
    assert sent[0]["status"] == 200
    sent, _ = _run(middleware, _scope("/api/v1/dealer/team"), [b"12345678901"])
    assert sent[0]["status"] == 200
