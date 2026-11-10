"""The host monitor's off-host backup alert reaches the admin monitoring snapshot."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.api import monitoring
from app.monitoring_schemas import HostMonitoringStatusFile


def _host_status(now: datetime, codes: list[str]) -> HostMonitoringStatusFile:
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return HostMonitoringStatusFile.model_validate({
        "schema_version": 1,
        "status": "action_required" if codes else "healthy",
        "checked_at_utc": stamp,
        "docker_healthy": True,
        "backup_service_state": "success",
        "backup_last_success_at_utc": stamp,
        "backup_snapshot_created_at_utc": stamp,
        "backup_checksums_valid": True,
        "backup_checksums_checked_at_utc": stamp,
        "alert_codes": codes,
    })


def test_offsite_backup_stale_host_code_is_reported_as_backup_alert(monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setattr(monitoring, "get_settings", lambda: SimpleNamespace(monitoring_status_path=Path("/status.json")))
    monkeypatch.setattr(monitoring, "_read_host_status", lambda path: _host_status(now, ["offsite_backup_stale"]))

    backup, alerts = monitoring._backup_snapshot(now)

    assert backup["status"] == "action_required"
    assert alerts == [{"code": "backup_stale", "severity": "high"}]
