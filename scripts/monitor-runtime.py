#!/usr/bin/env python3
"""Collect safe local health aggregates for a closed Avtorinok deployment."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_snapshot import SnapshotError, validate_snapshot

EXPECTED_SERVICES = {"db", "api", "worker", "web"}
SNAPSHOT_NAME = re.compile(r"^avtorinok-(\d{8}T\d{6}Z)(?:\.[A-Za-z0-9_.-]+)?$")
SYSTEMD_TIMESTAMP = re.compile(r"^[A-Za-z]{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([A-Z0-9:+-]+)$")
ALERT_CODES = {
    "docker_unavailable",
    "container_unhealthy",
    "backup_service_failed",
    "backup_stale",
    "backup_missing",
    "backup_checksum_failed",
    "monitor_configuration",
    "health_endpoint_unavailable",
}
STATE_LIMIT = 4096
STATUS_LIMIT = 4096


class MonitorError(ValueError):
    """A local monitoring input is unsafe or malformed."""


def read_access_file(path: Path) -> tuple[str, str]:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}:
        raise MonitorError("access_file_unsafe")
    if metadata.st_uid != os.geteuid() or metadata.st_size > 1024:
        raise MonitorError("access_file_unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise MonitorError("access_file_unsafe")
        content = source.read(1025)
        after = os.fstat(source.fileno())
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise MonitorError("access_file_unsafe")
    if len(content) > 1024:
        raise MonitorError("access_file_unsafe")
    try:
        value = content.decode("utf-8").removesuffix("\n")
    except UnicodeDecodeError as exc:
        raise MonitorError("access_file_unsafe") from exc
    username, separator, password = value.partition(":")
    if not separator or not username or not password or any(character in username + password for character in "\r\n"):
        raise MonitorError("access_file_unsafe")
    return username, password


def check_health_endpoint(url: str, credentials: tuple[str, str], timeout: float = 8.0) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        return False
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    target = url.rstrip("/") + "/healthz"
    raw = f"{credentials[0]}:{credentials[1]}".encode()
    authorization = "Basic " + base64.b64encode(raw).decode("ascii")
    request = urllib.request.Request(target, headers={"Authorization": authorization, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _decode_compose_json(content: str) -> list[dict]:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    result = []
    for line in content.splitlines():
        if line.strip():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("invalid compose health output")
            result.append(item)
    return result


def check_docker_health(project_dir: Path, runner=subprocess.run) -> tuple[bool, list[str]]:
    try:
        result = runner(
            ["docker", "compose", "--project-directory", str(project_dir), "ps", "--format", "json"],
            check=False, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return False, ["docker_unavailable"]
        rows = _decode_compose_json(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return False, ["docker_unavailable"]
    services = {str(row.get("Service", "")): row for row in rows}
    if not EXPECTED_SERVICES.issubset(services):
        return False, ["container_unhealthy"]
    healthy = all(
        str(services[name].get("State", "")).lower() == "running"
        and str(services[name].get("Health", "")).lower() == "healthy"
        for name in EXPECTED_SERVICES
    )
    return healthy, [] if healthy else ["container_unhealthy"]


def _parse_utc_stamp(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def find_verified_backup(backup_root: Path) -> tuple[dt.datetime | None, bool]:
    try:
        root_stat = backup_root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode):
            return None, False
        candidates = []
        with os.scandir(backup_root) as entries:
            for entry in entries:
                match = SNAPSHOT_NAME.fullmatch(entry.name)
                if match is None or entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
                try:
                    created = _parse_utc_stamp(match.group(1))
                except ValueError:
                    continue
                candidates.append((created, Path(entry.path)))
    except OSError:
        return None, False
    if not candidates:
        return None, False
    created, directory = max(candidates, key=lambda item: item[0])
    try:
        validate_snapshot(directory)
        manifest = (directory / "manifest.txt").read_text(encoding="ascii")
        created_values = [line.partition("=")[2] for line in manifest.splitlines() if line.startswith("created_at_utc=")]
        if created_values != [created.strftime("%Y%m%dT%H%M%SZ")]:
            return created, False
    except (OSError, UnicodeError, SnapshotError):
        return created, False
    return created, True


def read_backup_service(runner=subprocess.run) -> tuple[str, dt.datetime | None]:
    try:
        result = runner(
            ["systemctl", "show", "--property=ActiveState", "--property=Result", "--property=ExecMainExitTimestamp", "--value", "avtorinok-backup.service"],
            check=False, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown", None
    if result.returncode != 0:
        return "unknown", None
    values = result.stdout.splitlines()
    if len(values) != 3:
        return "unknown", None
    active_state, result_state, timestamp = values
    if result_state == "failed":
        return "failed", None
    if result_state != "success":
        return "unknown", None
    if not timestamp:
        return "never_run", None
    match = SYSTEMD_TIMESTAMP.fullmatch(timestamp)
    if match is None:
        return "unknown", None
    try:
        local_stamp = match.group(1).replace(" ", "T")
        zone = match.group(2)
        if zone in {"UTC", "GMT", "+00", "+0000", "+00:00"}:
            parsed = dt.datetime.fromisoformat(local_stamp + "+00:00")
        elif re.fullmatch(r"[+-]\d{2}(?::?\d{2})?", zone):
            digits = zone[1:].replace(":", "")
            offset = zone[0] + digits[:2] + ":" + (digits[2:] or "00")
            parsed = dt.datetime.fromisoformat(local_stamp + offset)
        else:
            parsed = dt.datetime.fromisoformat(local_stamp).astimezone()
        parsed = parsed.astimezone(dt.timezone.utc)
    except ValueError:
        return "unknown", None
    del active_state  # A successful oneshot backup service is normally inactive.
    return "success", parsed


def _iso(value: dt.datetime | None) -> str | None:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if value else None


def collect_status(
    *,
    project_dir: Path,
    base_url: str,
    access_file: Path,
    backup_root: Path,
    now: dt.datetime | None = None,
    runner=subprocess.run,
    max_backup_age_hours: int = 36,
) -> dict:
    checked = now or dt.datetime.now(dt.timezone.utc)
    checked = checked.astimezone(dt.timezone.utc)
    alert_codes: list[str] = []
    try:
        credentials = read_access_file(access_file)
    except (OSError, MonitorError):
        credentials = None
        alert_codes.append("monitor_configuration")

    docker_healthy, docker_alerts = check_docker_health(project_dir, runner)
    alert_codes.extend(docker_alerts)
    if credentials is None or not check_health_endpoint(base_url, credentials):
        alert_codes.append("health_endpoint_unavailable")

    service_state, last_success = read_backup_service(runner)
    if service_state == "failed":
        alert_codes.append("backup_service_failed")
    elif service_state in {"unknown", "never_run"}:
        alert_codes.append("backup_missing")

    snapshot_created, checksum_ok = find_verified_backup(backup_root)
    if snapshot_created is None:
        alert_codes.append("backup_missing")
    elif not checksum_ok:
        alert_codes.append("backup_checksum_failed")
    elif checked - snapshot_created > dt.timedelta(hours=max_backup_age_hours):
        alert_codes.append("backup_stale")
    if (
        last_success is not None
        and checked - last_success > dt.timedelta(hours=max_backup_age_hours)
        and "backup_stale" not in alert_codes
    ):
        alert_codes.append("backup_stale")

    alert_codes = sorted(set(alert_codes))
    return {
        "schema_version": 1,
        "status": "action_required" if alert_codes else "healthy",
        "checked_at_utc": _iso(checked),
        "docker_healthy": docker_healthy,
        "backup_service_state": service_state,
        "backup_last_success_at_utc": _iso(last_success),
        "backup_snapshot_created_at_utc": _iso(snapshot_created),
        "backup_checksums_valid": checksum_ok if snapshot_created is not None else None,
        "backup_checksums_checked_at_utc": _iso(checked) if snapshot_created is not None else None,
        "alert_codes": alert_codes,
    }


def _read_state(path: Path) -> set[str] | None:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > STATE_LIMIT:
            return None
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as source:
            raw = source.read(STATE_LIMIT + 1)
        if len(raw) > STATE_LIMIT:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"alert_codes"}:
            return None
        codes = payload["alert_codes"]
        if not isinstance(codes, list) or any(not isinstance(code, str) or code not in ALERT_CODES for code in codes):
            return None
        return set(codes)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _atomic_write_private(path: Path, payload: bytes) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise MonitorError("state_directory_unavailable")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".monitor-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def store_private_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    if len(encoded) > STATUS_LIMIT:
        raise MonitorError("status_too_large")
    _atomic_write_private(path, encoded)


def update_alert_state(path: Path, current_codes: list[str]) -> tuple[bool, list[str]]:
    previous = _read_state(path)
    current = set(current_codes)
    changed = previous is None or previous != current
    new_codes = sorted(current - (previous or set())) if changed else []
    _atomic_write_private(path, (json.dumps({"alert_codes": sorted(current)}, separators=(",", ":")) + "\n").encode("ascii"))
    return changed, new_codes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True, help="Basic-Auth-protected pilot origin")
    parser.add_argument("--access-file", type=Path, required=True, help="Protected file containing user:password")
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--status-owner-uid", type=int)
    parser.add_argument("--max-backup-age-hours", type=int, default=36)
    args = parser.parse_args(argv)
    if not 1 <= args.max_backup_age_hours <= 168:
        parser.error("--max-backup-age-hours must be between 1 and 168")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.project_dir.is_dir() or args.project_dir.is_symlink():
        report = {
            "schema_version": 1,
            "status": "action_required",
            "checked_at_utc": _iso(dt.datetime.now(dt.timezone.utc)),
            "docker_healthy": False,
            "backup_service_state": "unknown",
            "backup_last_success_at_utc": None,
            "backup_snapshot_created_at_utc": None,
            "backup_checksums_valid": None,
            "backup_checksums_checked_at_utc": None,
            "alert_codes": ["monitor_configuration"],
        }
    else:
        report = collect_status(
            project_dir=args.project_dir,
            base_url=args.base_url,
            access_file=args.access_file,
            backup_root=args.backup_root,
            max_backup_age_hours=args.max_backup_age_hours,
        )
    try:
        changed, new_codes = update_alert_state(args.state_file, report["alert_codes"])
        store_private_json(args.status_file, report)
        if args.status_owner_uid is not None:
            os.chown(args.status_file, args.status_owner_uid, -1, follow_symlinks=False)
    except (OSError, MonitorError):
        print(json.dumps({"status": "action_required", "alert_codes": ["monitor_configuration"]}, sort_keys=True))
        return 2
    public_report = {
        "status": report["status"],
        "checked_at_utc": report["checked_at_utc"],
        "docker_healthy": report["docker_healthy"],
        "backup_service_state": report["backup_service_state"],
        "backup_last_success_at_utc": report["backup_last_success_at_utc"],
        "backup_snapshot_created_at_utc": report["backup_snapshot_created_at_utc"],
        "backup_checksums_valid": report["backup_checksums_valid"],
        "alert_count": len(report["alert_codes"]),
        "alerts_changed": changed,
        "new_alert_codes": new_codes,
    }
    print(json.dumps(public_report, sort_keys=True, separators=(",", ":")))
    return 1 if report["alert_codes"] else 0


if __name__ == "__main__":
    sys.exit(main())
