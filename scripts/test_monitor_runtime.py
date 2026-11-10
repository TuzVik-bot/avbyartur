from __future__ import annotations

import contextlib
import hashlib
import io
import importlib.util
import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


    def test_site_identity_requires_avtorinok_title(self):
        def page(html):
            return lambda _url, _timeout: (200, html.encode("utf-8"))

        good = "<html><head><title>Автомобили Беларуси | Авторынок</title></head></html>"
        self.assertTrue(monitor.check_site_identity("https://example.test", fetch=page(good)))
        self.assertFalse(monitor.check_site_identity("https://example.test", fetch=page("<title>AURUM</title>")))
        self.assertFalse(monitor.check_site_identity("https://example.test", fetch=lambda _u, _t: (502, b"")))
        self.assertFalse(monitor.check_site_identity("http://public.example", fetch=page(good)))

        def broken(_url, _timeout):
            raise OSError("down")

        self.assertFalse(monitor.check_site_identity("https://example.test", fetch=broken))

    def test_wrong_site_title_raises_health_alert(self):
        access = self.root / "access"
        access.write_text("monitor:pw\n", encoding="utf-8")
        access.chmod(0o600)
        original_health, original_identity = monitor.check_health_endpoint, monitor.check_site_identity
        monitor.check_health_endpoint = lambda *_args, **_kwargs: True
        monitor.check_site_identity = lambda *_args, **_kwargs: False
        try:
            report = monitor.collect_status(
                project_dir=self.root,
                base_url="https://example.test",
                access_file=access,
                backup_root=self.root / "missing",
                runner=lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr=""),
            )
        finally:
            monitor.check_health_endpoint, monitor.check_site_identity = original_health, original_identity
        self.assertIn("health_endpoint_unavailable", report["alert_codes"])

    def test_alert_config_reads_environment_then_private_file(self):
        self.assertIsNone(monitor.read_alert_config({}, None))
        env = {"MONITOR_TELEGRAM_BOT_TOKEN": "123:abc", "MONITOR_TELEGRAM_CHAT_ID": "-100"}
        self.assertEqual(monitor.read_alert_config(env, None), ("123:abc", "-100"))
        alert_file = self.root / "alerts.env"
        alert_file.write_text("# comment\nMONITOR_TELEGRAM_BOT_TOKEN=999:file\nMONITOR_TELEGRAM_CHAT_ID='42'\n", encoding="utf-8")
        alert_file.chmod(0o600)
        self.assertEqual(monitor.read_alert_config({}, alert_file), ("999:file", "42"))
        alert_file.chmod(0o644)
        self.assertIsNone(monitor.read_alert_config({}, alert_file))
        self.assertIsNone(monitor.read_alert_config({}, self.root / "absent.env"))

    def test_alert_notification_only_on_state_change_and_never_leaks_token(self):
        sent = []

        def sender(url, data, timeout):
            sent.append((url, data, timeout))

        config = ("123:secret-token", "42")
        self.assertFalse(monitor.notify_alert_changes(config, {"backup_stale"}, ["backup_stale"], "https://x.test", sender=sender))
        self.assertFalse(monitor.notify_alert_changes(config, None, [], "https://x.test", sender=sender))
        self.assertFalse(monitor.notify_alert_changes(None, set(), ["backup_stale"], "https://x.test", sender=sender))
        self.assertEqual(sent, [])

        self.assertTrue(monitor.notify_alert_changes(config, {"backup_stale"}, ["container_unhealthy"], "https://x.test", sender=sender))
        url, data, timeout = sent[0]
        self.assertEqual(url, "https://api.telegram.org/bot123:secret-token/sendMessage")
        self.assertEqual(timeout, 10)
        self.assertEqual(data["chat_id"], "42")
        self.assertIn("container_unhealthy", data["text"])
        self.assertIn("backup_stale", data["text"])
        self.assertNotIn("secret-token", data["text"])

        def failing(_url, _data, _timeout):
            raise OSError("https://api.telegram.org/bot123:secret-token/sendMessage unreachable")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertFalse(monitor.notify_alert_changes(config, set(), ["backup_stale"], "https://x.test", sender=failing))
        self.assertIn("telegram_alert_failed", stderr.getvalue())
        self.assertNotIn("secret-token", stderr.getvalue())

    def write_offsite_status(self, snapshot_created: datetime, mode: int = 0o600) -> Path:
        path = self.root / "offsite-status.json"
        path.write_text(
            json.dumps({
                "schema_version": 1,
                "bundle": "avtorinok-20261109T031500Z.tar.age",
                "snapshot_created_at_utc": snapshot_created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "delivered_at_utc": snapshot_created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }),
            encoding="utf-8",
        )
        path.chmod(mode)
        return path

    def test_offsite_copy_younger_than_limit_is_fresh(self):
        now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        path = self.write_offsite_status(now - timedelta(hours=47))

        self.assertFalse(monitor.offsite_backup_stale(path, now, 48))

    def test_offsite_copy_older_than_limit_is_stale(self):
        now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        path = self.write_offsite_status(now - timedelta(hours=49))

        self.assertTrue(monitor.offsite_backup_stale(path, now, 48))

    def test_missing_or_unsafe_offsite_status_is_stale(self):
        now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(monitor.offsite_backup_stale(self.root / "absent.json", now, 48))
        path = self.write_offsite_status(now, mode=0o644)
        self.assertTrue(monitor.offsite_backup_stale(path, now, 48))
        path.chmod(0o600)
        path.write_text("not json", encoding="utf-8")
        self.assertTrue(monitor.offsite_backup_stale(path, now, 48))

    def test_offsite_alert_only_when_status_file_is_configured(self):
        now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        runner = lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="")
        common = dict(
            project_dir=self.root,
            base_url="https://example.test",
            access_file=self.root / "missing-access",
            backup_root=self.root / "missing",
            now=now,
            runner=runner,
        )

        without = monitor.collect_status(**common)
        stale = monitor.collect_status(**common, offsite_status_file=self.root / "absent.json")

        self.assertNotIn("offsite_backup_stale", without["alert_codes"])
        self.assertIn("offsite_backup_stale", stale["alert_codes"])
        self.assertIn("offsite_backup_stale", monitor.ALERT_CODES)

    def test_parse_args_accepts_offsite_status_options(self):
        args = monitor.parse_args([
            "--project-dir", str(self.root), "--base-url", "https://example.test",
            "--access-file", "a", "--backup-root", "b", "--state-file", "c", "--status-file", "d",
            "--offsite-status-file", "e", "--max-offsite-age-hours", "48",
        ])

        self.assertEqual(args.offsite_status_file, Path("e"))
        self.assertEqual(args.max_offsite_age_hours, 48)


if __name__ == "__main__":
    unittest.main()
