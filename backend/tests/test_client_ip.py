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


DOCKER_PRIVATE_RANGES = "172.16.0.0/12,10.0.0.0/8,192.168.0.0/16"


def test_client_ip_uses_forwarded_client_behind_nginx_and_web_container(monkeypatch):
    # nginx sets X-Forwarded-For to the real client; the Next.js proxy in the
    # web container forwards it, so the API peer is the web container's IP.
    set_trusted_proxies(monkeypatch, DOCKER_PRIVATE_RANGES)

    result = security.client_ip(make_request("172.18.0.5", "198.51.100.23"))

    assert result == "198.51.100.23"


def test_client_ip_ignores_forwarded_for_from_public_peer_with_docker_ranges(monkeypatch):
    set_trusted_proxies(monkeypatch, DOCKER_PRIVATE_RANGES)

    result = security.client_ip(make_request("203.0.113.9", "198.51.100.23"))

    assert result == "203.0.113.9"


def test_client_ip_is_trusted_proxy_detects_unresolved_client(monkeypatch):
    set_trusted_proxies(monkeypatch, "192.168.213.253/32,127.0.0.1/32")

    assert security.client_ip_is_trusted_proxy("192.168.213.253") is True
    assert security.client_ip_is_trusted_proxy("198.51.100.23") is False
    assert security.client_ip_is_trusted_proxy("unknown") is False


def test_ip_scoped_limit_keeps_per_client_limit_for_resolved_ip(monkeypatch):
    set_trusted_proxies(monkeypatch, "192.168.213.253/32")
    monkeypatch.setattr(security, "_last_unresolved_ip_warning", float("-inf"))
    warnings = []
    monkeypatch.setattr(security, "log_event", lambda logger, level, event, **fields: warnings.append(event))

    assert security.ip_scoped_limit("198.51.100.23", 50) == 50
    assert warnings == []


def test_ip_scoped_limit_widens_to_site_cap_and_warns_once(monkeypatch):
    set_trusted_proxies(monkeypatch, "192.168.213.253/32")
    monkeypatch.setattr(security, "_last_unresolved_ip_warning", float("-inf"))
    warnings = []
    monkeypatch.setattr(security, "log_event", lambda logger, level, event, **fields: warnings.append(event))

    first = security.ip_scoped_limit("192.168.213.253", 50)
    second = security.ip_scoped_limit("192.168.213.253", 50)

    assert first == second == 50 * security.UNKNOWN_CLIENT_IP_LIMIT_FACTOR
    assert warnings == ["client_ip_unresolved"]
