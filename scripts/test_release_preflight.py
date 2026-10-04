import hashlib
import io
import os
import stat
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release-preflight.sh"
REQUIRED = ("docker-compose.yml", "backend/Dockerfile", "web/Dockerfile", "scripts/backup.sh", "scripts/restore.sh", "data/catalog.json")


class ReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / "pilot-new"
        self.rollback = self.root / "pilot-old"
        self.active = self.root / "avtorinok"
        for directory in (self.release, self.rollback):
            for relative in REQUIRED:
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("services:\n" if relative == "docker-compose.yml" else "placeholder\n", encoding="utf-8")
        self.active.symlink_to(self.release, target_is_directory=True)
        self.env_file = self.release / ".env"
        self.env_file.write_text(
            "POSTGRES_PASSWORD=disposable-test-placeholder\n"
            "SESSION_SECRET=disposable-test-placeholder\n"
            "AVTORINOK_IMAGE_TAG=pilot-new\n",
            encoding="utf-8",
        )
        self.env_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def run_script(self, *args, path=None):
        return subprocess.run(
            [str(SCRIPT), *args],
            text=True,
            capture_output=True,
            env={**os.environ, **({"PATH": str(path) + os.pathsep + os.environ["PATH"]} if path else {})},
            check=False,
        )

    def write_archive(self, members, name="source.tar.gz"):
        archive_path = self.root / name
        with tarfile.open(archive_path, "w:gz") as archive:
            for member_name, content, member_type in members:
                info = tarfile.TarInfo(member_name)
                if member_type == "file":
                    payload = content.encode("utf-8")
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
                elif member_type == "directory":
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                elif member_type == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = content
                    archive.addfile(info)
                elif member_type == "hardlink":
                    info.type = tarfile.LNKTYPE
                    info.linkname = content
                    archive.addfile(info)
                else:
                    raise AssertionError(f"Unsupported test member type: {member_type}")
        return archive_path, hashlib.sha256(archive_path.read_bytes()).hexdigest()

    def write_compose_fixture(self, override_text=None):
        compose = self.release / "docker-compose.yml"
        compose.write_text(
            "services:\n"
            "  db:\n"
            "    image: postgres:17.11-alpine\n"
            "  api:\n"
            "    image: avtorinok-api:${AVTORINOK_IMAGE_TAG:-local}\n"
            "  worker:\n"
            "    image: avtorinok-api:${AVTORINOK_IMAGE_TAG:-local}\n"
            "  web:\n"
            "    image: avtorinok-web:${AVTORINOK_IMAGE_TAG:-local}\n",
            encoding="utf-8",
        )
        override = self.release / "deployment.override.yml"
        override.write_text(
            override_text
            or "services:\n"
            "  api:\n"
            "    image: avtorinok-api:${AVTORINOK_IMAGE_TAG:?Set AVTORINOK_IMAGE_TAG}\n"
            "  worker:\n"
            "    image: avtorinok-api:${AVTORINOK_IMAGE_TAG:?Set AVTORINOK_IMAGE_TAG}\n"
            "  web:\n"
            "    image: avtorinok-web:${AVTORINOK_IMAGE_TAG:?Set AVTORINOK_IMAGE_TAG}\n",
            encoding="utf-8",
        )
        return compose, override

    def test_layout_active_and_rollback_pass_without_compose(self):
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--active-link",
            str(self.active),
            "--expect-active",
            "--rollback-dir",
            str(self.rollback),
            "--env-file",
            str(self.env_file),
            "--skip-compose",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Release preflight passed", result.stdout)

    def test_missing_release_file_fails(self):
        (self.release / "scripts/restore.sh").unlink()
        result = self.run_script("--release-dir", str(self.release), "--skip-compose")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing safe required file scripts/restore.sh", result.stdout)

    def test_wrong_env_mode_and_floating_image_fail(self):
        self.env_file.chmod(0o644)
        (self.release / "docker-compose.yml").write_text("services:\n  api:\n    image: example:latest\n", encoding="utf-8")
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--env-file",
            str(self.env_file),
            "--expected-image-tag",
            "pilot-new",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode 600", result.stdout)
        self.assertIn("unsafe image reference", result.stdout)

    def test_compose_config_runs_read_only(self):
        _compose, override = self.write_compose_fixture()
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--env-file",
            str(self.env_file),
            "--override-file",
            str(override),
            "--expected-image-tag",
            "pilot-new",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("effective image tags match pilot-new", result.stdout)
        self.assertNotIn("disposable-test-placeholder", result.stdout + result.stderr)

    def test_compose_preflight_automatically_includes_default_override(self):
        _compose, override = self.write_compose_fixture()
        override.rename(self.release / "docker-compose.override.yml")
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--env-file",
            str(self.env_file),
            "--expected-image-tag",
            "pilot-new",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("effective image tags match pilot-new", result.stdout)

    def test_compose_preflight_rejects_stale_override_image(self):
        _compose, override = self.write_compose_fixture(
            "services:\n"
            "  api:\n"
            "    image: avtorinok-api:pilot-stale\n"
            "  worker:\n"
            "    image: avtorinok-api:pilot-stale\n"
            "  web:\n"
            "    image: avtorinok-web:pilot-stale\n"
        )
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--env-file",
            str(self.env_file),
            "--override-file",
            str(override),
            "--expected-image-tag",
            "pilot-new",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("effective image tags do not match", result.stdout)
        self.assertNotIn("disposable-test-placeholder", result.stdout + result.stderr)

    def test_compose_preflight_rejects_floating_or_unexpected_images(self):
        _compose, override = self.write_compose_fixture(
            "services:\n"
            "  api:\n"
            "    image: avtorinok-api:pilot-new\n"
            "  worker:\n"
            "    image: avtorinok-api:pilot-new\n"
            "  web:\n"
            "    image: avtorinok-web:latest\n"
        )
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--env-file",
            str(self.env_file),
            "--override-file",
            str(override),
            "--expected-image-tag",
            "pilot-new",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe image reference", result.stdout)

    def test_compose_preflight_requires_a_safe_expected_tag(self):
        _compose, _override = self.write_compose_fixture()
        for tag in ("local", "latest", "bad/tag", "-unsafe"):
            with self.subTest(tag=tag):
                result = self.run_script(
                    "--release-dir",
                    str(self.release),
                    "--env-file",
                    str(self.env_file),
                    "--expected-image-tag",
                    tag,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("expected image tag", result.stdout)

    def test_archive_requires_sha256_when_supplied(self):
        archive, _digest = self.write_archive([("README.md", "source", "file")])
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--source-archive",
            str(archive),
            "--skip-compose",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--source-archive requires --sha256", result.stderr)

    def test_safe_archive_accepts_source_tests_and_catalog_with_matching_sha(self):
        archive, digest = self.write_archive(
            [
                ("README.md", "release source", "file"),
                (".env.example", "safe example only", "file"),
                ("tests/test_contract.py", "source test", "file"),
                ("data/catalog.json", "{}", "file"),
                ("data/", "", "directory"),
            ]
        )
        result = self.run_script(
            "--release-dir",
            str(self.release),
            "--source-archive",
            str(archive),
            "--sha256",
            digest,
            "--skip-compose",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("source archive members are safe", result.stdout)

    def test_archive_rejects_secret_and_runtime_payload_paths_without_echoing_them(self):
        unsafe_paths = (
            ".env",
            "backend/.env.production",
            "secrets/id_ed25519",
            "private-media/photo.jpg",
            "data/licensed/source.csv",
            "backups/database.dump",
            "../../outside.txt",
            "/absolute/path.txt",
        )
        for member_name in unsafe_paths:
            with self.subTest(member_name=member_name):
                archive, digest = self.write_archive([(member_name, "placeholder", "file")])
                result = self.run_script(
                    "--release-dir",
                    str(self.release),
                    "--source-archive",
                    str(archive),
                    "--sha256",
                    digest,
                    "--skip-compose",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe or unreadable", result.stdout)
                self.assertNotIn(member_name, result.stdout + result.stderr)

    def test_archive_rejects_symlink_and_hardlink_members(self):
        for member_type in ("symlink", "hardlink"):
            with self.subTest(member_type=member_type):
                archive, digest = self.write_archive(
                    [("linked-file", "../outside", member_type)]
                )
                result = self.run_script(
                    "--release-dir",
                    str(self.release),
                    "--source-archive",
                    str(archive),
                    "--sha256",
                    digest,
                    "--skip-compose",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe or unreadable", result.stdout)

    def test_archive_rejects_duplicate_or_mismatched_hash(self):
        archive, digest = self.write_archive(
            [("README.md", "first", "file"), ("README.md", "second", "file")]
        )
        duplicate = self.run_script(
            "--release-dir",
            str(self.release),
            "--source-archive",
            str(archive),
            "--sha256",
            digest,
            "--skip-compose",
        )
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("unsafe or unreadable", duplicate.stdout)

        valid_archive, valid_digest = self.write_archive(
            [("README.md", "content", "file")]
        )
        mismatch = self.run_script(
            "--release-dir",
            str(self.release),
            "--source-archive",
            str(valid_archive),
            "--sha256",
            "0" * 64 if valid_digest != "0" * 64 else "1" * 64,
            "--skip-compose",
        )
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("SHA-256 does not match", mismatch.stdout)

    def test_archive_rejects_casefolded_duplicate_paths_and_agent_material(self):
        for members in (
            [("README.md", "first", "file"), ("readme.md", "second", "file")],
            [(".superpowers/plan.md", "local notes", "file")],
        ):
            with self.subTest(members=members):
                archive, digest = self.write_archive(members)
                result = self.run_script(
                    "--release-dir",
                    str(self.release),
                    "--source-archive",
                    str(archive),
                    "--sha256",
                    digest,
                    "--skip-compose",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe or unreadable", result.stdout)


if __name__ == "__main__":
    unittest.main()
