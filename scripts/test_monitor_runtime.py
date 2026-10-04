from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SCRIPT_PATH = Path(__file__).with_name("monitor-runtime.py")
SPEC = importlib.util.spec_from_file_location("monitor_runtime", SCRIPT_PATH)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class MonitorRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_snapshot(self, when: datetime) -> Path:
        stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.root / f"avtorinok-{stamp}"
        path.mkdir(mode=0o700)
        files = {
            "database.dump": b"database bytes",
            "private-media.tar.gz": b"media bytes",
            "catalog.json": b"{}\n",
            "catalog-coverage.json": b"{}\n",
        }
        for name, payload in files.items():
            file_path = path / name
            file_path.write_bytes(payload)
            file_path.chmod(0o600)
        files["manifest.txt"] = (
            "format_version=1\n"
            f"created_at_utc={stamp}\n"
            "includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json\n"
        ).encode("ascii")
        (path / "manifest.txt").write_bytes(files["manifest.txt"])
        (path / "manifest.txt").chmod(0o600)
        checksums = "".join(f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in files.items())
        (path / "SHA256SUMS").write_text(checksums, encoding="ascii")
        (path / "SHA256SUMS").chmod(0o600)
        return path

    def test_access_file_requires_private_regular_file_owned_by_current_user(self):
        access = self.root / "access"
        access.write_text("monitor:pw:with:colon\n", encoding="utf-8")
        access.chmod(0o600)
        self.assertEqual(monitor.read_access_file(access), ("monitor", "pw:with:colon"))
        access.chmod(0o400)
        self.assertEqual(monitor.read_access_file(access), ("monitor", "pw:with:colon"))
        access.chmod(0o700)
        with self.assertRaises(monitor.MonitorError):
            monitor.read_access_file(access)
        access.chmod(0o640)
        with self.assertRaises(monitor.MonitorError):
            monitor.read_access_file(access)
        access.unlink()
        target = self.root / "real-access"
        target.write_text("monitor:private", encoding="utf-8")
        target.chmod(0o600)
        access.symlink_to(target)
        with self.assertRaises(monitor.MonitorError):
            monitor.read_access_file(access)

    def test_backup_freshness_uses_verified_manifest_timestamp_and_checksums(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        root = self.root / "backups"
        root.mkdir(mode=0o700)
        valid = self.make_snapshot(now)
        valid.rename(root / valid.name)
        timestamp, checksums_valid = monitor.find_verified_backup(root)
        self.assertEqual(timestamp, now)
        self.assertTrue(checksums_valid)
        latest = root / valid.name
        (latest / "database.dump").write_bytes(b"changed")
        timestamp, checksums_valid = monitor.find_verified_backup(root)
        self.assertEqual(timestamp, now)
        self.assertFalse(checksums_valid)

    def test_docker_health_requires_all_expected_services(self):
        healthy = [
            {"Service": name, "State": "running", "Health": "healthy"}
            for name in sorted(monitor.EXPECTED_SERVICES)
        ]

        def runner(*_args, **_kwargs):
            return SimpleNamespace(returncode=0, stdout=json.dumps(healthy), stderr="")

        self.assertEqual(monitor.check_docker_health(self.root, runner), (True, []))
        unhealthy = list(healthy)
        unhealthy[0] = {**unhealthy[0], "Health": "unhealthy"}
        self.assertEqual(
            monitor.check_docker_health(
                self.root,
                lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(unhealthy), stderr=""),
            ),
            (False, ["container_unhealthy"]),
        )

    def test_backup_timer_status_is_read_as_safe_state_and_timestamp(self):
        output = "inactive\nsuccess\nThu 2026-10-01 03:15:00 UTC\n"
        state, timestamp = monitor.read_backup_service(
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=output, stderr="")
        )
        self.assertEqual(state, "success")
        self.assertEqual(timestamp.tzinfo, timezone.utc)
        self.assertEqual(timestamp.isoformat(), "2026-10-01T03:15:00+00:00")
        state, timestamp = monitor.read_backup_service(
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="inactive\nfailed\n\n", stderr="")
        )
        self.assertEqual((state, timestamp), ("failed", None))

    def test_alert_state_suppresses_unchanged_codes_and_stays_private(self):
        state = self.root / "state.json"
        state.parent.chmod(0o700)
        changed, new_codes = monitor.update_alert_state(state, ["backup_stale"])
        self.assertTrue(changed)
        self.assertEqual(new_codes, ["backup_stale"])
        changed, new_codes = monitor.update_alert_state(state, ["backup_stale"])
        self.assertFalse(changed)
        self.assertEqual(new_codes, [])
        self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)
        self.assertEqual(json.loads(state.read_text()), {"alert_codes": ["backup_stale"]})


if __name__ == "__main__":
    unittest.main()
