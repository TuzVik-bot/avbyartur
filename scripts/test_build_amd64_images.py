import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-amd64-images.sh"


class BuildAmd64ImagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "docker.log"
        self.write_command(
            "df",
            "#!/bin/sh\nprintf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/test 1 1 20000000 1%% /tmp\\n'\n",
        )
        self.write_command(
            "docker",
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
            "case \"$*\" in\n"
            "  *'--format {{.Os}}/{{.Architecture}}'*) printf 'linux/amd64\\n' ;;\n"
            "  *'--format {{.Size}}'*) printf '1234\\n' ;;\n"
            "  'run --rm --read-only --platform linux/amd64 --entrypoint sh '*) printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n/dev/test 1 1 20000000 1%% /\\n' ;;\n"
            "esac\n",
        )

    def write_command(self, name, content):
        path = self.bin / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def run_script(self, **extra_env):
        env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "DOCKER_LOG": str(self.log),
            "AVTORINOK_IMAGE_TAG": "pilot-2026.10",
        }
        env.update(extra_env)
        return subprocess.run([str(SCRIPT)], cwd=ROOT, text=True, capture_output=True, env=env, check=False)

    def test_api_and_web_image_builds_receive_derived_release_id(self):
        result = self.run_script(AVTORINOK_IMAGE_TAG="pilot-2026.10")
        self.assertEqual(result.returncode, 0, result.stderr)
        build_commands = self.log.read_text(encoding="utf-8").splitlines()
        api_build = next(command for command in build_commands if "-f backend/Dockerfile" in command)
        web_build = next(command for command in build_commands if "-f web/Dockerfile" in command)
        self.assertIn("--build-arg RELEASE_ID=pilot-2026.10", api_build)
        self.assertIn("--build-arg NEXT_PUBLIC_RELEASE_ID=pilot-2026.10", web_build)

    def test_explicit_release_id_is_validated_and_forwarded(self):
        result = self.run_script(NEXT_PUBLIC_RELEASE_ID="custom.release+1")
        self.assertEqual(result.returncode, 0, result.stderr)
        build_commands = self.log.read_text(encoding="utf-8").splitlines()
        api_build = next(command for command in build_commands if "-f backend/Dockerfile" in command)
        web_build = next(command for command in build_commands if "-f web/Dockerfile" in command)
        self.assertIn("--build-arg RELEASE_ID=custom.release+1", api_build)
        self.assertIn("--build-arg NEXT_PUBLIC_RELEASE_ID=custom.release+1", web_build)

    def test_long_tag_derives_a_valid_release_id(self):
        tag = "pilot-" + "x" * 110
        result = self.run_script(AVTORINOK_IMAGE_TAG=tag)
        self.assertEqual(result.returncode, 0, result.stderr)
        build_commands = self.log.read_text(encoding="utf-8").splitlines()
        api_build = next(command for command in build_commands if "-f backend/Dockerfile" in command)
        web_build = next(command for command in build_commands if "-f web/Dockerfile" in command)
        api_value = re.search(r"--build-arg RELEASE_ID=([^ ]+)", api_build).group(1)
        web_value = re.search(r"--build-arg NEXT_PUBLIC_RELEASE_ID=([^ ]+)", web_build).group(1)
        self.assertEqual(api_value, web_value)
        value = api_value
        self.assertRegex(value, r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")

    def test_invalid_or_overlong_explicit_release_id_fails_before_docker(self):
        for release_id in ("https://private.invalid", "x" * 65, "_invalid"):
            with self.subTest(release_id=release_id):
                self.log.unlink(missing_ok=True)
                result = self.run_script(NEXT_PUBLIC_RELEASE_ID=release_id)
                self.assertEqual(result.returncode, 2)
                self.assertIn("NEXT_PUBLIC_RELEASE_ID", result.stderr)
                self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
