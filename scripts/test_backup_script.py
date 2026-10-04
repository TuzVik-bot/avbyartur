import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "backup.sh"
BATCH_01_FILES = (
    "drom-batch-01-1-10-makes.csv",
    "drom-batch-01-1-10-makes-report.json",
)
BATCH_02_FILES = (
    "drom-batch-02-10-makes.csv",
    "drom-batch-02-10-makes.json",
    "drom-batch-02-10-makes-report.json",
)
BATCH_03_FILES = (
    "drom-batch-03-10-makes.csv",
    "drom-batch-03-10-makes.json",
    "drom-batch-03-10-makes-report.json",
)
BATCH_04_09_FILES = tuple(
    f"drom-batch-{batch:02d}-10-makes{suffix}"
    for batch in range(4, 10)
    for suffix in (".csv", ".json", "-report.json")
)

DOCKER_STUB = """#!/bin/sh
set -eu
operation="$*"
printf '%s\\n' "$operation" >> "$BACKUP_DOCKER_LOG"
case "$operation" in
    *"inspect --format"*api-id*api-id-duplicate*) printf 'inspect received ambiguous container IDs\n' >&2; exit 64 ;;
    *"inspect --format"*api-id) printf 'avtorinok-api:release-test|sha256:api-content\n' ;;
    *"inspect --format"*worker-id) printf 'avtorinok-api:release-test|sha256:worker-content\n' ;;
    *"inspect --format"*web-id) printf 'avtorinok-web:release-test|sha256:web-content\n' ;;
    *"ps -q --status running api"*)
        if [ "${BACKUP_DUPLICATE_SERVICE:-}" = api ]; then
            printf 'api-id\\napi-id-duplicate\\n'
        else
            printf 'api-id\\n'
        fi
        ;;
    *"ps -q --status running worker"*)
        if [ "${BACKUP_DUPLICATE_SERVICE:-}" = worker ]; then
            printf 'worker-id\\nworker-id-duplicate\\n'
        else
            printf 'worker-id\\n'
        fi
        ;;
    *"ps -q --status running web"*)
        if [ "$BACKUP_WEB_STOPPED" = 1 ]; then
            :
        elif [ "${BACKUP_DUPLICATE_SERVICE:-}" = web ]; then
            printf 'web-id\\nweb-id-duplicate\\n'
        else
            printf 'web-id\\n'
        fi
        ;;
    *"pg_database_size"*) printf '1024\\n' ;;
    *"pg_dump"*) printf 'database dump\\n' ;;
    *"getsize"*) printf '512\\n' ;;
    *"tarfile.open"*)
        [ "${BACKUP_FAIL_MEDIA:-0}" != 1 ] || exit 70
        printf 'media archive\\n'
        ;;
    *"stop web api worker"*) ;;
    *"start api"*) ;;
    *"start worker"*) ;;
    *"start web"*) ;;
    *) printf 'Unexpected docker command: %s\\n' "$operation" >&2; exit 64 ;;
esac
"""


