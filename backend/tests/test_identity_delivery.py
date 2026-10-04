"""Identity and delivery contracts; network transports are never called externally."""

from types import SimpleNamespace
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings
from app.email_delivery import EmailDeliveryUnavailable, SmtpEmailSender
from pydantic import SecretStr

from app.api import auth
from app import models
from app.main import app
from app.security import hash_password
from app.security import new_secret, secret_hash


class FakeSmtp:
    def __init__(self, *, fail_with: Exception | None = None):
        self.fail_with = fail_with
        self.messages = []
        self.started_tls = False
        self.login_args = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self, *, context):
        self.started_tls = True

    def login(self, username, password):
        if self.fail_with:
            raise self.fail_with
        self.login_args = (username, password)

    def send_message(self, message):
        if self.fail_with:
            raise self.fail_with
        self.messages.append(message)


def test_sms_provider_factory_uses_configured_smsc_adapter(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            sms_provider="smsc",
            smsc_api_key=SecretStr("unit-test-smsc-key"),
            smsc_sender="Avtorinok",
            smsc_api_url="https://smsc.ru/sys/send.php",
            smsc_timeout_seconds=2,
        ),
    )

    provider = auth.get_sms_provider()

    assert provider.is_configured is True
    assert type(provider).__name__ == "SmscSmsCodeProvider"


def test_auth_capabilities_endpoint_reports_safe_defaults():
    response = TestClient(app, base_url="http://testserver").get(
        "/api/v1/auth/capabilities"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "sms_login": False,
        "sms_registration": False,
        "email_notifications": False,
        "email_verification": False,
        "password_recovery": False,
    }


def test_auth_capabilities_enable_email_only_for_a_complete_smtp_configuration(monkeypatch):
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            sms_login_enabled=False,
            public_registration_enabled=False,
            sms_provider="disabled",
            smtp_host="smtp.example.test",
            smtp_port=587,
            smtp_username="mailer",
            smtp_password=SecretStr("smtp-unit-test-password"),
            smtp_from="noreply@example.test",
            smtp_starttls=True,
            smtp_ssl=False,
            smtp_timeout_seconds=3,
            public_app_url="https://cars.example.test",
        ),
    )

    response = TestClient(app, base_url="http://testserver").get(
        "/api/v1/auth/capabilities"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "sms_login": False,
        "sms_registration": False,
        "email_notifications": True,
        "email_verification": True,
        "password_recovery": True,
    }


def test_smtp_message_id_is_stable_for_retry_and_transport_uses_tls():
    settings = Settings(
        smtp_host="smtp.example.test",
        smtp_username="mailer",
        smtp_password=SecretStr("smtp-unit-test-password"),
        smtp_from="noreply@example.test",
        smtp_starttls=True,
    )
    fake = FakeSmtp()
    sender = SmtpEmailSender(settings, smtp_factory=lambda *_args, **_kwargs: fake)

    sender.send_email("person@example.test", "Test subject", "Body text", idempotency_key="stable-job-key")
    sender.send_email("person@example.test", "Test subject", "Body text", idempotency_key="stable-job-key")

    expected_id = f"<{hashlib.sha256(b'stable-job-key').hexdigest()}@example.test>"
    assert fake.started_tls is True
    assert fake.login_args == ("mailer", "smtp-unit-test-password")
    assert [message["Message-ID"] for message in fake.messages] == [expected_id, expected_id]
    assert [message.get_content().strip() for message in fake.messages] == ["Body text", "Body text"]


def test_smtp_transport_errors_do_not_retain_server_details_or_credentials():
    settings = Settings(
        smtp_host="smtp.example.test",
        smtp_username="mailer",
        smtp_password=SecretStr("smtp-unit-test-password"),
        smtp_from="noreply@example.test",
    )
    fake = FakeSmtp(fail_with=RuntimeError("rejected smtp-unit-test-password"))
    sender = SmtpEmailSender(settings, smtp_factory=lambda *_args, **_kwargs: fake)

    try:
        sender.send_email("person@example.test", "Test subject", "Body text", idempotency_key="job")
    except EmailDeliveryUnavailable as exc:
        assert exc.code == "email_delivery_failed"
        assert "smtp-unit-test-password" not in str(exc)
        assert "rejected" not in str(exc)
    else:
        raise AssertionError("transport failure should be sanitized and reported")


