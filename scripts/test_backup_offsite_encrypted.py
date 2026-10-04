import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup-offsite.sh"
ENCRYPTED_OFFSITE = ROOT / "scripts" / "backup-offsite-encrypted.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
_offsite_spec = importlib.util.spec_from_file_location(
    "backup_offsite_encrypted", ENCRYPTED_OFFSITE
)
assert _offsite_spec and _offsite_spec.loader
backup_offsite_encrypted = importlib.util.module_from_spec(_offsite_spec)
_offsite_spec.loader.exec_module(backup_offsite_encrypted)


class EncryptedOffsiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.remote_log = self.root / "remote.log"
        self.rsync_log = self.root / "rsync.log"
        self.bundle = self.root / "avtorinok-20261001T120000Z.tar.age"
        self.bundle.write_bytes(b"age-encryption.org/v1\nopaque-ciphertext\n")
        self.bundle.chmod(0o600)
        ssh = self.bin_dir / "ssh"
        ssh.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "REMOTE_COMMAND=\n"
            "for argument do REMOTE_COMMAND=$argument; done\n"
            "printf 'ssh %s\\n' \"$*\" >> \"$OFFSITE_REMOTE_LOG\"\n"
            "case \"$REMOTE_COMMAND\" in\n"
            "  *'df -Pk '* ) printf '%s\\n' \"${OFFSITE_FREE_KB:-999999}\"; exit \"${OFFSITE_SSH_PREFLIGHT_STATUS:-0}\" ;;\n"
            "  *'&& mkdir -m 700 '* ) exit \"${OFFSITE_SSH_CREATE_STATUS:-0}\" ;;\n"
            "  *'sha256sum -c -'* ) exit \"${OFFSITE_SSH_FINALIZE_STATUS:-0}\" ;;\n"
            "  *'&& test ! -e '* ) exit \"${OFFSITE_SSH_CREATE_STATUS:-0}\" ;;\n"
            "  * ) exit 0 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        ssh.chmod(0o755)
        rsync = self.bin_dir / "rsync"
        rsync.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "printf 'rsync %s\\n' \"$*\" >> \"$OFFSITE_RSYNC_LOG\"\n"
            "exit \"${OFFSITE_RSYNC_STATUS:-0}\"\n",
            encoding="utf-8",
        )
        rsync.chmod(0o755)

    def run_script(self, *arguments, **extra_env):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "OFFSITE_REMOTE_LOG": str(self.remote_log),
                "OFFSITE_RSYNC_LOG": str(self.rsync_log),
                "AVTORINOK_OFFSITE_TARGET": "backup@example.invalid:/archives/avtorinok",
            }
        )
        env.update(extra_env)
        return subprocess.run(
            [str(SCRIPT), "--encrypted-bundle", *arguments, str(self.bundle)],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_preflight_checks_remote_capacity_without_transfer_or_remote_writes(self):
        result = self.run_script("--preflight")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Encrypted bundle preflight OK", result.stdout)
        self.assertIn("StrictHostKeyChecking=yes", self.remote_log.read_text(encoding="utf-8"))
        self.assertFalse(self.rsync_log.exists())
        invocations = [
            line for line in self.remote_log.read_text(encoding="utf-8").splitlines() if line.startswith("ssh ")
        ]
        self.assertEqual(len(invocations), 1)

    def test_transfers_ciphertext_and_verifies_remote_hash_before_publish(self):
        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified encrypted bundle copied", result.stdout)
        rsync_log = self.rsync_log.read_text(encoding="utf-8")
        self.assertIn(self.bundle.name, rsync_log)
        self.assertIn("--archive", rsync_log)
        remote_log = self.remote_log.read_text(encoding="utf-8")
        self.assertIn("sha256sum -c -", remote_log)
        self.assertIn("mv -T -n", remote_log)

    def test_remote_verification_failure_does_not_claim_delivery(self):
        result = self.run_script(OFFSITE_SSH_FINALIZE_STATUS="1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr.lower())
        self.assertIn("retained", result.stderr.lower())

    def test_insufficient_remote_space_stops_before_rsync(self):
        result = self.run_script("--preflight", OFFSITE_FREE_KB="0")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("insufficient free space", result.stderr.lower())
        self.assertFalse(self.rsync_log.exists())

    def test_requires_an_explicit_remote_target_before_any_remote_command(self):
        result = self.run_script(AVTORINOK_OFFSITE_TARGET="")

        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.remote_log.exists())

    def test_rejects_a_plaintext_snapshot_directory_before_remote_access(self):
        result = subprocess.run(
            [str(SCRIPT), "--encrypted-bundle", "--preflight", str(self.root)],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
                "OFFSITE_REMOTE_LOG": str(self.remote_log),
                "OFFSITE_RSYNC_LOG": str(self.rsync_log),
                "AVTORINOK_OFFSITE_TARGET": "backup@example.invalid:/archives/avtorinok",
            },
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular file", result.stderr.lower())
        self.assertFalse(self.remote_log.exists())

    def test_source_path_replacement_after_validation_cannot_change_transferred_bytes(self):
        original_bytes = self.bundle.read_bytes()
        with backup_offsite_encrypted._bundle(
            self.bundle, stage_for_transfer=True
        ) as (bundle_copy, digest, size):
            replacement = self.root / "replacement"
            replacement.write_bytes(b"not-an-age-bundle-after-path-swap\n")
            replacement.chmod(0o644)
            os.replace(replacement, self.bundle)

            captured = {}
            real_run = subprocess.run

            def record_rsync(command, *args, **kwargs):
                if isinstance(command, (list, tuple)) and command and command[0] == "rsync":
                    source = Path(command[-2])
                    captured["source"] = source
                    captured["bytes"] = source.read_bytes()
                    return subprocess.CompletedProcess(command, 0, "", "")
                return real_run(command, *args, **kwargs)

            with mock.patch.dict(
                os.environ,
                {
                    "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                    "OFFSITE_REMOTE_LOG": str(self.remote_log),
                },
            ), mock.patch.object(
                backup_offsite_encrypted.subprocess,
                "run",
                side_effect=record_rsync,
            ):
                backup_offsite_encrypted._transfer(
                    "backup@example.invalid",
                    "/archives/avtorinok",
                    bundle_copy,
                    digest,
                )

            self.assertEqual(size, len(original_bytes))
            self.assertEqual(bundle_copy.name, self.bundle.name)
            self.assertNotEqual(bundle_copy, self.bundle)
            self.assertEqual(captured["source"], bundle_copy)
            self.assertNotEqual(captured["source"], self.bundle)
            self.assertEqual(captured["bytes"], original_bytes)
            self.assertEqual(hashlib.sha256(captured["bytes"]).hexdigest(), digest)
            self.assertEqual(self.bundle.read_bytes(), b"not-an-age-bundle-after-path-swap\n")

    def test_target_rejects_ssh_option_and_root_path_aliases(self):
        invalid_targets = (
            "-oProxyCommand=bad@backup.example.invalid:/archives",
            "backup@-oProxyCommand=bad:/archives",
            "backup@example.invalid:/.",
            "backup@example.invalid:/archives/.",
            "backup@example.invalid:/archives/./nested",
        )
        for target in invalid_targets:
            with self.subTest(target=target), self.assertRaises(
                backup_offsite_encrypted.OffsiteError
            ):
                backup_offsite_encrypted._target(target)

        self.assertEqual(
            backup_offsite_encrypted._target(
                "backup@example.invalid:/archives/avtorinok/"
            ),
            ("backup@example.invalid", "/archives/avtorinok"),
        )


if __name__ == "__main__":
    unittest.main()
