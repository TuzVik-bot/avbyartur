import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup-offsite.sh"
V1_FILES = ("database.dump", "private-media.tar.gz", "catalog.json", "catalog-coverage.json", "manifest.txt")
BATCH1_FILES = ("drom-batch-01-1-10-makes.csv", "drom-batch-01-1-10-makes-report.json")
BATCH2_FILES = (
    "drom-batch-02-10-makes.csv",
    "drom-batch-02-10-makes.json",
    "drom-batch-02-10-makes-report.json",
)
BATCH3_FILES = (
    "drom-batch-03-10-makes.csv",
    "drom-batch-03-10-makes.json",
    "drom-batch-03-10-makes-report.json",
)
BATCH4_9_FILES = tuple(
    f"drom-batch-{batch:02d}-10-makes{suffix}"
    for batch in range(4, 10)
    for suffix in (".csv", ".json", "-report.json")
)
V2_FILES = V1_FILES[:-1] + BATCH1_FILES + ("manifest.txt",)
V3_FILES = V1_FILES[:-1] + BATCH1_FILES + BATCH2_FILES + ("manifest.txt",)
V4_FILES = V1_FILES[:-1] + BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + ("manifest.txt",)
V5_FILES = V1_FILES[:-1] + BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + BATCH4_9_FILES + ("manifest.txt",)


class OffsiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.remote_log = self.root / "remote.log"
        self.backup = self.root / "avtorinok-20260927T120000Z"
        self.backup.mkdir()
        self.write_snapshot(2)

        ssh = self.bin_dir / "ssh"
        ssh.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "REMOTE_COMMAND=\n"
            "for argument do REMOTE_COMMAND=$argument; done\n"
            "printf 'ssh %s\\n' \"$*\" >> \"$OFFSITE_REMOTE_LOG\"\n"
            "case \"$REMOTE_COMMAND\" in\n"
            "  *'df -Pk '* ) printf '999999\\n'; exit \"${OFFSITE_SSH_PREFLIGHT_STATUS:-0}\" ;;\n"
            "  *'cd '*'sha256sum -c SHA256SUMS'* ) exit \"${OFFSITE_SSH_FINALIZE_STATUS:-${OFFSITE_SSH_VERIFY_STATUS:-0}}\" ;;\n"
            "  *'&& test ! -e '* ) exit \"${OFFSITE_SSH_PRECHECK_STATUS:-0}\" ;;\n"
            "  * ) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        ssh.chmod(0o755)
        rsync = self.bin_dir / "rsync"
        rsync.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "printf 'rsync %s\\n' \"$*\" >> \"$OFFSITE_REMOTE_LOG\"\n"
            "exit \"${OFFSITE_RSYNC_STATUS:-0}\"\n",
            encoding="utf-8",
        )
        rsync.chmod(0o755)

    def write_checksums(self):
        lines = []
        for name in self.files:
            digest = hashlib.sha256((self.backup / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
        (self.backup / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")

    def write_snapshot(self, version):
        if version == 1:
            for name in BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + BATCH4_9_FILES:
                (self.backup / name).unlink(missing_ok=True)
            self.files = V1_FILES
        elif version == 2:
            for name in BATCH1_FILES:
                (self.backup / name).write_text(f"snapshot {name}\n", encoding="utf-8")
            for name in BATCH2_FILES + BATCH3_FILES:
                (self.backup / name).unlink(missing_ok=True)
            self.files = V2_FILES
        elif version == 3:
            for name in BATCH1_FILES + BATCH2_FILES:
                (self.backup / name).write_text(f"snapshot {name}\n", encoding="utf-8")
            for name in BATCH3_FILES + BATCH4_9_FILES:
                (self.backup / name).unlink(missing_ok=True)
            self.files = V3_FILES
        elif version == 4:
            for name in BATCH1_FILES + BATCH2_FILES + BATCH3_FILES:
                (self.backup / name).write_text(f"snapshot {name}\n", encoding="utf-8")
            for name in BATCH4_9_FILES:
                (self.backup / name).unlink(missing_ok=True)
            self.files = V4_FILES
        else:
            for name in BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + BATCH4_9_FILES:
                (self.backup / name).write_text(f"snapshot {name}\n", encoding="utf-8")
            self.files = V5_FILES
        for name in V1_FILES[:-1]:
            (self.backup / name).write_text(f"snapshot {name}\n", encoding="utf-8")
        manifest = [
            f"format_version={version}",
            "created_at_utc=20260927T120000Z",
        ]
        if version == 1:
            manifest.append("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json")
        elif version == 2:
            manifest.append("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json")
            manifest.append("licensed_data_classification=proprietary-permissioned")
        elif version == 3:
            manifest.append("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json")
            manifest.append("licensed_data_classification=proprietary-permissioned")
        elif version == 4:
            manifest.append("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json,drom-batch-03-10-makes.csv,drom-batch-03-10-makes.json,drom-batch-03-10-makes-report.json")
            manifest.append("licensed_data_classification=proprietary-permissioned")
        else:
            manifest.append("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json," + ",".join(BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + BATCH4_9_FILES))
            manifest.append("licensed_data_classification=proprietary-permissioned")
        (self.backup / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="ascii")
        self.write_checksums()

    def run_script(self, **extra_env):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "OFFSITE_REMOTE_LOG": str(self.remote_log),
                "AVTORINOK_OFFSITE_TARGET": "backup@example.invalid:/archives/avtorinok",
            }
        )
        env.update(extra_env)
        return subprocess.run(
            [str(SCRIPT), str(self.backup)], text=True, capture_output=True, env=env, check=False
        )

    def test_requires_explicit_remote_target_before_any_remote_command(self):
        result = self.run_script(AVTORINOK_OFFSITE_TARGET="")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no remote copy was attempted", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_rejects_changed_snapshot_before_transport(self):
        (self.backup / "database.dump").write_text("changed\n", encoding="utf-8")
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_legacy_version_one_snapshot_remains_eligible_for_offsite_copy(self):
        self.write_snapshot(1)

        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified snapshot copied", result.stdout)

    def test_version_three_snapshot_with_both_licensed_batches_is_eligible(self):
        self.write_snapshot(3)

        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified snapshot copied", result.stdout)

    def test_rejects_tampered_v3_licensed_json_before_transport(self):
        self.write_snapshot(3)
        (self.backup / "drom-batch-02-10-makes.json").write_text("changed\n", encoding="utf-8")

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_rejects_missing_v3_licensed_file_before_transport(self):
        self.write_snapshot(3)
        (self.backup / "drom-batch-02-10-makes-report.json").unlink()

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or contains an unsafe entry", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_valid_v4_snapshot_with_all_three_batches_is_eligible(self):
        self.write_snapshot(4)

        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified snapshot copied", result.stdout)
        self.assertIn("rsync ", self.remote_log.read_text(encoding="utf-8"))

    def test_rejects_tampered_v4_batch_three_json_before_transport(self):
        self.write_snapshot(4)
        (self.backup / BATCH3_FILES[1]).write_text("changed\n", encoding="utf-8")

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_rejects_missing_v4_batch_three_file_before_transport(self):
        self.write_snapshot(4)
        (self.backup / BATCH3_FILES[-1]).unlink()

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or contains an unsafe entry", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_valid_v5_snapshot_with_batches_one_through_nine_is_eligible(self):
        self.write_snapshot(5)

        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified snapshot copied", result.stdout)
        self.assertIn("rsync ", self.remote_log.read_text(encoding="utf-8"))

    def test_rejects_tampered_v5_batch_nine_json_before_transport(self):
        self.write_snapshot(5)
        (self.backup / "drom-batch-09-10-makes.json").write_text("changed\n", encoding="utf-8")

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_rejects_missing_v5_batch_seven_file_before_transport(self):
        self.write_snapshot(5)
        (self.backup / "drom-batch-07-10-makes-report.json").unlink()

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete or contains an unsafe entry", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_verified_snapshot_uses_staging_and_remote_finalization(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.remote_log.read_text(encoding="utf-8")
        self.assertIn("-o BatchMode=yes -o StrictHostKeyChecking=yes", commands)
        self.assertIn("mkdir '/archives/avtorinok/.avtorinok-20260927T120000Z.incoming.", commands)
        self.assertIn("rsync -e ssh -o BatchMode=yes -o StrictHostKeyChecking=yes --archive --", commands)
        self.assertIn("sha256sum -c SHA256SUMS", commands)
        self.assertIn("mv -T -n -- '/archives/avtorinok/.avtorinok-20260927T120000Z.incoming.", commands)
        self.assertIn("test ! -e '/archives/avtorinok/.avtorinok-20260927T120000Z.incoming.", commands)

    def test_preflight_verifies_snapshot_and_remote_without_writing(self):
        result = subprocess.run(
            [str(SCRIPT), "--preflight", str(self.backup)],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
                "OFFSITE_REMOTE_LOG": str(self.remote_log),
                "AVTORINOK_OFFSITE_TARGET": "backup@example.invalid:/archives/avtorinok",
            },
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Off-host preflight OK", result.stdout)
        commands = self.remote_log.read_text(encoding="utf-8")
        self.assertTrue(commands.startswith("ssh "))
        self.assertNotIn("\nrsync ", commands)
        self.assertNotIn("mkdir ", commands)
        self.assertNotIn("mv -T", commands)

    def test_transfer_error_fails_and_does_not_delete_remote_staging(self):
        result = self.run_script(OFFSITE_RSYNC_STATUS="23")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("staging data was retained", result.stderr)
        commands = self.remote_log.read_text(encoding="utf-8")
        self.assertNotIn("mv ", commands)
        self.assertNotIn("rm -", commands)

    def test_destination_collision_is_reported_without_transfer(self):
        result = self.run_script(OFFSITE_SSH_PRECHECK_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertNotIn("rsync ", self.remote_log.read_text(encoding="utf-8"))

    def test_rejects_unmanifested_top_level_files_before_transport(self):
        (self.backup / "unmanifested.txt").write_text("not in snapshot\n", encoding="utf-8")

        result = self.run_script()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected top-level entries", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_concurrent_final_destination_collision_does_not_finalize_or_succeed(self):
        result = self.run_script(OFFSITE_SSH_FINALIZE_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("finalization failed", result.stderr)
        self.assertNotIn("Verified snapshot copied", result.stdout)
        commands = self.remote_log.read_text(encoding="utf-8")
        self.assertIn("mv -T -n --", commands)
        self.assertIn("&& test ! -e '/archives/avtorinok/.avtorinok-20260927T120000Z.incoming.", commands)
        self.assertNotIn("rm -", commands)


if __name__ == "__main__":
    unittest.main()
