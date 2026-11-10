"""Build release images for audit-20261111-r1 and preflight them without starting services.

Run as: ssh fortebit-prod python3 - < 20-build-server.py

Builds avtorinok-api:<TAG> and avtorinok-web:<TAG> from the prepared release
directory, then runs throw-away `compose run --rm --no-deps` containers of the
new api image to validate settings and read the Alembic head. Running
containers, the database schema and the active symlink are not changed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TAG = "audit-20261111-r1"
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
ACTIVE = Path("/home/suite/apps/avtorinok")
API_IMAGE = f"avtorinok-api:{TAG}"
WEB_IMAGE = f"avtorinok-web:{TAG}"
GIB = 1024**3
MIN_FREE_BYTES = 6 * GIB
BUILD_TIMEOUT = 3600
PREFLIGHT_TIMEOUT = 300

# Executed inside a throw-away container of the new api image. It prints only
# a marker, the exception class and pydantic field names, never values.
CONFIG_PREFLIGHT = """
import json, sys
try:
    from pydantic import ValidationError
    from app.config import get_settings
    get_settings()
except ValidationError as exc:
    fields = sorted({".".join(str(p) for p in err.get("loc", ())) for err in exc.errors()})
    print("config-fail " + json.dumps({"error": type(exc).__name__, "fields": fields}))
    sys.exit(3)
except Exception as exc:
    print("config-fail " + json.dumps({"error": type(exc).__name__}))
    sys.exit(3)
