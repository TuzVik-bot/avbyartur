import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_BACKUP_SCRIPT = ROOT / "scripts" / "daily-backup.sh"

BACKUP_STUB = """#!/bin/sh
set -eu
printf 'backup\\n' >> "$DAILY_BACKUP_EVENT_LOG"
[ "${DAILY_BACKUP_FAIL:-0}" != 1 ] || exit 1
"""

PYTHON_STUB = """#!/bin/sh
set -eu
printf 'prune %s\\n' "$*" >> "$DAILY_BACKUP_EVENT_LOG"
"""


class DailyBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.scripts = self.project / "scripts"
        self.bin_dir = self.root / "bin"
        self.backup_root = self.root / "backups"
        self.events = self.root / "events.log"
        self.scripts.mkdir(parents=True)
        self.bin_dir.mkdir()
        self.daily_script = self.scripts / "daily-backup.sh"
        shutil.copy2(DAILY_BACKUP_SCRIPT, self.daily_script)
        self.write_executable(self.scripts / "backup.sh", BACKUP_STUB)
        self.write_executable(self.bin_dir / "python3", PYTHON_STUB)

    @staticmethod
    def write_executable(path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def run_daily_backup(self, *, fail_backup=False):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "AVTORINOK_BACKUP_DIR": str(self.backup_root),
                "DAILY_BACKUP_EVENT_LOG": str(self.events),
                "DAILY_BACKUP_FAIL": "1" if fail_backup else "0",
            }
        )
        return subprocess.run(
            [str(self.daily_script)],
            cwd=self.project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_retention_runs_after_backup_and_keeps_seven(self):
        result = self.run_daily_backup()

        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.events.read_text(encoding="utf-8").splitlines()
        self.assertEqual(events[0], "backup")
        self.assertTrue(events[1].startswith("prune "))
        self.assertTrue(events[1].endswith(f"{self.backup_root} --keep 7"))
        self.assertEqual(self.backup_root.stat().st_mode & 0o777, 0o700)

    def test_failed_backup_does_not_run_retention(self):
        result = self.run_daily_backup(fail_backup=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.events.read_text(encoding="utf-8").splitlines(), ["backup"]
        )


if __name__ == "__main__":
    unittest.main()
