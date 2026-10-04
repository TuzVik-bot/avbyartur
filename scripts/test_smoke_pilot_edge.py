import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-pilot-edge.sh"


class EdgeSmokeTests(unittest.TestCase):
    def run_smoke(self, *, noindex=True, **env):
        with tempfile.TemporaryDirectory(prefix="avtorinok-edge-smoke-test-") as temp_dir:
            fake_curl = Path(temp_dir) / "curl"
            fake_curl.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import os
                import sys
                from urllib.parse import urlsplit

                args = sys.argv[1:]
                header_path = args[args.index("--dump-header") + 1]
                url = args[-1]
                path = urlsplit(url).path
                status = "401" if path in {"/api/v1/me", "/api/v1/admin/users"} else "200"
                with open(header_path, "w", encoding="utf-8") as headers:
                    headers.write(f"HTTP/1.1 {status} Test\\r\\n")
                    if os.environ.get("EDGE_SMOKE_TEST_NOINDEX") == "1":
                        headers.write("X-Robots-Tag: noindex, nofollow, noarchive\\r\\n")
                    headers.write("\\r\\n")
                sys.stdout.write(status)
            """), encoding="utf-8")
            fake_curl.chmod(0o755)
            smoke_env = {k: v for k, v in os.environ.items() if not k.startswith("SMOKE_BASIC_AUTH_")}
            smoke_env.update(env)
            smoke_env["PATH"] = f"{temp_dir}:{smoke_env.get('PATH', '')}"
            smoke_env["EDGE_SMOKE_TEST_NOINDEX"] = "1" if noindex else "0"
            return subprocess.run(
                [str(SCRIPT), "--base-url", "https://pilot.example.invalid"],
                text=True,
                capture_output=True,
                env=smoke_env,
                check=False,
            )

    def test_portal_and_category_routes_pass_without_shared_credentials(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("portal routes are available without shared credentials", result.stdout)
        self.assertIn("anonymous /agricultural-equipment HTTP 200", result.stdout)
        self.assertIn("anonymous /vin-check HTTP 200", result.stdout)
        self.assertIn("anonymous /financing HTTP 200", result.stdout)

    def test_account_apis_remain_protected_and_noindex_is_present(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("anonymous /api/v1/me HTTP 401", result.stdout)
        self.assertIn("anonymous /api/v1/admin/users HTTP 401", result.stdout)
        self.assertIn("anonymous /api/v1/me contains noindex", result.stdout)

    def test_missing_noindex_fails(self):
        result = self.run_smoke(noindex=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is missing X-Robots-Tag: noindex", result.stdout)


if __name__ == "__main__":
    unittest.main()
