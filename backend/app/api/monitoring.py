"""Aggregate admin monitoring without payloads, identifiers or credentials."""

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.listings import _active_query
from app.api.moderation import require_admin
from app.config import get_settings
from app.db import get_db
from app.identity_models import IdentityEmailOutbox
from app.models import (
    ExchangeRate,
    FeedImportRun,
    NotificationOutbox,
    PaymentAttempt,
    SmsOtpChallenge,
    User,
    WorkerJob,
)
from app.monitoring_schemas import HostMonitoringStatusFile, MonitoringSnapshotOut

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])
STATUS_FILE_LIMIT = 4096
HOST_MONITOR_MAX_AGE = timedelta(minutes=15)
QUEUE_ALERT_AGE = timedelta(minutes=10)
PAYMENT_ALERT_AGE = timedelta(minutes=30)
EXCHANGE_RATE_MAX_AGE = timedelta(hours=72)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _age_seconds(now: datetime, value: datetime | None) -> int:
    aware = _aware(value)
    return max(0, int((now - aware).total_seconds())) if aware else 0


def _count(db: Session, model, *predicates) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*predicates)) or 0)


def _minimum(db: Session, column, *predicates) -> datetime | None:
    return db.scalar(select(func.min(column)).where(*predicates))


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def _read_host_status(path: Path) -> HostMonitoringStatusFile | None:
    """Read a small private status document without following links."""
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) not in {0o400, 0o600}
            or before.st_uid != os.geteuid()
        ):
            return None
        if before.st_size > STATUS_FILE_LIMIT:
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                return None
            raw = source.read(STATUS_FILE_LIMIT + 1)
            after = os.fstat(source.fileno())
            if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                return None
        if len(raw) > STATUS_FILE_LIMIT:
            return None
        payload = json.loads(raw)
        status = HostMonitoringStatusFile.model_validate(payload)
        checked = _timestamp(status.checked_at_utc)
        if checked is None:
            return None
        if status.backup_last_success_at_utc is not None:
            _timestamp(status.backup_last_success_at_utc)
        if status.backup_snapshot_created_at_utc is not None:
            _timestamp(status.backup_snapshot_created_at_utc)
        if (status.status == "healthy") != (len(status.alert_codes) == 0):
            return None
        return status
    except (OSError, ValueError, TypeError, json.JSONDecodeError, ValidationError):
        return None


def _backup_snapshot(now: datetime) -> tuple[dict, list[dict]]:
    path = get_settings().monitoring_status_path
    if path is None:
        return {
            "status": "unconfigured", "docker_healthy": None, "backup_service_state": None,
            "backup_checksums_valid": None, "backup_checksums_checked_at": None, "backup_last_success_at": None,
            "snapshot_created_at": None, "checked_at": None,
        }, []

    host = _read_host_status(path)
    if host is None:
        return {
            "status": "unavailable", "docker_healthy": None, "backup_service_state": None,
            "backup_checksums_valid": None, "backup_checksums_checked_at": None, "backup_last_success_at": None,
            "snapshot_created_at": None, "checked_at": None,
        }, [{"code": "runtime_monitor_unavailable", "severity": "medium"}]

    checked = _timestamp(host.checked_at_utc)
    if checked is None or now - checked > HOST_MONITOR_MAX_AGE or checked - now > timedelta(minutes=2):
        return {
            "status": "stale", "docker_healthy": host.docker_healthy,
            "backup_service_state": host.backup_service_state,
            "backup_checksums_valid": host.backup_checksums_valid,
            "backup_checksums_checked_at": host.backup_checksums_checked_at_utc,
            "backup_last_success_at": host.backup_last_success_at_utc,
            "snapshot_created_at": host.backup_snapshot_created_at_utc,
            "checked_at": host.checked_at_utc,
        }, [{"code": "runtime_monitor_unavailable", "severity": "medium"}]

    alert_map = {
        "docker_unavailable": ("docker_unhealthy", "high"),
        "container_unhealthy": ("docker_unhealthy", "high"),
        "backup_service_failed": ("backup_failed", "high"),
        "backup_stale": ("backup_stale", "medium"),
        "backup_missing": ("backup_stale", "medium"),
        "backup_checksum_failed": ("backup_checksum_failed", "high"),
        "monitor_configuration": ("runtime_monitor_unavailable", "medium"),
        "health_endpoint_unavailable": ("docker_unhealthy", "high"),
    }
    alerts = []
    for code in host.alert_codes:
        alert_code, severity = alert_map[code]
        if not any(alert["code"] == alert_code for alert in alerts):
            alerts.append({"code": alert_code, "severity": severity})
    return {
        "status": "action_required" if alerts else "ok",
        "docker_healthy": host.docker_healthy,
        "backup_service_state": host.backup_service_state,
        "backup_checksums_valid": host.backup_checksums_valid,
        "backup_checksums_checked_at": host.backup_checksums_checked_at_utc,
        "backup_last_success_at": host.backup_last_success_at_utc,
        "snapshot_created_at": host.backup_snapshot_created_at_utc,
        "checked_at": host.checked_at_utc,
    }, alerts


