"""Identity endpoints must not share one site-wide rate-limit bucket."""

import uuid

from fastapi.testclient import TestClient

from app.api import account


def _client(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def test_recovery_requests_for_one_email_do_not_block_another_email(integration):
    client = _client(integration)
    attacker_target = _email("attacker-target")
    for _ in range(10):
        accepted = client.post(
            "/api/v1/auth/recovery/request", json={"email": attacker_target}
        )
        assert accepted.status_code == 202, accepted.text

    exhausted = client.post(
        "/api/v1/auth/recovery/request", json={"email": attacker_target.upper()}
    )
    victim = client.post(
        "/api/v1/auth/recovery/request", json={"email": _email("victim")}
    )

    assert exhausted.status_code == 429, exhausted.text
    assert victim.status_code == 202, victim.text


def test_recovery_confirm_limits_each_token_separately(integration):
    client = _client(integration)
    for index in range(13):
        invalid = client.post(
            "/api/v1/auth/recovery/confirm",
            json={
                "token": f"unknown-token-{index}-{uuid.uuid4().hex}",
                "new_password": "new-password-12345",
            },
        )
        assert invalid.status_code == 401, invalid.text

    repeated_token = f"repeated-{uuid.uuid4().hex}"
    statuses = [
        client.post(
            "/api/v1/auth/recovery/confirm",
            json={"token": repeated_token, "new_password": "new-password-12345"},
        ).status_code
        for _ in range(13)
    ]
    assert statuses == [401] * 12 + [429]


def test_email_confirm_limits_each_token_separately(integration):
    client = _client(integration)
    for index in range(13):
        invalid = client.post(
            "/api/v1/auth/email/verification/confirm",
            json={"token": f"unknown-verification-{index}-{uuid.uuid4().hex}"},
        )
        assert invalid.status_code == 401, invalid.text


def test_identity_endpoints_keep_a_site_wide_safety_cap(integration, monkeypatch):
    monkeypatch.setattr(account, "IDENTITY_SITE_HOURLY_CAP", 3)
    client = _client(integration)
    statuses = [
        client.post(
            "/api/v1/auth/recovery/request", json={"email": _email(f"cap-{index}")}
        ).status_code
        for index in range(4)
    ]
    assert statuses == [202, 202, 202, 429]
