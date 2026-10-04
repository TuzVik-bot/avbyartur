"""Only aggregate health and explicitly allowlisted error events leave the API."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from app import models
from test_admin_management import add_user, signed_client


def test_monitoring_snapshot_requires_admin_and_explains_stale_failed_work(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    user = add_user(factory)
    ordinary, _ = signed_client(integration, user)
    assert ordinary.get("/api/v1/admin/monitoring").status_code == 403
    with factory() as db:
        db.add(models.WorkerJob(kind="photo.process", job_key=uuid.uuid4().hex, payload={"secret": "never-return-job-payload"},
                               status="failed", attempts=5, max_attempts=5, run_after=datetime.now(timezone.utc) - timedelta(hours=1)))
        db.add(models.WorkerJob(kind="saved-search.match", job_key=uuid.uuid4().hex, payload={},
                               status="queued", attempts=0, max_attempts=5, run_after=datetime.now(timezone.utc) - timedelta(minutes=20)))
        db.commit()
    client, _ = signed_client(integration, admin)
    response = client.get("/api/v1/admin/monitoring")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["queue"]["failed"] == 1
    assert data["queue"]["overdue"] == 1
    assert data["queue"]["oldest_overdue_seconds"] >= 1100
    codes = {alert["code"] for alert in data["alerts"]}
    assert {"worker_failed_jobs", "worker_backlog", "exchange_rate_unavailable"}.issubset(codes)
    assert response.headers["cache-control"] == "no-store"
    assert "never-return-job-payload" not in response.text


def test_sentry_scrubber_discards_request_locals_identifiers_and_exception_text():
    from app.error_monitoring import scrub_error_event
    source = {"event_id": "0123456789abcdef0123456789abcdef", "level": "error",
              "message": "password-secret +375291234567", "user": {"email": "private@example.com"},
              "request": {"headers": {"authorization": "secret-token"}, "data": "body-secret"},
              "exception": {"values": [{"type": "RuntimeError", "value": "exception-secret", "stacktrace": {"frames": [{"vars": {"password": "local-secret"}}]}}]},
              "tags": {"component": "api", "error_type": "RuntimeError", "request_id": "a" * 32, "user_id": "private-id"},
              "extra": {"url": "https://private.example/?token=hidden"}}
    cleaned = scrub_error_event(source, {})
    serialized = json.dumps(cleaned)
    for secret in ["password-secret", "+375291234567", "private@example.com", "secret-token", "body-secret", "exception-secret", "local-secret", "private-id", "hidden"]:
        assert secret not in serialized
    assert cleaned["message"] == "RuntimeError"
    assert cleaned["tags"] == {"component": "api", "error_type": "RuntimeError", "request_id": "a" * 32}


def test_sentry_is_disabled_until_configured_and_send_failure_never_breaks_app(monkeypatch):
    import sentry_sdk
    from app import error_monitoring
    from app.config import Settings

    monkeypatch.setattr(error_monitoring, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda *_: (_ for _ in ()).throw(AssertionError("must remain disabled")))
    error_monitoring.capture_safe_error("api", "RuntimeError", request_id="a" * 32)
    from pydantic import SecretStr
    monkeypatch.setattr(error_monitoring, "get_settings", lambda: Settings(_env_file=None, sentry_dsn=SecretStr("https://public@sentry.example/1")))
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda *_: (_ for _ in ()).throw(RuntimeError("transport credential error")))
    error_monitoring.capture_safe_error("worker", "RuntimeError")


def test_monitoring_exposes_expired_leases_and_delivery_failures_without_payloads(integration):
    from app.identity_models import IdentityEmailOutbox
    from app.models import Company, DealerFeed, FeedImportRun
    factory = integration["SessionLocal"]
    administrator = add_user(factory, role="admin")
    now = datetime.now(timezone.utc)
    with factory() as db:
        db.add(models.WorkerJob(kind="photo.process", job_key=uuid.uuid4().hex, payload={}, status="running", attempts=1, max_attempts=5,
                               run_after=now - timedelta(hours=1), lease_until=now - timedelta(minutes=10)))
        db.add(IdentityEmailOutbox(dedupe_key=uuid.uuid4().hex, message_type="email_verification", challenge_id=uuid.uuid4(),
                                  user_id=administrator.id, recipient="private@example.com", subject="Private", body="never-return-email-body", status="failed", attempts=5))
        company = Company(owner_id=administrator.id, name="Мониторинг", slug="monitor-test", unp="123456789", address="Minsk", phone="+375291234567", status="approved")
        db.add(company); db.flush()
        feed = DealerFeed(company_id=company.id, name="Мониторинг", format="csv", created_by=administrator.id)
        db.add(feed); db.flush()
        db.add(FeedImportRun(feed_id=feed.id, company_id=company.id, initiated_by=administrator.id, idempotency_key=uuid.uuid4().hex,
                             payload_digest="a" * 64, status="failed", source_filename="private-source.csv", dry_run=False, total_rows=0, applied_rows=0, rejected_rows=0, error_code="csv_invalid"))
        db.commit()
    client, _ = signed_client(integration, administrator)
    response = client.get("/api/v1/admin/monitoring")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["queue"]["expired_leases"] == 1
    assert snapshot["notifications"]["identity_failed"] == 1
    assert snapshot["imports"]["failed_24h"] == 1
    assert {"worker_expired_leases", "identity_delivery_failed", "feed_import_failed"}.issubset({alert["code"] for alert in snapshot["alerts"]})
    assert snapshot["backup"]["status"] == "unconfigured"
    for value in ["never-return-email-body", "private@example.com", "private-source.csv", "+375291234567"]:
        assert value not in response.text


def test_monitoring_aggregates_identity_feed_sms_payment_and_database_listing_state(integration):
    from decimal import Decimal

    from app.identity_models import IdentityEmailOutbox
    from app.models import (
        BillingOrder,
        BillingTariff,
        Company,
        DealerFeed,
        ExchangeRate,
        FeedImportRun,
        Listing,
        NotificationOutbox,
        PaymentAttempt,
        SavedSearch,
        SmsOtpChallenge,
    )

    factory = integration["SessionLocal"]
    administrator = add_user(factory, role="admin")
    now = datetime.now(timezone.utc)
    with factory() as db:
        listing = Listing(owner_id=administrator.id, slug=f"monitor-{uuid.uuid4().hex}", status="active")
        db.add(listing)
        db.flush()
        saved_search = SavedSearch(user_id=administrator.id, name="Search", search_url="/cars", filters={})
        db.add(saved_search)
        db.flush()
        for status, age_minutes in [("failed", 35), ("unsupported", 25)]:
            db.add(NotificationOutbox(
                dedupe_key=f"outbox-{uuid.uuid4().hex}", saved_search_id=saved_search.id,
                user_id=administrator.id, listing_id=listing.id, channel="web", status=status,
                created_at=now - timedelta(minutes=age_minutes),
            ))
        db.add(IdentityEmailOutbox(
            dedupe_key=uuid.uuid4().hex, message_type="email_verification", challenge_id=uuid.uuid4(),
            user_id=administrator.id, recipient="identity@example.com", subject="Verification", body="secret body",
            status="failed", attempts=3, created_at=now - timedelta(hours=2),
        ))
        for is_failed, is_suppressed, age_hours in [(True, False, 1), (False, True, 2)]:
            db.add(SmsOtpChallenge(
                phone_hash=uuid.uuid4().hex, purpose="login", code_digest="a" * 64,
                idempotency_key_hash=uuid.uuid4().hex, delivery_failed=is_failed,
                delivery_suppressed=is_suppressed, expires_at=now + timedelta(minutes=5),
                created_at=now - timedelta(hours=age_hours),
            ))
        company = Company(owner_id=administrator.id, name="Feed metrics", slug=f"feed-{uuid.uuid4().hex}",
                          unp=uuid.uuid4().hex[:9], address="Minsk", phone="+375291234567", status="approved")
        db.add(company)
        db.flush()
        feed = DealerFeed(company_id=company.id, name="Metrics", format="csv", created_by=administrator.id)
        db.add(feed)
        db.flush()
        db.add(FeedImportRun(
            feed_id=feed.id, company_id=company.id, initiated_by=administrator.id,
            idempotency_key=uuid.uuid4().hex, payload_digest="b" * 64, status="failed",
            source_filename="sensitive.csv", dry_run=False, total_rows=1, applied_rows=0,
            rejected_rows=1, error_code="csv_invalid", created_at=now - timedelta(hours=4),
        ))
        tariff = BillingTariff(
            code=f"monitor-{uuid.uuid4().hex}", service_code="bump", name="Test tariff",
            amount=Decimal("10.00"), currency="BYN", duration_days=1, status="active",
        )
        db.add(tariff)
        db.flush()
        order = BillingOrder(
            user_id=administrator.id, listing_id=listing.id, tariff_id=tariff.id,
            service_code="bump", tariff_code=tariff.code, tariff_revision=1, amount=Decimal("10.00"),
            currency="BYN", duration_days=1, provider="test", idempotency_key_digest="c" * 64,
            request_digest="d" * 64, status="pending", expires_at=now + timedelta(days=1),
        )
        db.add(order)
        db.flush()
        db.add_all([
            PaymentAttempt(order_id=order.id, attempt_number=1, provider="test", amount=Decimal("10.00"),
                           currency="BYN", status="failed", created_at=now - timedelta(minutes=10)),
            PaymentAttempt(order_id=order.id, attempt_number=2, provider="test", amount=Decimal("10.00"),
                           currency="BYN", status="pending", created_at=now - timedelta(hours=3),
                           updated_at=now - timedelta(hours=3)),
        ])
        db.add(ExchangeRate(currency="USD", rate_date=(now.date() - timedelta(days=4)).isoformat(),
                            official_rate=Decimal("3.200000"), scale=1, source="test",
                            fetched_at=now - timedelta(days=4)))
        db.commit()

    client, _ = signed_client(integration, administrator)
    response = client.get("/api/v1/admin/monitoring")
    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["notifications"]["saved_search_failed"] == 1
    assert snapshot["notifications"]["saved_search_unsupported"] == 1
    assert snapshot["notifications"]["identity_failed"] == 1
    assert snapshot["notifications"]["oldest_failed_seconds"] >= 7000
    assert snapshot["sms"]["delivery_failed_24h"] == 1
    assert snapshot["sms"]["delivery_suppressed_24h"] == 1
    assert snapshot["imports"]["failed_24h"] == 1
    assert snapshot["payments"]["failed"] == 1
    assert snapshot["payments"]["pending_aged"] == 1
    assert snapshot["payments"]["oldest_pending_seconds"] >= 10000
    assert snapshot["exchange_rate"]["status"] == "stale"
    assert snapshot["public_listing_index"]["store"] == "postgresql"
    assert snapshot["public_listing_index"]["external_search"] is False
    assert snapshot["public_listing_index"]["active_public_listings"] == 1
    codes = {alert["code"] for alert in snapshot["alerts"]}
    assert {
        "notification_delivery_failed", "identity_delivery_failed", "sms_delivery_failed",
        "feed_import_failed", "payment_failed", "payment_pending_aged", "exchange_rate_unavailable",
    }.issubset(codes)
    for value in ["identity@example.com", "secret body", "sensitive.csv", "+375291234567", "test@example.com"]:
        assert value not in response.text


def test_error_delivery_counters_contain_counts_only(monkeypatch):
    import sentry_sdk
    from app import error_monitoring
    from app.config import Settings
    from pydantic import SecretStr

    monkeypatch.setattr(error_monitoring, "get_settings", lambda: Settings(
        _env_file=None, sentry_dsn=SecretStr("https://public@sentry.example/1")
    ))
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda *_: "private-sentry-event-id")
    before = error_monitoring.error_delivery_snapshot()
    error_monitoring.capture_safe_error("worker", "RuntimeError", request_id="a" * 32)
    after = error_monitoring.error_delivery_snapshot()
    assert after["attempted"] == before["attempted"] + 1
    assert after["accepted"] == before["accepted"] + 1
    assert after["failed"] == before["failed"]
    assert all(isinstance(value, int) for value in after.values())


def test_runtime_status_reader_requires_owner_only_regular_file_and_allowlisted_fields(tmp_path):
    from datetime import datetime, timezone

    from app.api.monitoring import _read_host_status

    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "schema_version": 1,
        "status": "healthy",
        "checked_at_utc": checked,
        "docker_healthy": True,
        "backup_service_state": "success",
        "backup_last_success_at_utc": checked,
        "backup_snapshot_created_at_utc": checked,
        "backup_checksums_valid": True,
        "backup_checksums_checked_at_utc": checked,
        "alert_codes": [],
    }
    path = tmp_path / "status.json"
    path.write_text(json.dumps(payload), encoding="ascii")
    path.chmod(0o600)
    assert _read_host_status(path).backup_checksums_valid is True
    path.chmod(0o640)
    assert _read_host_status(path) is None
    path.chmod(0o700)
    assert _read_host_status(path) is None
    path.chmod(0o600)
    path.write_text("x" * 4097, encoding="ascii")
    assert _read_host_status(path) is None
    path.chmod(0o600)
    path.write_text(json.dumps(payload), encoding="ascii")
    payload["private_path"] = "/home/suite/backups"
    path.write_text(json.dumps(payload), encoding="ascii")
    assert _read_host_status(path) is None
    path.unlink()
    target = tmp_path / "target.json"
    target.write_text(json.dumps({**payload, "private_path": None}), encoding="ascii")
    target.chmod(0o600)
    path.symlink_to(target)
    assert _read_host_status(path) is None


def test_empty_monitoring_status_environment_path_is_unconfigured():
    from app.config import Settings

    assert Settings(_env_file=None, monitoring_status_path="").monitoring_status_path is None