@router.get("/monitoring", response_model=MonitoringSnapshotOut)
def monitoring_snapshot(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    del admin
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    alerts: list[dict] = []

    worker_failed = _count(db, WorkerJob, WorkerJob.status == "failed")
    overdue = _count(db, WorkerJob, WorkerJob.status == "queued", WorkerJob.run_after < now)
    oldest_overdue = _minimum(db, WorkerJob.run_after, WorkerJob.status == "queued", WorkerJob.run_after < now)
    expired_leases = _count(
        db, WorkerJob, WorkerJob.status == "running", WorkerJob.lease_until.is_not(None), WorkerJob.lease_until < now,
    )
    oldest_expired_lease = _minimum(
        db, WorkerJob.lease_until, WorkerJob.status == "running", WorkerJob.lease_until.is_not(None), WorkerJob.lease_until < now,
    )
    if worker_failed:
        alerts.append({"code": "worker_failed_jobs", "severity": "high", "count": worker_failed})
    if overdue:
        alerts.append({"code": "worker_backlog", "severity": "medium", "count": overdue})
    if expired_leases:
        alerts.append({"code": "worker_expired_leases", "severity": "high", "count": expired_leases})

    saved_search_failed = _count(
        db, NotificationOutbox, NotificationOutbox.saved_search_id.is_not(None), NotificationOutbox.status == "failed",
    )
    saved_search_unsupported = _count(
        db, NotificationOutbox, NotificationOutbox.saved_search_id.is_not(None), NotificationOutbox.status == "unsupported",
    )
    saved_search_queued_aged = _count(
        db, NotificationOutbox, NotificationOutbox.saved_search_id.is_not(None),
        NotificationOutbox.status == "queued", NotificationOutbox.available_at < now - QUEUE_ALERT_AGE,
    )
    identity_failed = _count(db, IdentityEmailOutbox, IdentityEmailOutbox.status == "failed")
    identity_queued_aged = _count(
        db, IdentityEmailOutbox, IdentityEmailOutbox.status == "queued",
        IdentityEmailOutbox.available_at < now - QUEUE_ALERT_AGE,
    )
    oldest_failed_times = [
        _minimum(db, NotificationOutbox.created_at, NotificationOutbox.saved_search_id.is_not(None), NotificationOutbox.status == "failed"),
        _minimum(db, IdentityEmailOutbox.created_at, IdentityEmailOutbox.status == "failed"),
    ]
    oldest_failed_at = min((value for value in oldest_failed_times if value is not None), key=_aware, default=None)
    if saved_search_failed or saved_search_unsupported:
        alerts.append({"code": "notification_delivery_failed", "severity": "high", "count": saved_search_failed + saved_search_unsupported})
    if saved_search_queued_aged or identity_queued_aged:
        alerts.append({"code": "notification_backlog", "severity": "medium", "count": saved_search_queued_aged + identity_queued_aged})
    if identity_failed:
        alerts.append({"code": "identity_delivery_failed", "severity": "high", "count": identity_failed})

    sms_cutoff = now - timedelta(hours=24)
    sms_recent = _count(db, SmsOtpChallenge, SmsOtpChallenge.created_at >= sms_cutoff)
    if sms_recent:
        sms = {
            "sent_24h": _count(db, SmsOtpChallenge, SmsOtpChallenge.sent_at >= sms_cutoff),
            "delivery_failed_24h": _count(db, SmsOtpChallenge, SmsOtpChallenge.created_at >= sms_cutoff, SmsOtpChallenge.delivery_failed.is_(True)),
            "delivery_suppressed_24h": _count(db, SmsOtpChallenge, SmsOtpChallenge.created_at >= sms_cutoff, SmsOtpChallenge.delivery_suppressed.is_(True)),
        }
        if sms["delivery_failed_24h"]:
            alerts.append({"code": "sms_delivery_failed", "severity": "high", "count": sms["delivery_failed_24h"]})
    else:
        sms = {"sent_24h": None, "delivery_failed_24h": None, "delivery_suppressed_24h": None}

    import_failures = _count(
        db, FeedImportRun, FeedImportRun.status == "failed", FeedImportRun.created_at >= now - timedelta(hours=24),
    )
    if import_failures:
        alerts.append({"code": "feed_import_failed", "severity": "medium", "count": import_failures})

    payment_failed = _count(db, PaymentAttempt, PaymentAttempt.status == "failed")
    pending_cutoff = now - PAYMENT_ALERT_AGE
    pending_aged = _count(db, PaymentAttempt, PaymentAttempt.status == "pending", PaymentAttempt.created_at < pending_cutoff)
    oldest_pending = _minimum(db, PaymentAttempt.created_at, PaymentAttempt.status == "pending", PaymentAttempt.created_at < pending_cutoff)
    if payment_failed:
        alerts.append({"code": "payment_failed", "severity": "medium", "count": payment_failed})
    if pending_aged:
        alerts.append({"code": "payment_pending_aged", "severity": "medium", "count": pending_aged})

    rate = db.scalar(
        select(ExchangeRate).where(ExchangeRate.currency == "USD", ExchangeRate.rate_date <= now.date().isoformat())
        .order_by(ExchangeRate.rate_date.desc()).limit(1)
    )
    rate_age = _age_seconds(now, rate.fetched_at) if rate and rate.fetched_at else None
    if rate_age is None:
        rate_status = "unavailable"
    elif rate_age > EXCHANGE_RATE_MAX_AGE.total_seconds():
        rate_status = "stale"
    else:
        rate_status = "current"
    if rate_status != "current":
        alerts.append({"code": "exchange_rate_unavailable", "severity": "medium"})

    dialect = db.get_bind().dialect.name
    public_count = int(db.scalar(select(func.count()).select_from(_active_query().subquery())) or 0)
    public_store = "postgresql" if dialect == "postgresql" else "sqlite" if dialect == "sqlite" else "other"

    from app.error_monitoring import error_delivery_snapshot

    error_delivery = error_delivery_snapshot()
    backup, host_alerts = _backup_snapshot(now)
    alerts.extend(host_alerts)

    return {
        "queue": {
            "failed": worker_failed,
            "overdue": overdue,
            "oldest_overdue_seconds": _age_seconds(now, oldest_overdue),
            "expired_leases": expired_leases,
            "oldest_expired_lease_seconds": _age_seconds(now, oldest_expired_lease),
        },
        "notifications": {
            "saved_search_failed": saved_search_failed,
            "saved_search_unsupported": saved_search_unsupported,
            "saved_search_queued_aged": saved_search_queued_aged,
            "identity_failed": identity_failed,
            "identity_queued_aged": identity_queued_aged,
            "oldest_failed_seconds": _age_seconds(now, oldest_failed_at),
        },
        "sms": sms,
        "imports": {"failed_24h": import_failures},
        "payments": {
            "failed": payment_failed,
            "pending_aged": pending_aged,
            "oldest_pending_seconds": _age_seconds(now, oldest_pending),
        },
        "exchange_rate": {
            "status": rate_status,
            "fetched_at": _aware(rate.fetched_at).isoformat() if rate and rate.fetched_at else None,
            "age_seconds": rate_age,
        },
        "error_delivery": error_delivery,
        "public_listing_index": {
            "store": public_store,
            "external_search": False,
            "parity": "same_store",
            "active_public_listings": public_count,
        },
        "backup": backup,
        "alerts": alerts,
    }
