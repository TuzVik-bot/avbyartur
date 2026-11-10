"""Off-host delivery accepts only age-encrypted bundles; plaintext snapshots never leave the host."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup-offsite.sh"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "backup-offsite-preflight.sh"


class PlaintextOffsiteForbiddenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.remote_log = self.root / "remote.log"
        self.backup = self.root / "avtorinok-20260927T120000Z"
        self.backup.mkdir()
        (self.backup / "database.dump").write_text("plaintext dump\n", encoding="utf-8")
        for tool in ("ssh", "rsync"):
            stub = self.bin_dir / tool
            stub.write_text(
                "#!/bin/sh\nprintf '%s %s\\n' \"$(basename \"$0\")\" \"$*\" >> \"$OFFSITE_REMOTE_LOG\"\nexit 0\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)

    def run_script(self, script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "OFFSITE_REMOTE_LOG": str(self.remote_log),
                "AVTORINOK_OFFSITE_TARGET": "backup@example.invalid:/archives/avtorinok",
            }
        )
        return subprocess.run([str(script), *arguments], text=True, capture_output=True, env=env, check=False)

    def test_plaintext_snapshot_transfer_is_refused_without_remote_contact(self):
        result = self.run_script(SCRIPT, str(self.backup))

        self.assertEqual(result.returncode, 2)
        self.assertIn("--encrypted-bundle", result.stderr)
        self.assertFalse(self.remote_log.exists())

    def test_plaintext_snapshot_preflight_is_refused_without_remote_contact(self):
        result = self.run_script(SCRIPT, "--preflight", str(self.backup))

        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.remote_log.exists())

    def test_preflight_wrapper_only_checks_encrypted_bundles(self):
        result = self.run_script(PREFLIGHT_SCRIPT, str(self.backup))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Encrypted off-host delivery failed", result.stderr)
        self.assertFalse(self.remote_log.exists())


if __name__ == "__main__":
    unittest.main()
