"""Read-only post-deploy report for audit-20261111-r1.

Run as: ssh fortebit-prod python3 - < 40-post-server.py

Reports container images/health, Alembic revision, worker heartbeat age,
counts of error-level JSON log lines per event since the deploy, and free disk.
It changes nothing on the host except writing post-<timestamp>.json (mode 600)
into the release backup directory. Log bodies are never printed.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TAG = "audit-20261111-r1"
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
ACTIVE = Path("/home/suite/apps/avtorinok")
WEB, API, WORKER, DB, MAIL = (
    f"avtorinok-{name}-1" for name in ("web", "api", "worker", "db", "test-mail")
)
CONTAINERS = (WEB, API, WORKER, DB, MAIL)
GIB = 1024**3
HEARTBEAT_SQL = "SELECT coalesce(extract(epoch FROM now() - max(last_seen_at))::bigint, -1) FROM worker_heartbeats"
ERROR_LEVELS = {"error", "critical", "fatal"}


class Abort(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Abort(message)


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


def run(cmd, *, timeout=300):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def inspect(name):
    result = run(["docker", "inspect", "--type", "container", name])
    require(result.returncode == 0, f"docker inspect {name} failed")
    return json.loads(result.stdout)[0]


def write_private(path, payload):
    data = (
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode()
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def alembic_current():
    result = run(["docker", "exec", API, "alembic", "current"], timeout=120)
    if result.returncode != 0:
        return {"error": f"exit {result.returncode}"}
    lines = result.stdout.decode("utf-8", "replace").splitlines()
    return [
        line.strip()
        for line in lines
        if re.match(r"^\S+( \((?:effective )?head\))?\s*$", line.strip())
    ]


def heartbeat_age():
    script = f'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "{HEARTBEAT_SQL}"'
    result = run(["docker", "exec", DB, "sh", "-c", script], timeout=60)
    if result.returncode != 0:
        return {"error": f"psql exit {result.returncode}"}
    value = result.stdout.decode().strip()
    return (
        {"seconds": int(value)}
        if re.fullmatch(r"-?\d+", value)
        else {"error": "unexpected psql output"}
    )


def error_counts(container, since):
    result = run(["docker", "logs", "--since", since, container], timeout=300)
    require(result.returncode == 0, f"docker logs {container} failed")
    counts, other = Counter(), Counter()
    lines = 0
    for raw in (
        (result.stdout + b"\n" + result.stderr).decode("utf-8", "replace").splitlines()
    ):
        if not raw.strip():
            continue
        lines += 1
        try:
            entry = json.loads(raw)
        except ValueError:
            if "Traceback" in raw or " ERROR" in raw:
                other["non_json_error_lines"] += 1
            continue
        if (
            isinstance(entry, dict)
            and str(entry.get("level", "")).lower() in ERROR_LEVELS
        ):
            counts[str(entry.get("event", "unknown"))[:80]] += 1
    return {"lines": lines, "error_events": dict(counts.most_common(50)), **other}


def main():
    deployed_path = BACKUP / "deployed.json"
    require(deployed_path.is_file(), f"{deployed_path} missing; nothing deployed yet")
    deployed = json.loads(deployed_path.read_text())
    candidate = Path(deployed["candidate"])
    since_dt = datetime.fromisoformat(deployed["deployed_at_utc"]).astimezone(
        timezone.utc
    )
    since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    expected = {
        API: deployed["new_api_image_id"],
        WORKER: deployed["new_api_image_id"],
        WEB: deployed["new_web_image_id"],
    }

    services, problems = {}, []
    for name in CONTAINERS:
        item = inspect(name)
        health = (item["State"].get("Health") or {}).get("Status")
        services[name] = {
            "image": item["Config"]["Image"],
            "image_ok": item["Image"] == expected[name] if name in expected else None,
            "status": item["State"]["Status"],
            "health": health,
            "restarts": item.get("RestartCount"),
            "started_at": item["State"]["StartedAt"],
        }
        if health != "healthy":
            problems.append(f"{name} health {health}")
        if name in expected and item["Image"] != expected[name]:
            problems.append(f"{name} does not run the deployed image")
    env_mode = oct(os.stat(ACTIVE / ".env").st_mode & 0o777)
    if ACTIVE.resolve() != candidate:
        problems.append("active symlink does not point to the deployed release")
    if env_mode != "0o600":
        problems.append(f"active .env mode {env_mode}")
    revision = alembic_current()
    head = deployed.get("preflight", {}).get("alembic_head")
    if not (
        isinstance(revision, list)
        and len(revision) == 1
        and revision[0].split()[0] == head
    ):
        problems.append("alembic current is not the deployed head")
    heartbeat = heartbeat_age()
    if heartbeat.get("seconds", -1) < 0 or heartbeat["seconds"] >= 60:
        problems.append("worker heartbeat missing or stale")
    logs = {name: error_counts(name, since) for name in (API, WORKER)}
    report = {
        "tag": TAG,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_release": str(ACTIVE.resolve()),
        "env_mode": env_mode,
        "services": services,
        "alembic_current": revision,
        "alembic_head": head,
        "worker_heartbeat_age": heartbeat,
        "logs_since": since,
        "log_errors": logs,
        "disk_free_gib": round(shutil.disk_usage(candidate).free / GIB, 2),
        "problems": problems,
        "ok": not problems,
    }
    write_private(
        BACKUP / f"post-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
        report,
    )
    return report


if __name__ == "__main__":
    try:
        summary = main()
    except Abort as error:
        print(
            json.dumps({"ok": False, "error": redact(str(error))}, ensure_ascii=False)
        )
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - report the class without leaking values
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(error).__name__,
                    "detail": redact(str(error))[:300],
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(0 if summary["ok"] else 3)
