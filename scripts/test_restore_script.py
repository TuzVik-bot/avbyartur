import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESTORE_SCRIPT = ROOT / "scripts" / "restore.sh"
V1_BACKUP_FILES = (
    "database.dump",
    "private-media.tar.gz",
    "catalog.json",
    "catalog-coverage.json",
    "manifest.txt",
)
DROM_FILES = (
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
BATCH_01_02_FILES = DROM_FILES + BATCH_02_FILES
ALL_DROM_FILES = BATCH_01_02_FILES + BATCH_03_FILES
ALL_DROM_V5_FILES = ALL_DROM_FILES + BATCH_04_09_FILES
BACKUP_FILES = V1_BACKUP_FILES[:-1] + DROM_FILES + ("manifest.txt",)
V3_BACKUP_FILES = V1_BACKUP_FILES[:-1] + BATCH_01_02_FILES + ("manifest.txt",)
V4_BACKUP_FILES = V1_BACKUP_FILES[:-1] + ALL_DROM_FILES + ("manifest.txt",)
V5_BACKUP_FILES = V1_BACKUP_FILES[:-1] + ALL_DROM_V5_FILES + ("manifest.txt",)

DOCKER_STUB = """#!/bin/sh
set -eu
operation="$*"
working_dir=$(pwd -P)
printf 'docker %s\\n' "$operation" >> "$RESTORE_EVENT_LOG"
case "$operation" in
    *"compose ps -q --status running api"*) [ "$working_dir" = "$RESTORE_PROJECT_DIR" ] || exit 1; printf 'api-id\\n' ;;
    *"compose ps -q --status running worker"*) [ "$working_dir" = "$RESTORE_PROJECT_DIR" ] || exit 1; printf 'worker-id\\n' ;;
    *"compose ps -q --status running web"*) [ "$working_dir" = "$RESTORE_PROJECT_DIR" ] || exit 1; printf 'web-id\\n' ;;
    *"health/ready"*)
        [ "${RESTORE_HEALTH:-ready}" = ready ] || exit 1
        ;;
    *"volume create "*) ;;
    *"tar -xzf - -C /target"*) [ "${RESTORE_FAIL_MEDIA_EXTRACT:-0}" != 1 ] || exit 69 ;;
    *"pg_restore"*) [ "${RESTORE_FAIL_PG_RESTORE:-0}" != 1 ] || exit 70 ;;
    *"import-catalog"*) [ "${RESTORE_FAIL_IMPORT_CATALOG:-0}" != 1 ] || exit 72 ;;
    *"compose stop web api worker"*) ;;
    *"compose up -d db api worker web"*) [ "${RESTORE_FAIL_STARTUP:-0}" != 1 ] || exit 71 ;;
    *"compose start api"*) ;;
    *"compose start worker"*) ;;
    *"compose start web"*) ;;
    *) printf 'Unexpected docker command: %s\\n' "$operation" >&2; exit 64 ;;
esac
"""

BACKUP_STUB = """#!/bin/sh
set -eu
[ "$#" -eq 2 ] && [ "$1" = "--output-dir" ]
mkdir -p "$2"
printf 'pre-restore backup\\n' >> "$RESTORE_EVENT_LOG"
[ "${AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED:-0}" != 1 ] || printf 'pre-restore legacy license fallback\\n' >> "$RESTORE_EVENT_LOG"
printf 'protected\\n' > "$2/test-pre-restore-marker"
"""


class RestoreScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.scripts = self.project / "scripts"
        self.data = self.project / "data"
        self.bin_dir = self.root / "bin"
        self.backup = self.root / "incoming" / "avtorinok-test"
        self.backup_root = self.root / "protected-backups"
        self.events = self.root / "events.log"
        self.scripts.mkdir(parents=True)
        self.data.mkdir()
        self.bin_dir.mkdir()
        self.backup.mkdir(parents=True)

        self.restore_script = self.scripts / "restore.sh"
        shutil.copy2(RESTORE_SCRIPT, self.restore_script)
        self.write_executable(self.scripts / "backup.sh", BACKUP_STUB)
        self.write_executable(self.bin_dir / "docker", DOCKER_STUB)
        self.write_executable(self.bin_dir / "sleep", "#!/bin/sh\nexit 0\n")

        (self.project / ".env").write_text(
            "APP_ENV=test\nPRIVATE_MEDIA_VOLUME=avtorinok_private\nOTHER=value\n",
            encoding="utf-8",
        )
        (self.data / "catalog.json").write_text("old catalog\n", encoding="utf-8")
        (self.data / "catalog-coverage.json").write_text(
            "old coverage\n", encoding="utf-8"
        )
        self.licensed_data = self.data / "licensed"
        self.licensed_data.mkdir()
        (self.licensed_data / "existing-source.csv").write_text(
            "keep this unrelated licensed input\n", encoding="utf-8"
        )
        (self.licensed_data / DROM_FILES[0]).write_text(
            "pre-restore licensed source\n", encoding="utf-8"
        )
        (self.licensed_data / DROM_FILES[1]).write_text(
            "pre-restore licensed report\n", encoding="utf-8"
        )
        for name in BATCH_02_FILES + BATCH_03_FILES:
            (self.licensed_data / name).write_text(
                f"pre-restore {name}\n", encoding="utf-8"
            )
        for name in BACKUP_FILES[:-1]:
            (self.backup / name).write_text(f"fixture {name}\n", encoding="utf-8")
        self.write_snapshot(2)

    @staticmethod
    def write_executable(path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def write_checksum_manifest(self, names, digest_overrides=None):
        digest_overrides = digest_overrides or {}
        lines = []
        for name in names:
            digest = digest_overrides.get(name)
            if digest is None:
                digest = hashlib.sha256((self.backup / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
        (self.backup / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_snapshot(self, version):
        for name in ALL_DROM_V5_FILES:
            (self.backup / name).unlink(missing_ok=True)
        if version == 1:
            files = V1_BACKUP_FILES
            includes = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json"
        elif version == 2:
            for name in DROM_FILES:
                (self.backup / name).write_text(f"fixture {name}\n", encoding="utf-8")
            files = BACKUP_FILES
            includes = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json"
        elif version == 3:
            for name in BATCH_01_02_FILES:
                (self.backup / name).write_text(f"fixture {name}\n", encoding="utf-8")
            files = V3_BACKUP_FILES
            includes = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json"
        elif version == 4:
            for name in ALL_DROM_FILES:
                (self.backup / name).write_text(f"fixture {name}\n", encoding="utf-8")
            files = V4_BACKUP_FILES
            includes = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json,drom-batch-03-10-makes.csv,drom-batch-03-10-makes.json,drom-batch-03-10-makes-report.json"
        else:
            for name in ALL_DROM_V5_FILES:
                (self.backup / name).write_text(f"fixture {name}\n", encoding="utf-8")
            files = V5_BACKUP_FILES
            includes = (
                "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,"
                + ",".join(ALL_DROM_V5_FILES)
            )
        manifest = [
            f"format_version={version}",
            "created_at_utc=20260927T120000Z",
            f"includes={includes}",
        ]
        if version in (2, 3, 4, 5):
            manifest.append("licensed_data_classification=proprietary-permissioned")
        (self.backup / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="ascii")
        self.snapshot_files = files
        self.write_checksum_manifest(files)

    def run_restore(self, *args, extra_env=None):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}{os.pathsep}{env['PATH']}",
                "RESTORE_EVENT_LOG": str(self.events),
                "RESTORE_PROJECT_DIR": str(self.project.resolve()),
                "AVTORINOK_BACKUP_DIR": str(self.backup_root),
            }
        )
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.restore_script), *map(str, args)],
            cwd=extra_env.get("RESTORE_CWD", self.project) if extra_env else self.project,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def event_lines(self):
        return self.events.read_text(encoding="utf-8").splitlines()

    def test_requires_explicit_confirmation_before_any_side_effect(self):
        result = self.run_restore(self.backup)

        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: restore.sh --yes", result.stderr)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())
        self.assertEqual(
            (self.project / ".env").read_text(encoding="utf-8"),
            "APP_ENV=test\nPRIVATE_MEDIA_VOLUME=avtorinok_private\nOTHER=value\n",
        )

    def test_checksum_failure_stops_before_backup_or_docker(self):
        with (self.backup / "database.dump").open("a", encoding="utf-8") as database:
            database.write("tampered\n")

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())
        self.assertEqual(
            (self.data / "catalog.json").read_text(encoding="utf-8"), "old catalog\n"
        )

    def test_invalid_checksum_manifests_stop_before_backup_docker_or_env_changes(self):
        (self.backup / "extra.dump").write_text("unknown file\n", encoding="utf-8")
        cases = (
            ("incomplete", BACKUP_FILES[:-1], {}),
            (
                "duplicate",
                BACKUP_FILES[:-1] + ("database.dump",),
                {},
            ),
            (
                "unknown filename",
                BACKUP_FILES[:-1] + ("extra.dump",),
                {},
            ),
            (
                "short digest",
                BACKUP_FILES,
                {"database.dump": "a" * 63},
            ),
            (
                "non-hex digest",
                BACKUP_FILES,
                {"database.dump": "g" * 64},
            ),
        )

        for label, names, digest_overrides in cases:
            with self.subTest(manifest=label):
                self.write_checksum_manifest(names, digest_overrides)
                original_env = (self.project / ".env").read_text(encoding="utf-8")
                result = self.run_restore("--yes", self.backup)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid checksum manifest", result.stderr)
                self.assertFalse(self.events.exists())
                self.assertFalse(self.backup_root.exists())
                self.assertEqual(
                    (self.project / ".env").read_text(encoding="utf-8"), original_env
                )
                self.assertEqual(
                    (self.data / "catalog.json").read_text(encoding="utf-8"),
                    "old catalog\n",
                )

    def test_success_orders_protection_before_restore_and_retains_old_volume(self):
        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Restored database and media", result.stdout)
        events = self.event_lines()
        pre_backup = events.index("pre-restore backup")
        stop = events.index("docker compose stop web api worker")
        create_volume = next(
            i for i, event in enumerate(events) if event.startswith("docker volume create ")
        )
        restore_db = next(i for i, event in enumerate(events) if "pg_restore" in event)
        self.assertIn("--single-transaction", events[restore_db])
        import_catalog = next(i for i, event in enumerate(events) if "import-catalog" in event)
        start = events.index("docker compose up -d db api worker web")
        readiness = next(i for i, event in enumerate(events) if "health/ready" in event)
        self.assertLess(pre_backup, stop)
        self.assertLess(stop, create_volume)
        self.assertLess(create_volume, restore_db)
        self.assertLess(restore_db, import_catalog)
        self.assertLess(import_catalog, start)
        self.assertLess(start, readiness)
        self.assertFalse(any("volume rm" in event for event in events))

        active_volume = next(
            line.split("=", 1)[1]
            for line in (self.project / ".env").read_text(encoding="utf-8").splitlines()
            if line.startswith("PRIVATE_MEDIA_VOLUME=")
        )
        created_volume = events[create_volume].removeprefix("docker volume create ")
        self.assertEqual(active_volume, created_volume)
        self.assertTrue(active_volume.startswith("avtorinok_private_restore_"))
        self.assertEqual((self.project / ".env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.data / "catalog.json").read_text(encoding="utf-8"),
            "fixture catalog.json\n",
        )
        self.assertEqual(
            (self.data / "catalog-coverage.json").read_text(encoding="utf-8"),
            "fixture catalog-coverage.json\n",
        )
        self.assertEqual((self.data / "catalog.json").stat().st_mode & 0o777, 0o644)
        self.assertEqual(
            (self.licensed_data / DROM_FILES[0]).read_text(encoding="utf-8"),
            f"fixture {DROM_FILES[0]}\n",
        )
        self.assertEqual(
            (self.licensed_data / DROM_FILES[1]).read_text(encoding="utf-8"),
            f"fixture {DROM_FILES[1]}\n",
        )
        self.assertEqual((self.licensed_data / DROM_FILES[0]).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.licensed_data / DROM_FILES[1]).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.licensed_data / "existing-source.csv").read_text(encoding="utf-8"),
            "keep this unrelated licensed input\n",
        )
        for name in BATCH_02_FILES:
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"),
                f"pre-restore {name}\n",
            )
        self.assertEqual(self.licensed_data.stat().st_mode & 0o777, 0o755)
        self.assertTrue(
            (self.backup_root / "pre-restore" / "test-pre-restore-marker").is_file()
        )

    def test_legacy_version_one_snapshot_restores_without_changing_licensed_sources(self):
        self.write_snapshot(1)

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.licensed_data / DROM_FILES[0]).read_text(encoding="utf-8"),
            "pre-restore licensed source\n",
        )
        self.assertEqual(
            (self.licensed_data / DROM_FILES[1]).read_text(encoding="utf-8"),
            "pre-restore licensed report\n",
        )
        for name in ALL_DROM_FILES:
            expected = (
                "pre-restore licensed source\n"
                if name == DROM_FILES[0]
                else "pre-restore licensed report\n"
                if name == DROM_FILES[1]
                else f"pre-restore {name}\n"
            )
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"), expected
            )
        self.assertEqual(
            (self.licensed_data / "existing-source.csv").read_text(encoding="utf-8"),
            "keep this unrelated licensed input\n",
        )

    def test_version_two_restore_recovers_when_all_current_licensed_files_are_absent(self):
        for name in ALL_DROM_FILES:
            (self.licensed_data / name).unlink()

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pre-restore legacy license fallback", self.event_lines())
        self.assertEqual(
            (self.licensed_data / DROM_FILES[0]).read_text(encoding="utf-8"),
            f"fixture {DROM_FILES[0]}\n",
        )
        self.assertEqual(
            (self.licensed_data / DROM_FILES[1]).read_text(encoding="utf-8"),
            f"fixture {DROM_FILES[1]}\n",
        )
        self.assertEqual((self.licensed_data / DROM_FILES[0]).stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.licensed_data / DROM_FILES[1]).stat().st_mode & 0o777, 0o600)
        for name in BATCH_02_FILES:
            self.assertFalse((self.licensed_data / name).exists())

    def test_version_three_restore_recovers_all_five_licensed_artifacts(self):
        self.write_snapshot(3)

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        for name in BATCH_01_02_FILES:
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"),
                f"fixture {name}\n",
            )
            self.assertEqual((self.licensed_data / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.licensed_data / "existing-source.csv").read_text(encoding="utf-8"),
            "keep this unrelated licensed input\n",
        )

    def test_version_four_restore_recovers_all_eight_licensed_artifacts(self):
        self.write_snapshot(4)

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ALL_DROM_FILES:
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"),
                f"fixture {name}\n",
            )
            self.assertEqual((self.licensed_data / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.licensed_data / "existing-source.csv").read_text(encoding="utf-8"),
            "keep this unrelated licensed input\n",
        )

    def test_version_four_checksum_failure_precedes_restore_side_effects(self):
        self.write_snapshot(4)
        with (self.backup / BATCH_03_FILES[1]).open("a", encoding="utf-8") as source:
            source.write("tampered\n")

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())
        for name in ALL_DROM_FILES:
            self.assertTrue((self.licensed_data / name).is_file())

    def test_version_four_missing_batch_three_file_is_rejected_before_restore(self):
        self.write_snapshot(4)
        (self.backup / BATCH_03_FILES[-1]).unlink()

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing backup file", result.stderr)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())

    def test_version_five_restore_recovers_all_batches_one_through_nine(self):
        self.write_snapshot(5)

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ALL_DROM_V5_FILES:
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"),
                f"fixture {name}\n",
            )
            self.assertEqual((self.licensed_data / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.licensed_data / "existing-source.csv").read_text(encoding="utf-8"),
            "keep this unrelated licensed input\n",
        )

    def test_version_five_checksum_failure_precedes_restore_side_effects(self):
        self.write_snapshot(5)
        with (self.backup / "drom-batch-09-10-makes.json").open("a", encoding="utf-8") as source:
            source.write("tampered\n")

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())

    def test_version_five_missing_batch_file_is_rejected_before_restore(self):
        self.write_snapshot(5)
        (self.backup / "drom-batch-07-10-makes-report.json").unlink()

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing backup file", result.stderr)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())

    def test_batch_four_artifact_prevents_empty_license_pre_restore_fallback(self):
        for name in ALL_DROM_FILES:
            (self.licensed_data / name).unlink()
        batch_four_csv = BATCH_04_09_FILES[0]
        (self.licensed_data / batch_four_csv).write_text("batch four present\n", encoding="utf-8")
        self.write_snapshot(1)

        result = self.run_restore("--yes", self.backup)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pre-restore legacy license fallback", self.event_lines())
        self.assertEqual(
            (self.licensed_data / batch_four_csv).read_text(encoding="utf-8"),
            "batch four present\n",
        )

    def test_version_three_staging_failure_leaves_current_licensed_set_unchanged(self):
        self.write_snapshot(3)
        cp_wrapper = self.bin_dir / "cp"
        cp_wrapper.write_text(
            "#!/bin/sh\n"
            'case "$*" in *drom-batch-02-10-makes.json*) exit 75 ;; esac\n'
            'exec "$RESTORE_REAL_CP" "$@"\n',
            encoding="utf-8",
        )
        cp_wrapper.chmod(0o755)

        result = self.run_restore(
            "--yes",
            self.backup,
            extra_env={"RESTORE_REAL_CP": shutil.which("cp")},
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app services were stopped", result.stderr)
        for name in ALL_DROM_FILES:
            expected = (
                "pre-restore licensed source\n"
                if name == DROM_FILES[0]
                else "pre-restore licensed report\n"
                if name == DROM_FILES[1]
                else f"pre-restore {name}\n"
            )
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"), expected
            )
        self.assertEqual(list(self.data.glob(".licensed.restore.*")), [])

    def test_version_three_checksum_failure_precedes_restore_side_effects(self):
        self.write_snapshot(3)
        with (self.backup / BATCH_02_FILES[1]).open("a", encoding="utf-8") as source:
            source.write("tampered\n")

        result = self.run_restore("--yes", self.backup)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse(self.events.exists())
        self.assertFalse(self.backup_root.exists())
        for name in ALL_DROM_FILES:
            expected = (
                "pre-restore licensed source\n"
                if name == DROM_FILES[0]
                else "pre-restore licensed report\n"
                if name == DROM_FILES[1]
                else f"pre-restore {name}\n"
            )
            self.assertEqual(
                (self.licensed_data / name).read_text(encoding="utf-8"), expected
            )

    def test_invocation_outside_project_still_restarts_services_after_media_restore_failure(self):
        result = self.run_restore(
            "--yes",
            self.backup,
            extra_env={
                "RESTORE_CWD": str(self.root),
                "RESTORE_FAIL_MEDIA_EXTRACT": "1",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        events = self.event_lines()
        self.assertTrue(any("docker compose start api" == event for event in events))
        self.assertTrue(any("docker compose start worker" == event for event in events))
        self.assertTrue(any("docker compose start web" == event for event in events))

    def test_readiness_failure_reports_incomplete_restore_and_keeps_pre_restore_backup(self):
        result = self.run_restore(
            "--yes", self.backup, extra_env={"RESTORE_HEALTH": "fail"}
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("API readiness did not pass", result.stderr)
        self.assertTrue(
            (self.backup_root / "pre-restore" / "test-pre-restore-marker").is_file()
        )
        self.assertEqual(sum("health/ready" in event for event in self.event_lines()), 30)
        events = self.event_lines()
        self.assertFalse(any("docker compose start " in event for event in events))
        self.assertGreater(
            max(i for i, event in enumerate(events) if event == "docker compose stop web api worker"),
            max(i for i, event in enumerate(events) if "health/ready" in event),
        )
        self.assertTrue(
            any(
                line.startswith("PRIVATE_MEDIA_VOLUME=avtorinok_private_restore_")
                for line in (self.project / ".env").read_text(encoding="utf-8").splitlines()
            )
        )

    def test_pg_restore_failure_keeps_services_stopped_and_retains_backups_and_volumes(self):
        result = self.run_restore(
            "--yes", self.backup, extra_env={"RESTORE_FAIL_PG_RESTORE": "1"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app services were stopped", result.stderr)
        events = self.event_lines()
        restore_db = next(i for i, event in enumerate(events) if "pg_restore" in event)
        stop_indices = [
            i for i, event in enumerate(events) if event == "docker compose stop web api worker"
        ]
        self.assertEqual(len(stop_indices), 2)
        self.assertGreater(stop_indices[-1], restore_db)
        self.assertFalse(any("docker compose start " in event for event in events))
        self.assertTrue(any(event.startswith("docker volume create ") for event in events))
        self.assertFalse(any("volume rm" in event for event in events))
        self.assertTrue(
            (self.backup_root / "pre-restore" / "test-pre-restore-marker").is_file()
        )
        self.assertEqual(
            (self.project / ".env").read_text(encoding="utf-8"),
            "APP_ENV=test\nPRIVATE_MEDIA_VOLUME=avtorinok_private\nOTHER=value\n",
        )

    def test_catalog_import_failure_after_database_restore_keeps_services_stopped(self):
        result = self.run_restore(
            "--yes", self.backup, extra_env={"RESTORE_FAIL_IMPORT_CATALOG": "1"}
        )

        self.assertNotEqual(result.returncode, 0)
        events = self.event_lines()
        restore_db = next(i for i, event in enumerate(events) if "pg_restore" in event)
        import_catalog = next(i for i, event in enumerate(events) if "import-catalog" in event)
        self.assertLess(restore_db, import_catalog)
        self.assertFalse(any("docker compose start " in event for event in events))
        stop_indices = [
            i for i, event in enumerate(events) if event == "docker compose stop web api worker"
        ]
        self.assertEqual(len(stop_indices), 2)
        self.assertGreater(stop_indices[-1], import_catalog)
        self.assertIn("app services were stopped", result.stderr)
        self.assertEqual(
            (self.project / ".env").read_text(encoding="utf-8"),
            "APP_ENV=test\nPRIVATE_MEDIA_VOLUME=avtorinok_private\nOTHER=value\n",
        )
        self.assertTrue(
            (self.backup_root / "pre-restore" / "test-pre-restore-marker").is_file()
        )

    def test_startup_failure_keeps_services_stopped_and_retains_new_volume(self):
        result = self.run_restore(
            "--yes", self.backup, extra_env={"RESTORE_FAIL_STARTUP": "1"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app services were stopped", result.stderr)
        events = self.event_lines()
        startup = events.index("docker compose up -d db api worker web")
        stop_indices = [
            i for i, event in enumerate(events) if event == "docker compose stop web api worker"
        ]
        self.assertEqual(len(stop_indices), 2)
        self.assertGreater(stop_indices[-1], startup)
        self.assertFalse(any("docker compose start " in event for event in events))
        created_volume = next(
            event.removeprefix("docker volume create ")
            for event in events
            if event.startswith("docker volume create ")
        )
        active_volume = next(
            line.split("=", 1)[1]
            for line in (self.project / ".env").read_text(encoding="utf-8").splitlines()
            if line.startswith("PRIVATE_MEDIA_VOLUME=")
        )
        self.assertEqual(active_volume, created_volume)
        self.assertFalse(any("volume rm" in event for event in events))
        self.assertTrue(
            (self.backup_root / "pre-restore" / "test-pre-restore-marker").is_file()
        )


if __name__ == "__main__":
    unittest.main()
