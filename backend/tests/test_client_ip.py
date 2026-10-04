from types import SimpleNamespace

from starlette.requests import Request

from app import security


def make_request(peer: str, forwarded_for: str = "") -> Request:
    headers = []
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request({"type": "http", "headers": headers, "client": (peer, 12345)})


def set_trusted_proxies(monkeypatch, cidrs: str) -> None:
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(trusted_proxy_cidrs=cidrs),
    )


def test_client_ip_ignores_forwarded_for_from_untrusted_peer(monkeypatch):
    set_trusted_proxies(monkeypatch, "10.0.0.0/24")

    result = security.client_ip(
        make_request("172.20.0.4", "198.51.100.42, 10.0.0.8")
    )

    assert result == "172.20.0.4"


def test_client_ip_skips_spoofed_prefix_after_trusted_proxy_hops(monkeypatch):
    set_trusted_proxies(monkeypatch, "10.0.0.0/24,172.20.0.0/24")

    result = security.client_ip(
        make_request("172.20.0.4", "203.0.113.66, 198.51.100.42, 10.0.0.8")
    )

    assert result == "198.51.100.42"


def test_client_ip_falls_back_to_peer_when_forwarded_chain_is_invalid(monkeypatch):
    set_trusted_proxies(monkeypatch, "10.0.0.0/24")

    result = security.client_ip(make_request("10.0.0.8", "unknown, not-an-ip"))

    assert result == "10.0.0.8"
