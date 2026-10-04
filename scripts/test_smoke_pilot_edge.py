import base64
import http.server
import os
import subprocess
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-pilot-edge.sh"


class EdgeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib handler API
        expected = "Basic " + base64.b64encode(b"pilot:secret").decode("ascii")
        authenticated = self.headers.get("Authorization") == expected
        self.send_response(200 if authenticated else 401)
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.end_headers()

    def log_message(self, *_):
        return


class EdgeSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), EdgeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def run_smoke(self, **env):
        smoke_env = {k: v for k, v in os.environ.items() if not k.startswith("SMOKE_BASIC_AUTH_")}
        smoke_env.update(env)
        return subprocess.run(
            [str(SCRIPT), "--base-url", f"http://127.0.0.1:{self.server.server_port}"],
            text=True,
            capture_output=True,
            env=smoke_env,
            check=False,
        )

    def test_anonymous_boundary_passes_without_credentials(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authenticated responses", result.stdout)

    def test_authenticated_boundary_passes(self):
        result = self.run_smoke(SMOKE_BASIC_AUTH_USER="pilot", SMOKE_BASIC_AUTH_PASSWORD="secret")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("auth / HTTP 200", result.stdout)

    def test_wrong_credentials_fail_authenticated_checks(self):
        result = self.run_smoke(SMOKE_BASIC_AUTH_USER="pilot", SMOKE_BASIC_AUTH_PASSWORD="wrong")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected HTTP 200", result.stdout)


if __name__ == "__main__":
    unittest.main()
