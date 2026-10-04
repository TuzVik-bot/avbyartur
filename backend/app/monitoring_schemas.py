"""Typed, payload-free admin and host-monitor snapshots."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MonitoringAlertOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "worker_failed_jobs",
        "worker_backlog",
        "worker_expired_leases",
        "notification_delivery_failed",
        "notification_backlog",
        "identity_delivery_failed",
        "sms_delivery_failed",
        "feed_import_failed",
        "payment_failed",
        "payment_pending_aged",
        "exchange_rate_unavailable",
        "runtime_monitor_unavailable",
        "docker_unhealthy",
        "backup_failed",
        "backup_stale",
        "backup_checksum_failed",
    ]
    severity: Literal["low", "medium", "high"]
    count: int | None = None


class MonitoringQueueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed: int
    overdue: int
    oldest_overdue_seconds: int
    expired_leases: int
    oldest_expired_lease_seconds: int


class MonitoringNotificationsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_failed: int
    saved_search_unsupported: int
    saved_search_queued_aged: int
    identity_failed: int
    identity_queued_aged: int
    oldest_failed_seconds: int


class MonitoringSmsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sent_24h: int | None
    delivery_failed_24h: int | None
    delivery_suppressed_24h: int | None


class MonitoringImportsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed_24h: int


class MonitoringPaymentsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failed: int
    pending_aged: int
    oldest_pending_seconds: int


class MonitoringExchangeRateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["current", "stale", "unavailable"]
    fetched_at: str | None
    age_seconds: int | None


class MonitoringErrorDeliveryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    attempted: int | None
    accepted: int | None
    failed: int | None


class MonitoringPublicListingIndexOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store: Literal["postgresql", "sqlite", "other"]
    external_search: Literal[False]
    parity: Literal["same_store"]
    active_public_listings: int


class MonitoringBackupOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unconfigured", "ok", "action_required", "unavailable", "stale"]
    docker_healthy: bool | None
    backup_service_state: Literal["success", "failed", "never_run", "unknown"] | None
    backup_checksums_valid: bool | None
    backup_checksums_checked_at: str | None
    backup_last_success_at: str | None
    snapshot_created_at: str | None
    checked_at: str | None


class MonitoringSnapshotOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue: MonitoringQueueOut
    notifications: MonitoringNotificationsOut
    sms: MonitoringSmsOut
    imports: MonitoringImportsOut
    payments: MonitoringPaymentsOut
    exchange_rate: MonitoringExchangeRateOut
    error_delivery: MonitoringErrorDeliveryOut
    public_listing_index: MonitoringPublicListingIndexOut
    backup: MonitoringBackupOut
    alerts: list[MonitoringAlertOut]


class HostMonitoringStatusFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    status: Literal["healthy", "action_required"]
    checked_at_utc: str
    docker_healthy: bool
    backup_service_state: Literal["success", "failed", "never_run", "unknown"]
    backup_last_success_at_utc: str | None
    backup_snapshot_created_at_utc: str | None
    backup_checksums_valid: bool | None
    backup_checksums_checked_at_utc: str | None
    alert_codes: list[Literal[
        "docker_unavailable",
        "container_unhealthy",
        "backup_service_failed",
        "backup_stale",
        "backup_missing",
        "backup_checksum_failed",
        "monitor_configuration",
        "health_endpoint_unavailable",
    ]]
