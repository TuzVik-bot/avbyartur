"""Encrypt the newest local snapshot and deliver it off-host; record the result for the monitor.

Only an age-encrypted bundle leaves the host. The local ciphertext copy is
removed after each run because it can be recreated from the snapshot. On
success a private status file records which snapshot is the newest off-host
copy; scripts/monitor-runtime.py alerts when that copy gets too old.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENCRYPT_SCRIPT = SCRIPT_DIR / "backup-encrypt.py"
TRANSFER_SCRIPT = SCRIPT_DIR / "backup-offsite-encrypted.py"
SNAPSHOT_NAME = re.compile(r"avtorinok-(\d{8}T\d{6}Z)\Z", re.ASCII)
STATUS_NAME = "offsite-status.json"
RECIPIENT_ENV = "AVTORINOK_BACKUP_AGE_RECIPIENT"
TARGET_ENV = "AVTORINOK_OFFSITE_TARGET"
STATUS_LIMIT = 4096


def _log(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True), file=sys.stderr)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _snapshot_time(directory: Path) -> dt.datetime:
    match = SNAPSHOT_NAME.fullmatch(directory.name)
    assert match is not None
    return dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(
        tzinfo=dt.timezone.utc
    )


def newest_snapshot(backup_root: Path) -> Path | None:
    """Newest completed snapshot directory; partial or suffixed names are skipped."""

    candidates = [
        entry
        for entry in backup_root.iterdir()
        if SNAPSHOT_NAME.fullmatch(entry.name)
        and entry.is_dir()
        and not entry.is_symlink()
    ]
    return max(candidates, key=lambda entry: entry.name, default=None)


def _delivered_bundle(status_file: Path) -> str | None:
    try:
        raw = status_file.read_bytes()[:STATUS_LIMIT]
        payload = json.loads(raw)
    except (OSError, ValueError):
        return None
    bundle = payload.get("bundle") if isinstance(payload, dict) else None
    return bundle if isinstance(bundle, str) else None


def _write_status(status_file: Path, snapshot: Path, bundle_name: str) -> None:
    payload = {
        "schema_version": 1,
        "bundle": bundle_name,
        "snapshot_created_at_utc": _snapshot_time(snapshot).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "delivered_at_utc": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    descriptor, temporary = tempfile.mkstemp(
        prefix=".offsite-status-", dir=status_file.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        os.replace(temporary, status_file)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def run_daily(
    *, backup_root: Path, recipient: str, status_file: Path, runner=_run
) -> int:
    snapshot = newest_snapshot(backup_root)
    if snapshot is None:
        _log("offsite_backup_failed", reason="no_snapshot")
        return 1
    bundle_name = f"{snapshot.name}.tar.age"
    if _delivered_bundle(status_file) == bundle_name:
        _log("offsite_backup_current", bundle=bundle_name)
        return 0

    work_dir = Path(tempfile.mkdtemp(prefix=".offsite-work-", dir=backup_root))
    try:
        bundle = work_dir / bundle_name
        encrypt = runner(
            [
                sys.executable,
                str(ENCRYPT_SCRIPT),
                str(snapshot),
                "--recipient",
                recipient,
                "--output",
                str(bundle),
            ]
        )
        if encrypt.returncode != 0:
            _log(
                "offsite_backup_failed", reason="encrypt", stderr=encrypt.stderr[-500:]
            )
            return 1
        transfer = runner([sys.executable, str(TRANSFER_SCRIPT), str(bundle)])
        if transfer.returncode != 0:
            _log(
                "offsite_backup_failed",
                reason="transfer",
                stderr=transfer.stderr[-500:],
            )
            return 1
        _write_status(status_file, snapshot, bundle_name)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    _log("offsite_backup_delivered", bundle=bundle_name)
    return 0


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    environ = dict(os.environ) if environ is None else environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backup-root", type=Path, default=environ.get("AVTORINOK_BACKUP_DIR")
    )
    parser.add_argument(
        "--status-file", type=Path, help=f"defaults to BACKUP_ROOT/{STATUS_NAME}"
    )
    args = parser.parse_args(argv)
    recipient = environ.get(RECIPIENT_ENV, "").strip()
    if (
        args.backup_root is None
        or not recipient
        or not environ.get(TARGET_ENV, "").strip()
    ):
        parser.error(
            f"--backup-root (or AVTORINOK_BACKUP_DIR), {RECIPIENT_ENV} and {TARGET_ENV} are required"
        )
    backup_root = args.backup_root.resolve()
    if not backup_root.is_dir():
        parser.error("backup root is not a directory")
    status_file = args.status_file or backup_root / STATUS_NAME
    return run_daily(
        backup_root=backup_root, recipient=recipient, status_file=status_file
    )


if __name__ == "__main__":
    raise SystemExit(main())
