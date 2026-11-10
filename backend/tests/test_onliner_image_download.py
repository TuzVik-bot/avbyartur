"""Image downloads from the Onliner mirror are restricted to the Onliner CDN."""

import httpx
import pytest

from app.ingest_onliner import OnlinerClient, OnlinerFetchError

IMAGE_URL = "https://content.onliner.by/automarket/1/original/a.jpg"


def _client(handler) -> OnlinerClient:
    return OnlinerClient(transport=httpx.MockTransport(handler), sleep=lambda seconds: None)


def _never_called(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected request to {request.url}")


def test_download_image_reads_an_allowed_https_cdn_url():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"image-bytes")

    with _client(handler) as client:
        assert client.download_image(IMAGE_URL, max_bytes=1024) == b"image-bytes"
    assert seen == [IMAGE_URL]


@pytest.mark.parametrize(
    "url",
    [
        "http://content.onliner.by/automarket/1/original/a.jpg",
        "https://evil.example/automarket/1/original/a.jpg",
        "https://content.onliner.by.evil.example/a.jpg",
        "https://user@content.onliner.by/a.jpg",
        "https://content.onliner.by:8443/a.jpg",
        "https://127.0.0.1/a.jpg",
        "file:///etc/passwd",
    ],
)
def test_download_image_rejects_urls_outside_the_cdn_allowlist(url):
    with _client(_never_called) as client, pytest.raises(OnlinerFetchError):
        client.download_image(url, max_bytes=1024)


def test_download_image_does_not_follow_a_redirect_off_the_allowlist():
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.host)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    with _client(handler) as client, pytest.raises(OnlinerFetchError):
        client.download_image(IMAGE_URL, max_bytes=1024)
    assert requested == ["content.onliner.by"]


def test_download_image_follows_a_redirect_within_the_allowlist():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/a.jpg"):
            return httpx.Response(301, headers={"Location": "/automarket/1/original/b.jpg"})
        return httpx.Response(200, content=b"moved")

    with _client(handler) as client:
        assert client.download_image(IMAGE_URL, max_bytes=1024) == b"moved"


def test_download_image_stops_after_too_many_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": IMAGE_URL})

    with _client(handler) as client, pytest.raises(OnlinerFetchError):
        client.download_image(IMAGE_URL, max_bytes=1024)


def test_download_image_rejects_declared_oversized_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "4096"}, content=b"x" * 4096)

    with _client(handler) as client, pytest.raises(OnlinerFetchError):
        client.download_image(IMAGE_URL, max_bytes=1024)


def test_download_image_caps_a_streamed_body_without_content_length():
    chunks_sent = []

    def chunks():
        for _ in range(100):
            chunks_sent.append(1)
            yield b"x" * 512

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())

    with _client(handler) as client, pytest.raises(OnlinerFetchError):
        client.download_image(IMAGE_URL, max_bytes=1024)
    assert len(chunks_sent) < 100
