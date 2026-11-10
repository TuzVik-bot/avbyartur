from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).with_name("backup-offsite-daily.py")
SPEC = importlib.util.spec_from_file_location("backup_offsite_daily", SCRIPT_PATH)
assert SPEC and SPEC.loader
daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(daily)

RECIPIENT = "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqs3290gq"


class FakeRunner:
    def __init__(self, *, encrypt_status: int = 0, transfer_status: int = 0):
        self.calls: list[list[str]] = []
        self.encrypt_status = encrypt_status
        self.transfer_status = transfer_status

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        script = Path(command[1]).name
        if script == "backup-encrypt.py":
            output = Path(command[command.index("--output") + 1])
            if self.encrypt_status == 0:
                output.write_bytes(b"age-encryption.org/v1\nciphertext")
            return subprocess.CompletedProcess(command, self.encrypt_status, "", "")
        return subprocess.CompletedProcess(command, self.transfer_status, "", "")


class DailyOffsiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "backups"
        self.root.mkdir(mode=0o700)
        for name in ("avtorinok-20261108T031500Z", "avtorinok-20261109T031500Z", "avtorinok-20261110T031500Z.partial"):
            (self.root / name).mkdir()
        (self.root / "avtorinok-20261111T031500Z.tar.age").write_bytes(b"not a directory")
        self.status = self.root / "offsite-status.json"

    def run_daily(self, runner: FakeRunner) -> int:
        return daily.run_daily(
            backup_root=self.root,
            recipient=RECIPIENT,
            status_file=self.status,
            runner=runner,
        )

    def test_newest_completed_snapshot_is_selected(self):
        self.assertEqual(daily.newest_snapshot(self.root).name, "avtorinok-20261109T031500Z")

    def test_success_encrypts_transfers_and_records_status(self):
        runner = FakeRunner()

        result = self.run_daily(runner)

        self.assertEqual(result, 0)
        encrypt, transfer = runner.calls
        self.assertEqual(Path(encrypt[1]).name, "backup-encrypt.py")
        self.assertIn(RECIPIENT, encrypt)
        self.assertEqual(Path(transfer[1]).name, "backup-offsite-encrypted.py")
        self.assertNotIn("--preflight", transfer)
        bundle = Path(transfer[-1])
        self.assertEqual(bundle.name, "avtorinok-20261109T031500Z.tar.age")
        self.assertFalse(bundle.exists(), "local ciphertext copy must be removed after delivery")
        payload = json.loads(self.status.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["snapshot_created_at_utc"], "2026-11-09T03:15:00Z")
        self.assertEqual(payload["bundle"], "avtorinok-20261109T031500Z.tar.age")
        self.assertEqual(stat.S_IMODE(self.status.stat().st_mode), 0o600)

    def test_transfer_failure_keeps_previous_status_and_removes_bundle(self):
        self.status.write_text('{"previous": true}', encoding="utf-8")
        runner = FakeRunner(transfer_status=1)

        result = self.run_daily(runner)

        self.assertEqual(result, 1)
        self.assertEqual(self.status.read_text(encoding="utf-8"), '{"previous": true}')
        self.assertFalse(Path(runner.calls[-1][-1]).exists())

    def test_encryption_failure_does_not_transfer(self):
        runner = FakeRunner(encrypt_status=1)

        result = self.run_daily(runner)

        self.assertEqual(result, 1)
        self.assertEqual(len(runner.calls), 1)
        self.assertFalse(self.status.exists())

    def test_snapshot_already_delivered_is_not_sent_twice(self):
        self.run_daily(FakeRunner())
        runner = FakeRunner()

        result = self.run_daily(runner)

        self.assertEqual(result, 0)
        self.assertEqual(runner.calls, [])

    def test_missing_snapshot_fails(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()

        result = daily.run_daily(backup_root=empty, recipient=RECIPIENT, status_file=empty / "s.json", runner=FakeRunner())

        self.assertEqual(result, 1)

    def test_main_requires_recipient_and_target(self):
        with self.assertRaises(SystemExit) as raised:
            daily.main(["--backup-root", str(self.root)], environ={})

        self.assertEqual(raised.exception.code, 2)


class SystemdUnitTests(unittest.TestCase):
    UNIT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "systemd"

    def test_daily_offsite_unit_runs_encrypted_delivery(self):
        service = (self.UNIT_DIR / "avtorinok-offsite-backup.service").read_text(encoding="utf-8")
        timer = (self.UNIT_DIR / "avtorinok-offsite-backup.timer").read_text(encoding="utf-8")

        self.assertIn("scripts/backup-offsite-daily.py", service)
        self.assertIn("EnvironmentFile=/etc/avtorinok/offsite-backup.env", service)
        self.assertIn("Unit=avtorinok-offsite-backup.service", timer)

    def test_monitor_checks_offsite_freshness(self):
        monitor_unit = (self.UNIT_DIR / "avtorinok-monitor.service").read_text(encoding="utf-8")

        self.assertIn("--offsite-status-file /home/suite/backups/avtorinok/offsite-status.json", monitor_unit)
        self.assertIn("--max-offsite-age-hours 48", monitor_unit)


if __name__ == "__main__":
    unittest.main()