def test_profile_returns_masked_contacts_and_only_allows_display_name_patch(integration):
    factory = integration["SessionLocal"]
    email = f"identity-{uuid.uuid4().hex[:10]}@example.com"
    user = models.User(
        email=email,
        display_name="Identity Test User",
        password_hash=hash_password("identity-flow-test-password-456"),
        phone_e164="+375291234567",
        phone_verified_at=datetime.now(timezone.utc),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    client = integration["client"]
    signed_in = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "identity-flow-test-password-456"},
    )
    assert signed_in.status_code == 200, signed_in.text
    csrf = signed_in.json()["csrf_token"]

    profile = client.get("/api/v1/me/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()["profile"]
    assert body["id"] == str(user_id)
    assert body["display_name"] == "Identity Test User"
    assert body["contacts"]["email"]["verified"] is False
    assert email not in body["contacts"]["email"]["masked"]
    assert body["contacts"]["phone"]["verified"] is True
    assert body["contacts"]["phone"]["masked"].endswith("67")

    changed = client.patch(
        "/api/v1/me/profile",
        json={"display_name": "Updated User"},
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["profile"]["display_name"] == "Updated User"
    forbidden_contact_edit = client.patch(
        "/api/v1/me/profile",
        json={"display_name": "Updated User", "email": "attacker@example.com"},
        headers={"X-CSRF-Token": csrf},
    )
    assert forbidden_contact_edit.status_code == 422


def _create_identity_user(factory, email: str, *, role: str = "user", password: str = "identity-test-password-987"):
    user = models.User(
        email=email,
        display_name="Identity Flow User",
        password_hash=hash_password(password),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _login_identity(integration, email: str, password: str = "identity-test-password-987"):
    client = integration["client"]
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


class ConfiguredMemoryEmailSender:
    is_configured = True

    def __init__(self):
        self.sent = []

    def send_email(self, recipient, subject, body, *, idempotency_key):
        self.sent.append((recipient, subject, body, idempotency_key))


def _token_from_body(body: str) -> str:
    match = re.search(r"(?m)^Код:\s*([A-Za-z0-9_-]+)\s*$", body)
    assert match is not None
    return match.group(1)


def test_consent_history_is_scoped_to_current_user_and_keeps_versions(integration):
    factory = integration["SessionLocal"]
    email = f"consent-{uuid.uuid4().hex[:10]}@example.com"
    user_id = _create_identity_user(factory, email)
    other_id = _create_identity_user(factory, f"other-{uuid.uuid4().hex[:10]}@example.com")
    with factory() as db:
        db.add_all(
            [
                models.UserConsent(user_id=user_id, document_type="terms", version="terms-v7", source="sms_registration"),
                models.UserConsent(user_id=user_id, document_type="privacy", version="privacy-v4", source="sms_registration"),
                models.UserConsent(user_id=other_id, document_type="terms", version="other-v1", source="admin"),
            ]
        )
        db.commit()

    client, _csrf = _login_identity(integration, email)
    response = client.get("/api/v1/me/consents")

    assert response.status_code == 200, response.text
    assert {(item["document_type"], item["version"], item["source"]) for item in response.json()["items"]} == {
        ("terms", "terms-v7", "sms_registration"),
        ("privacy", "privacy-v4", "sms_registration"),
    }


def test_email_verification_uses_a_token_outbox_then_marks_contact_verified(integration, monkeypatch):
    from app.api import account
    from app.identity_models import IdentityEmailOutbox, VerifiedEmailContact

    factory = integration["SessionLocal"]
    current_email = f"verify-current-{uuid.uuid4().hex[:8]}@example.com"
    requested_email = f"verify-next-{uuid.uuid4().hex[:8]}@example.com"
    user_id = _create_identity_user(factory, current_email)
    sender = ConfiguredMemoryEmailSender()
    monkeypatch.setattr(account, "get_email_sender", lambda _settings=None: sender)
    client, csrf = _login_identity(integration, current_email)

    requested = client.post(
        "/api/v1/auth/email/verification/request",
        json={"email": requested_email},
        headers={"X-CSRF-Token": csrf},
    )
    assert requested.status_code == 202, requested.text
    assert requested.json() == {"accepted": True}
    with factory() as db:
        outbox = db.scalar(
            select(IdentityEmailOutbox).where(
                IdentityEmailOutbox.user_id == user_id,
                IdentityEmailOutbox.message_type == "email_verification",
            )
        )
        assert outbox is not None and outbox.status == "queued"
        token = _token_from_body(outbox.body)

    confirmed = client.post("/api/v1/auth/email/verification/confirm", json={"token": token})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"verified": True}
    with factory() as db:
        contact = db.scalar(select(VerifiedEmailContact).where(VerifiedEmailContact.user_id == user_id))
        user = db.get(models.User, user_id)
        assert contact.email == requested_email
        assert user.email == requested_email
        assert contact.verified_at is not None


def test_recovery_request_is_generic_and_confirmation_revokes_existing_sessions(integration, monkeypatch):
    from app.api import account
    from app.identity_models import IdentityEmailOutbox, VerifiedEmailContact

    factory = integration["SessionLocal"]
    email = f"recover-{uuid.uuid4().hex[:10]}@example.com"
    user_id = _create_identity_user(factory, email)
    with factory() as db:
        db.add(VerifiedEmailContact(user_id=user_id, email=email, verified_at=datetime.now(timezone.utc)))
        db.commit()
    sender = ConfiguredMemoryEmailSender()
    monkeypatch.setattr(account, "get_email_sender", lambda _settings=None: sender)

    unknown = integration["client"].post(
        "/api/v1/auth/recovery/request", json={"email": f"missing-{uuid.uuid4().hex[:8]}@example.com"}
    )
    requested = integration["client"].post("/api/v1/auth/recovery/request", json={"email": email})
    assert unknown.status_code == requested.status_code == 202
    assert unknown.json() == requested.json() == {"accepted": True}
    with factory() as db:
        outbox = db.scalar(
            select(IdentityEmailOutbox).where(
                IdentityEmailOutbox.user_id == user_id,
                IdentityEmailOutbox.message_type == "password_recovery",
            )
        )
        assert outbox is not None and outbox.status == "queued"
        token = _token_from_body(outbox.body)

    client, _csrf = _login_identity(integration, email)
    with factory() as db:
        previously_active_sessions = set(
            db.scalars(
                select(models.UserSession.token_hash).where(
                    models.UserSession.user_id == user_id,
                    models.UserSession.revoked_at.is_(None),
                )
            ).all()
        )
    assert previously_active_sessions
    confirmed = client.post(
        "/api/v1/auth/recovery/confirm",
        json={"token": token, "new_password": "new-identity-password-654"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"ok": True}
    assert client.get("/api/v1/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login", json={"email": email, "password": "new-identity-password-654"}
    ).status_code == 200
    with factory() as db:
        sessions = db.scalars(select(models.UserSession).where(models.UserSession.user_id == user_id)).all()
        previously_active = [item for item in sessions if item.token_hash in previously_active_sessions]
        assert len(previously_active) == len(previously_active_sessions)
        assert all(item.revoked_at is not None for item in previously_active)
        assert any(item.token_hash not in previously_active_sessions and item.revoked_at is None for item in sessions)


def test_account_deletion_deactivates_user_withdraws_listings_and_revokes_sessions(integration):
    from app.identity_models import AccountDeletionRequest

    factory = integration["SessionLocal"]
    email = f"delete-{uuid.uuid4().hex[:10]}@example.com"
    user_id = _create_identity_user(factory, email)
    listings = [
        models.Listing(owner_id=user_id, slug=f"delete-{uuid.uuid4().hex}", status=status, revision=1, title=status)
        for status in ("active", "pending_review")
    ]
    raw_other_session = new_secret()
    with factory() as db:
        db.add_all(listings)
        db.add(
            models.UserSession(
                token_hash=secret_hash(raw_other_session),
                csrf_hash=secret_hash(new_secret()),
                user_id=user_id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        db.commit()

    client, csrf = _login_identity(integration, email)
    requested = client.post(
        "/api/v1/me/deletion-requests",
        json={"confirmation": "DELETE"},
        headers={"X-CSRF-Token": csrf},
    )

    assert requested.status_code == 202, requested.text
    assert requested.json()["status"] == "requested"
    assert requested.json()["revoked_sessions"] == 2
    assert requested.json()["withdrawn_listings"] == 2
    assert client.get("/api/v1/me").status_code == 401
    with factory() as db:
        assert db.get(models.User, user_id).status == "deleted"
        assert db.scalar(select(AccountDeletionRequest.id).where(AccountDeletionRequest.user_id == user_id)) is not None
        assert set(db.scalars(select(models.Listing.status).where(models.Listing.owner_id == user_id)).all()) == {"paused"}
        events = db.scalars(select(models.ListingStatusEvent).where(models.ListingStatusEvent.listing_id.in_([item.id for item in listings]))).all()
        assert len(events) == 2
        assert all(event.actor_id == user_id and event.to_status == "paused" for event in events)


def test_identity_email_worker_retries_safely_and_is_idempotent(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import Base
    from app.identity_models import EmailVerificationChallenge, IdentityEmailOutbox
    import app.worker as worker

    engine = create_engine(f"sqlite:///{tmp_path / 'identity-worker.sqlite'}")
    Base.metadata.create_all(
        engine,
        tables=[
            models.User.__table__,
            EmailVerificationChallenge.__table__,
            IdentityEmailOutbox.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)

    class RetryEmailSender:
        is_configured = True

        def __init__(self):
            self.calls = []

        def send_email(self, recipient, subject, body, *, idempotency_key):
            self.calls.append((recipient, subject, body, idempotency_key))
            if len(self.calls) == 1:
                raise RuntimeError("provider rejected private-test-marker")

    sender = RetryEmailSender()
    monkeypatch.setattr(worker, "get_email_sender", lambda _settings=None: sender, raising=False)
    now = datetime.now(timezone.utc)
    user = models.User(
        id=uuid.uuid4(),
        email="delivery@example.com",
        display_name="Delivery Test",
        password_hash="not-used",
        role="user",
        status="active",
    )
    challenge = EmailVerificationChallenge(
        id=uuid.uuid4(),
        user_id=user.id,
        email=user.email,
        token_digest=hashlib.sha256(b"private-test-token").hexdigest(),
        expires_at=now + timedelta(minutes=30),
    )
    outbox = IdentityEmailOutbox(
        id=uuid.uuid4(),
        dedupe_key=f"identity-email:email_verification:{challenge.id}",
        message_type="email_verification",
        challenge_id=challenge.id,
        user_id=user.id,
        recipient=user.email,
        subject="Verify email",
        body="Code: private-test-token",
        status="queued",
        attempts=0,
        available_at=now,
    )
    with factory() as db:
        db.add_all([user, challenge, outbox])
        db.commit()
        outbox_id = outbox.id

    with pytest.raises(EmailDeliveryUnavailable) as failure:
        worker._deliver_identity_email(outbox_id)
    assert failure.value.code == "email_delivery_failed"
    assert "private-test-marker" not in str(failure.value)

    with factory() as db:
        pending = db.get(IdentityEmailOutbox, outbox_id)
        assert pending.status == "queued"
        assert pending.last_error == "email_delivery_failed"
        assert "private-test-marker" not in pending.last_error
        assert pending.attempts == 1
    assert len(sender.calls) == 1

    worker._deliver_identity_email(outbox_id)
    worker._deliver_identity_email(outbox_id)

    with factory() as db:
        complete = db.get(IdentityEmailOutbox, outbox_id)
        assert complete.status == "delivered"
        assert complete.last_error is None
        assert complete.body == ""
        assert complete.delivered_at is not None
    assert [call[3] for call in sender.calls] == [outbox.dedupe_key, outbox.dedupe_key]
    engine.dispose()