print("config-ok")
"""


class Abort(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Abort(message)


def log(message):
    print(f"[build] {message}", file=sys.stderr, flush=True)


_REDACTIONS = (
    (re.compile(r"://[^/\s:@]+:[^@\s]+@"), "://***:***@"),
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|KEY|DSN)[A-Z0-9_]*)\s*[=:]\s*\S+"
        ),
        r"\1=***",
    ),
)


def redact(text):
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def tail(text, lines=8):
    return redact("\n".join((text or "").splitlines()[-lines:]))


def run(cmd, *, cwd=None, timeout=900):
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def write_private(path, payload):
    if isinstance(payload, bytes):
        data = payload
    else:
        data = (
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode()
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)


def image_inspect(ref):
    result = run(["docker", "image", "inspect", ref])
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def parse_revisions(output):
    revisions = []
    for line in output.splitlines():
        match = re.match(r"^(\S+)(?: \((?:effective )?head\))?\s*$", line.strip())
        if match:
            revisions.append(match.group(1))
    return revisions


def build(compose_command, candidate):
    build_log = BACKUP / "build.log"
    fd = os.open(build_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(f"# build started {datetime.now(timezone.utc).isoformat()}\n")
        handle.flush()
        # stdout is a file (no TTY), so BuildKit already writes plain progress.
        result = subprocess.run(
            compose_command + ["build", "api", "web"],
            cwd=candidate,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=BUILD_TIMEOUT,
            check=False,
        )
    if result.returncode != 0:
        lines = build_log.read_text(errors="replace")
        raise Abort(
            f"compose build failed (exit {result.returncode}); see {build_log}; tail:\n{tail(lines, 40)}"
        )
    return str(build_log)


def compose_run_api(compose_command, candidate, args, what):
    result = run(
        compose_command + ["run", "--rm", "--no-deps", "-T", "api"] + args,
        cwd=candidate,
        timeout=PREFLIGHT_TIMEOUT,
    )
    fd = os.open(BACKUP / "preflight.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(f"## {what} exit={result.returncode}\n{redact(result.stderr)}\n")
    return result


def preflight(compose_command, candidate, expected_revision):
    config = compose_run_api(
        compose_command,
        candidate,
        ["python", "-c", CONFIG_PREFLIGHT],
        "config preflight",
    )
    markers = [
        line.strip()
        for line in config.stdout.splitlines()
        if line.startswith("config-")
    ]
    require(
        config.returncode == 0 and markers == ["config-ok"],
        f"settings preflight failed: {markers or ['no marker (exit ' + str(config.returncode) + ')']}",
    )

    heads_result = compose_run_api(
        compose_command, candidate, ["alembic", "heads"], "alembic heads"
    )
    require(
        heads_result.returncode == 0,
        f"alembic heads failed (exit {heads_result.returncode})",
    )
    heads = parse_revisions(heads_result.stdout)
    require(len(heads) == 1, f"expected a single alembic head, got {heads}")
    head = heads[0]
    require(
        head != expected_revision,
        f"new image head {head} equals the current revision; migration missing from build",
    )

    current_result = compose_run_api(
        compose_command, candidate, ["alembic", "current"], "alembic current"
    )
    require(
        current_result.returncode == 0,
        f"alembic current failed (exit {current_result.returncode})",
    )
    current = parse_revisions(current_result.stdout)
    require(
        len(current) == 1 and current[0] in (expected_revision, head),
        f"database revision {current} is neither {expected_revision} nor the new head {head}",
    )
    return {"config": "ok", "alembic_head": head, "alembic_current": current[0]}


def main():
    prepared_path = BACKUP / "prepared.json"
    require(
        prepared_path.is_file(),
        f"{prepared_path} missing; run 10-prepare-server.py first",
    )
    require(
        not (BACKUP / "deployed.json").exists(),
        "release already deployed; refusing to rebuild its tags",
    )
    prepared = json.loads(prepared_path.read_text())
    before = json.loads((BACKUP / "before.json").read_text())
    candidate = Path(prepared["candidate"])
    require(
        ACTIVE.resolve() == Path(prepared["previous_release"]),
        "active release changed since prepare",
    )
    require(
        (candidate / ".env").is_symlink()
        and os.stat(candidate / ".env").st_mode & 0o777 == 0o600,
        "candidate .env is not the protected symlink with mode 600",
    )
    free = shutil.disk_usage(candidate).free
    require(
        free >= MIN_FREE_BYTES,
        f"only {free / GIB:.2f} GiB free; need >= 6 GiB to build",
    )
    compose_command = prepared["compose_command"]

    log("building api and web (output goes to build.log)")
    started = datetime.now(timezone.utc)
    build_log = build(compose_command, candidate)
    images = {}
    running = {
        name: before["containers"][name]["image_id"]
        for name in ("avtorinok-api-1", "avtorinok-web-1")
    }
    for ref in (API_IMAGE, WEB_IMAGE):
        image = image_inspect(ref)
        require(image is not None, f"{ref} was not produced by the build")
        require(
            image.get("Architecture") == "amd64",
            f"{ref} architecture is {image.get('Architecture')}",
        )
        require(
            image["Id"] not in running.values(),
            f"{ref} is identical to a running image; build did not change anything",
        )
        images[ref] = {"id": image["Id"], "created": image.get("Created")}

    log("preflight in throw-away api containers")
    checks = preflight(compose_command, candidate, prepared["expected_db_revision"])
    built = {
        **prepared,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_seconds": int((datetime.now(timezone.utc) - started).total_seconds()),
        "build_log": build_log,
        "new_api_image_id": images[API_IMAGE]["id"],
        "new_web_image_id": images[WEB_IMAGE]["id"],
        "images": images,
        "preflight": checks,
    }
    write_private(BACKUP / "built.json", built)
    return {
        "built": True,
        "api_image": {"ref": API_IMAGE, **images[API_IMAGE]},
        "web_image": {"ref": WEB_IMAGE, **images[WEB_IMAGE]},
        "build_seconds": built["build_seconds"],
        "preflight": checks,
        "active_release_unchanged": str(ACTIVE.resolve()),
        "disk_free_gib": round(shutil.disk_usage(candidate).free / GIB, 2),
    }


if __name__ == "__main__":
    try:
        summary = main()
    except Abort as error:
        print(
            json.dumps(
                {"built": False, "error": redact(str(error))}, ensure_ascii=False
            )
        )
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - report the class without leaking values
        print(
            json.dumps(
                {
                    "built": False,
                    "error": type(error).__name__,
                    "detail": redact(str(error))[:300],
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    print(json.dumps(summary, ensure_ascii=False))
