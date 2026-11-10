"""Manual application rollback for audit-20261111-r1.

Run as: ssh fortebit-prod python3 - < 90-rollback-server.py

Recreates api/worker and web from the exact previous compose chains recorded
in rollback.json by the prepare step (api/worker and web use different
chains), verifies that the previous image IDs run healthy, then points
/home/suite/apps/avtorinok back to the previous release. It never downgrades
the database (migrations are additive) and never touches volumes, nginx or
systemd. Safe to re-run: compose leaves already-matching containers alone.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TAG = "audit-20261111-r1"
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
ACTIVE = Path("/home/suite/apps/avtorinok")
DB = "avtorinok-db-1"
UP_TIMEOUT = 600
HEALTH_POLL_SECONDS = 180


class Abort(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Abort(message)


def log(message):
    print(f"[rollback] {message}", file=sys.stderr, flush=True)


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


def must(cmd, what, *, cwd=None, timeout=900):
    result = run(cmd, cwd=cwd, timeout=timeout)
    require(result.returncode == 0, f"{what} failed (exit {result.returncode})")
    return result.stdout


def append_log(name, title, result):
    fd = os.open(BACKUP / name, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(
            f"## {datetime.now(timezone.utc).isoformat()} {title} exit={result.returncode}\n"
        )
        handle.write(
            redact(result.stdout or "") + "\n" + redact(result.stderr or "") + "\n"
        )


def inspect(name):
    return json.loads(
        must(
            ["docker", "inspect", "--type", "container", name], f"docker inspect {name}"
        )
    )[0]


def image_id_of(ref):
    result = run(["docker", "image", "inspect", "--format", "{{.Id}}", ref])
    return result.stdout.strip() if result.returncode == 0 else None


def write_private(path, payload):
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


def health_of(item):
    return (item["State"].get("Health") or {}).get("Status")


# ---- Same rollback logic as the automatic rollback in 30-deploy-server.py ------


def restore_image_refs(plan):
    """Make sure each previous image ref still points to the previously running image."""
    restored = []
    for name, ref in plan["image_refs"].items():
        expected = plan["expected_image_ids"][name]
        if image_id_of(ref) == expected:
            continue
        rollback_tag = next(
            (tag for tag, image in plan["rollback_tags"].items() if image == expected),
            None,
        )
        require(
            rollback_tag and image_id_of(rollback_tag) == expected,
            f"no rollback tag holds the previous image for {name}",
        )
        must(["docker", "tag", rollback_tag, ref], f"re-tag {ref}")
        restored.append(ref)
    return restored


def wait_for_previous(plan):
    deadline = time.monotonic() + HEALTH_POLL_SECONDS
    while True:
        state = {}
        for name, expected in plan["expected_image_ids"].items():
            item = inspect(name)
            state[name] = {
                "image_ok": item["Image"] == expected,
                "health": health_of(item),
            }
        if all(
            entry["image_ok"] and entry["health"] == "healthy"
            for entry in state.values()
        ):
            return True, state
        if time.monotonic() > deadline:
            return False, state
        time.sleep(5)


def switch_link(destination):
    temp = ACTIVE.with_name(f"avtorinok.{TAG}.rollback")
    require(not os.path.lexists(temp), f"{temp} already exists")
    os.symlink(str(destination), temp)
    os.replace(temp, ACTIVE)
    require(ACTIVE.resolve() == Path(destination), "symlink switch did not take effect")


def main():
    for name in ("before.json", "rollback.json"):
        require((BACKUP / name).is_file(), f"{BACKUP / name} missing")
    before = json.loads((BACKUP / "before.json").read_text())
    plan = json.loads((BACKUP / "rollback.json").read_text())
    previous = Path(plan["symlink_target"])
    require(
        previous == Path(before["previous_release"]),
        "rollback.json and before.json disagree on the previous release",
    )
    require(previous.is_dir(), f"previous release directory {previous} is missing")
    for group in plan["groups"]:
        require(
            Path(group["project_directory"]).is_dir(),
            f"missing project directory {group['project_directory']}",
        )
        for index, part in enumerate(group["command"]):
            if part == "-f":
                require(
                    Path(group["command"][index + 1]).is_file(),
                    f"missing compose file {group['command'][index + 1]}",
                )
    db_before = inspect(DB)
    already = ACTIVE.resolve() == previous and all(
        inspect(name)["Image"] == image
        for name, image in plan["expected_image_ids"].items()
    )

    log("restoring image refs and recreating previous containers")
    restored = restore_image_refs(plan)
    groups = []
    for group in plan["groups"]:
        result = run(
            group["command"], cwd=group["project_directory"], timeout=UP_TIMEOUT
        )
        append_log("rollback.log", f"manual up {' '.join(group['services'])}", result)
        groups.append({"services": group["services"], "exit": result.returncode})
        require(
            result.returncode == 0,
            f"compose up {' '.join(group['services'])} failed (exit {result.returncode}); see rollback.log",
        )
    healthy, state = wait_for_previous(plan)
    require(healthy, f"previous images are not all running healthy: {state}")
    if ACTIVE.resolve() != previous:
        switch_link(previous)
    db_after = inspect(DB)
    require(
        db_after["Id"] == db_before["Id"]
        and db_after["State"]["StartedAt"] == db_before["State"]["StartedAt"],
        "db container changed during rollback",
    )
    receipt = {
        "tag": TAG,
        "rolled_back_at_utc": datetime.now(timezone.utc).isoformat(),
        "already_rolled_back": already,
        "restored_refs": restored,
        "groups": groups,
        "state": state,
        "active_release": str(ACTIVE.resolve()),
        "database": "not downgraded",
    }
    write_private(BACKUP / "rolled-back.json", receipt)
    return {"rolled_back": True, **receipt}


if __name__ == "__main__":
    try:
        summary = main()
    except Abort as error:
        print(
            json.dumps(
                {"rolled_back": False, "error": redact(str(error))}, ensure_ascii=False
            )
        )
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - report the class without leaking values
        print(
            json.dumps(
                {
                    "rolled_back": False,
                    "error": type(error).__name__,
                    "detail": redact(str(error))[:300],
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    print(json.dumps(summary, ensure_ascii=False))