class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.project = self.root / "project"
        self.scripts = self.project / "scripts"
        self.licensed_dir = self.project / "data" / "licensed"
        self.scripts.mkdir(parents=True)
        self.licensed_dir.mkdir(parents=True)
        self.backup_script = self.scripts / "backup.sh"
        shutil.copy2(BACKUP_SCRIPT, self.backup_script)
        (self.project / "data" / "catalog.json").write_text("catalog fixture\n", encoding="utf-8")
        (self.project / "data" / "catalog-coverage.json").write_text("coverage fixture\n", encoding="utf-8")
        for name, contents in zip(BATCH_01_FILES, (b"batch 1 source fixture\n", b"batch 1 report fixture\n")):
            (self.licensed_dir / name).write_bytes(contents)
        docker = self.bin_dir / "docker"
        docker.write_text(DOCKER_STUB, encoding="utf-8")
        docker.chmod(0o755)
        self.backup_root = self.root / "backups"
        self.log_path = self.root / "docker.log"

    def run_backup(self, minimum_free_kb, extra_env=None):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "BACKUP_DOCKER_LOG": str(self.log_path),
                "AVTORINOK_BACKUP_MIN_FREE_KB": str(minimum_free_kb),
                "BACKUP_WEB_STOPPED": "0",
            }
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.backup_script), "--output-dir", str(self.backup_root)],
            cwd=self.project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_insufficient_space_restores_services_and_leaves_no_staging_backup(self):
        result = self.run_backup(10_000_000_000)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Insufficient free space", result.stderr)
        commands = self.log_path.read_text(encoding="utf-8")
        self.assertIn("compose start api", commands)
        self.assertIn("compose start worker", commands)
        self.assertIn("compose start web", commands)
        self.assertEqual(list(self.backup_root.iterdir()), [])

    def test_media_export_failure_removes_staging_backup_and_restarts_services(self):
        result = self.run_backup(0, {"BACKUP_FAIL_MEDIA": "1"})

        self.assertNotEqual(result.returncode, 0)
        commands = self.log_path.read_text(encoding="utf-8")
        self.assertIn("tarfile.open", commands)
        self.assertIn("compose start api", commands)
        self.assertIn("compose start worker", commands)
        self.assertIn("compose start web", commands)
        self.assertEqual(list(self.backup_root.iterdir()), [])

    def test_stopped_service_is_recorded_as_unavailable_without_starting_it(self):
        result = self.run_backup(0, {"BACKUP_WEB_STOPPED": "1"})

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(self.backup_root.glob("avtorinok-*/"))
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("application_web_image=unavailable\n", manifest)
        self.assertIn("application_web_image_id=unavailable\n", manifest)

        commands = self.log_path.read_text(encoding="utf-8")
        self.assertNotIn("compose start web", commands)

    def test_ambiguous_running_service_fails_before_mutating_services_or_backup_root(self):
        result = self.run_backup(0, {"BACKUP_DUPLICATE_SERVICE": "api"})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ambiguous running Compose containers for service api", result.stderr)
        commands = self.log_path.read_text(encoding="utf-8")
        self.assertIn("compose ps -q --status running api", commands)
        self.assertNotIn("inspect --format", commands)
        self.assertNotIn("compose stop", commands)
        self.assertNotIn("compose start", commands)
        self.assertFalse(self.backup_root.exists())

    def test_success_writes_private_checksummed_backup_and_restarts_services(self):
        result = self.run_backup(0, {"AVTORINOK_IMAGE_TAG": "local"})

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(self.backup_root.glob("avtorinok-*/"))
        expected_files = {
            "database.dump",
            "private-media.tar.gz",
            "catalog.json",
            "catalog-coverage.json",
            "drom-batch-01-1-10-makes.csv",
            "drom-batch-01-1-10-makes-report.json",
            "manifest.txt",
            "SHA256SUMS",
        }
        self.assertEqual({path.name for path in backup_dir.iterdir()}, expected_files)
        self.assertEqual(backup_dir.stat().st_mode & 0o777, 0o700)
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("format_version=2\n", manifest)
        self.assertIn("application_api_image=avtorinok-api:release-test\n", manifest)
        self.assertIn("application_api_image_id=sha256:api-content\n", manifest)
        self.assertIn("application_worker_image=avtorinok-api:release-test\n", manifest)
        self.assertIn("application_worker_image_id=sha256:worker-content\n", manifest)
        self.assertIn("application_web_image=avtorinok-web:release-test\n", manifest)
        self.assertIn("application_web_image_id=sha256:web-content\n", manifest)
        self.assertIn("licensed_data_classification=proprietary-permissioned\n", manifest)
        licensed_csv = self.licensed_dir / BATCH_01_FILES[0]
        licensed_report = self.licensed_dir / BATCH_01_FILES[1]
        self.assertEqual((backup_dir / licensed_csv.name).read_bytes(), licensed_csv.read_bytes())
        self.assertEqual((backup_dir / licensed_report.name).read_bytes(), licensed_report.read_bytes())
        self.assertEqual(
            hashlib.sha256((backup_dir / licensed_csv.name).read_bytes()).hexdigest(),
            hashlib.sha256(b"batch 1 source fixture\n").hexdigest(),
        )
        for name in expected_files - {"SHA256SUMS"}:
            self.assertEqual((backup_dir / name).stat().st_mode & 0o777, 0o600)

        for line in (backup_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            expected_digest, name = line.split(maxsplit=1)
            name = name.strip().lstrip("*")
            actual_digest = hashlib.sha256((backup_dir / name).read_bytes()).hexdigest()
            self.assertEqual(actual_digest, expected_digest, name)

        commands = self.log_path.read_text(encoding="utf-8")
        self.assertIn("compose start api", commands)
        self.assertIn("compose start worker", commands)
        self.assertIn("compose start web", commands)

    def run_backup_without_licensed_sources(self, *, allow_empty=False):
        project = self.root / "empty-project"
        (project / "scripts").mkdir(parents=True)
        (project / "data").mkdir()
        (project / "data" / "catalog.json").write_text("catalog\n", encoding="utf-8")
        (project / "data" / "catalog-coverage.json").write_text("coverage\n", encoding="utf-8")
        script = project / "scripts" / "backup.sh"
        shutil.copy2(BACKUP_SCRIPT, script)
        output = self.root / ("legacy-backups" if allow_empty else "missing-backups")
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "BACKUP_DOCKER_LOG": str(self.log_path),
                "AVTORINOK_BACKUP_MIN_FREE_KB": "0",
                "BACKUP_WEB_STOPPED": "0",
            }
        )
        if allow_empty:
            env["AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED"] = "1"
        return subprocess.run(
            [str(script), "--output-dir", str(output)],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        ), output

    def test_backup_without_licensed_sources_fails_before_compose_by_default(self):
        result, output = self.run_backup_without_licensed_sources()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Required permissioned Drom artifacts", result.stderr)
        self.assertFalse(self.log_path.exists())
        self.assertFalse(output.exists())

    def test_explicit_missing_source_recovery_backup_uses_legacy_version_one_set(self):
        result, output = self.run_backup_without_licensed_sources(allow_empty=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(output.glob("avtorinok-*/"))
        expected_files = {
            "database.dump",
            "private-media.tar.gz",
            "catalog.json",
            "catalog-coverage.json",
            "manifest.txt",
            "SHA256SUMS",
        }
        self.assertEqual({path.name for path in backup_dir.iterdir()}, expected_files)
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("format_version=1\n", manifest)
        self.assertIn("includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json\n", manifest)
        self.assertNotIn("drom-batch-01-1-10-makes.csv", manifest)

    def test_batch_two_artifacts_use_version_three_and_are_checksummed(self):
        contents = {
            BATCH_02_FILES[0]: b"batch 2 source fixture\n",
            BATCH_02_FILES[1]: b"batch 2 normalized JSON fixture\n",
            BATCH_02_FILES[2]: b"batch 2 report fixture\n",
        }
        for name, payload in contents.items():
            (self.licensed_dir / name).write_bytes(payload)

        result = self.run_backup(0)

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(self.backup_root.glob("avtorinok-*/"))
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("format_version=3\n", manifest)
        for name, payload in contents.items():
            self.assertEqual((backup_dir / name).read_bytes(), payload)
        expected_names = {
            "database.dump",
            "private-media.tar.gz",
            "catalog.json",
            "catalog-coverage.json",
            *BATCH_01_FILES,
            *BATCH_02_FILES,
            "manifest.txt",
        }
        checksum_lines = (backup_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual({line.split(maxsplit=1)[1].strip() for line in checksum_lines}, expected_names)
        for name in BATCH_02_FILES:
            expected_digest, _ = next(line.split(maxsplit=1) for line in checksum_lines if line.endswith(name))
            self.assertEqual(hashlib.sha256((backup_dir / name).read_bytes()).hexdigest(), expected_digest)
            self.assertEqual((backup_dir / name).stat().st_mode & 0o777, 0o600)
        self.assertIn("licensed_drom_batch_02_source_bytes=", manifest)
        self.assertIn("licensed_drom_batch_02_data_bytes=", manifest)
        self.assertIn("licensed_drom_batch_02_report_bytes=", manifest)

    def test_partial_batch_two_set_fails_before_compose(self):
        for name in BATCH_02_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        (self.licensed_dir / BATCH_02_FILES[-1]).unlink()

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Batch 2 permissioned Drom artifacts must be a complete", result.stderr)
        self.assertFalse(self.log_path.exists())
        self.assertFalse(self.backup_root.exists())

    def test_batch_three_artifacts_use_version_four_and_are_checksummed(self):
        contents = {
            **{name: f"batch 2 fixture: {name}\n".encode() for name in BATCH_02_FILES},
            BATCH_03_FILES[0]: b"batch 3 source fixture\n",
            BATCH_03_FILES[1]: b"batch 3 normalized JSON fixture\n",
            BATCH_03_FILES[2]: b"batch 3 report fixture\n",
        }
        for name, payload in contents.items():
            (self.licensed_dir / name).write_bytes(payload)

        result = self.run_backup(0)

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(self.backup_root.glob("avtorinok-*/"))
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("format_version=4\n", manifest)
        self.assertIn(
            "includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json,drom-batch-03-10-makes.csv,drom-batch-03-10-makes.json,drom-batch-03-10-makes-report.json\n",
            manifest,
        )
        self.assertIn("licensed_data_classification=proprietary-permissioned\n", manifest)
        expected_names = {
            "database.dump",
            "private-media.tar.gz",
            "catalog.json",
            "catalog-coverage.json",
            *BATCH_01_FILES,
            *BATCH_02_FILES,
            *BATCH_03_FILES,
            "manifest.txt",
        }
        checksum_lines = (backup_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual({line.split(maxsplit=1)[1].strip() for line in checksum_lines}, expected_names)
        for name, payload in contents.items():
            self.assertEqual((backup_dir / name).read_bytes(), payload)
            expected_digest, _ = next(line.split(maxsplit=1) for line in checksum_lines if line.endswith(name))
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_digest)
            self.assertEqual((backup_dir / name).stat().st_mode & 0o777, 0o600)
        self.assertIn("licensed_drom_batch_03_source_bytes=23\n", manifest)
        self.assertIn("licensed_drom_batch_03_data_bytes=32\n", manifest)
        self.assertIn("licensed_drom_batch_03_report_bytes=23\n", manifest)

    def test_partial_batch_three_set_fails_before_compose(self):
        for name in BATCH_02_FILES + BATCH_03_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        (self.licensed_dir / BATCH_03_FILES[-1]).unlink()

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Batch 3 permissioned Drom artifacts must be a complete", result.stderr)
        self.assertFalse(self.log_path.exists())
        self.assertFalse(self.backup_root.exists())

    def test_batch_three_requires_complete_batch_two_set(self):
        for name in BATCH_03_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Batch 3 permissioned Drom artifacts require a complete batch 2 set", result.stderr)
        self.assertFalse(self.log_path.exists())
        self.assertFalse(self.backup_root.exists())

    def test_batches_four_through_nine_use_version_five_and_are_checksummed(self):
        contents = {
            name: f"licensed fixture: {name}\n".encode()
            for name in BATCH_02_FILES + BATCH_03_FILES + BATCH_04_09_FILES
        }
        for name, payload in contents.items():
            (self.licensed_dir / name).write_bytes(payload)

        result = self.run_backup(0)

        self.assertEqual(result.returncode, 0, result.stderr)
        backup_dir = next(self.backup_root.glob("avtorinok-*/"))
        manifest = (backup_dir / "manifest.txt").read_text(encoding="utf-8")
        self.assertIn("format_version=5\n", manifest)
        self.assertIn(
            "includes=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json,drom-batch-03-10-makes.csv,drom-batch-03-10-makes.json,drom-batch-03-10-makes-report.json," + ",".join(BATCH_04_09_FILES) + "\n",
            manifest,
        )
        self.assertIn("licensed_drom_batch_09_source_bytes=", manifest)
        self.assertIn("licensed_drom_batch_09_data_bytes=", manifest)
        self.assertIn("licensed_drom_batch_09_report_bytes=", manifest)
        expected_names = {
            "database.dump",
            "private-media.tar.gz",
            "catalog.json",
            "catalog-coverage.json",
            *BATCH_01_FILES,
            *BATCH_02_FILES,
            *BATCH_03_FILES,
            *BATCH_04_09_FILES,
            "manifest.txt",
        }
        checksum_lines = (backup_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual({line.split(maxsplit=1)[1].strip() for line in checksum_lines}, expected_names)
        for name, payload in contents.items():
            self.assertEqual((backup_dir / name).read_bytes(), payload)
            expected_digest, _ = next(line.split(maxsplit=1) for line in checksum_lines if line.endswith(name))
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_digest)
            self.assertEqual((backup_dir / name).stat().st_mode & 0o777, 0o600)

    def test_batches_four_through_nine_must_be_complete_before_compose(self):
        for name in BATCH_02_FILES + BATCH_03_FILES + BATCH_04_09_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        (self.licensed_dir / "drom-batch-07-10-makes-report.json").unlink()

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Batch 7 permissioned Drom artifacts must be a complete", result.stderr)
        self.assertFalse(self.log_path.exists())
        self.assertFalse(self.backup_root.exists())

    def test_version_five_licensed_bytes_are_included_in_free_space_estimate(self):
        for name in BATCH_02_FILES + BATCH_03_FILES + BATCH_04_09_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        (self.licensed_dir / "drom-batch-09-10-makes.json").write_bytes(b"x" * 2_000_000)
        df = self.bin_dir / "df"
        df.write_text(
            "#!/bin/sh\n"
            "printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\n"
            "printf 'fixture 2048 1024 1000 50%% /\\n'\n",
            encoding="utf-8",
        )
        df.chmod(0o755)

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Insufficient free space", result.stderr)
        self.assertTrue(self.log_path.exists())
        self.assertEqual(list(self.backup_root.iterdir()), [])

    def test_batch_three_bytes_are_included_in_free_space_estimate(self):
        for name in BATCH_02_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        for name in BATCH_03_FILES:
            (self.licensed_dir / name).write_text("fixture\n", encoding="utf-8")
        (self.licensed_dir / BATCH_03_FILES[1]).write_bytes(b"x" * 2_000_000)
        df = self.bin_dir / "df"
        df.write_text(
            "#!/bin/sh\n"
            "printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\n"
            "printf 'fixture 2048 1024 1000 50%% /\\n'\n",
            encoding="utf-8",
        )
        df.chmod(0o755)

        result = self.run_backup(0)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Insufficient free space", result.stderr)
        self.assertTrue(self.log_path.exists())
        self.assertEqual(list(self.backup_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
