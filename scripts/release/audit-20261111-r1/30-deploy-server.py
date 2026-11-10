"""Deploy release audit-20261111-r1: migrate, recreate api/worker/web, verify, switch symlink.

Run as: ssh fortebit-prod python3 - < 30-deploy-server.py

Any failure from `compose up` onward triggers an automatic application
rollback to the exact previous compose chains recorded by the prepare step
(api/worker and web have different chains). The database is never downgraded
(migrations are additive) and volumes are never touched.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

# ---- Gate the lead fills after reviewing env-diff.json from the prepare step ----
TAG = "audit-20261111-r1"
APPROVED_ENV_DIFF_SHA256 = "346fdfc54911b592dfbbf9eca05cf5c4d97d7e35472c016f04f9688eeb4e0917"

BACKUP = Path("/home/suite/backups/avtorinok") / TAG
ACTIVE = Path("/home/suite/apps/avtorinok")
NGINX = "http://127.0.0.1"
PUBLIC_HOST = "xn--80aeylebmo7f.xn--90ais"
HOME_TITLE = "Автомобили Беларуси"
REGISTER_ENTRY_TEXT = "Создать аккаунт"
UNKNOWN_LISTING_ID = "00000000-0000-0000-0000-000000000000"
WEB, API, WORKER, DB, MAIL = (
    f"avtorinok-{name}-1" for name in ("web", "api", "worker", "db", "test-mail")
)
CONTAINERS = (WEB, API, WORKER, DB, MAIL)
WAIT_TIMEOUT = "180"
UP_TIMEOUT = 600
MIGRATION_TIMEOUT = 1800
RETRY_DELAY_SECONDS = 15
HEALTH_POLL_SECONDS = 180
READY_PROBE = (
    "import urllib.request; "
    "print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).read().decode())"
)


class Abort(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Abort(message)


def log(message):
    print(f"[deploy] {message}", file=sys.stderr, flush=True)


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


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = build_opener(ProxyHandler({}), _NoRedirect)


def nginx_get(path, timeout=20):
    """GET through the local nginx vhost; returns (status, lower-cased headers, text)."""
    request = Request(
        NGINX + path,
        headers={"Host": PUBLIC_HOST, "User-Agent": "avtorinok-release-check"},
    )
    try:
        response = _OPENER.open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        headers = {}
        for key, value in response.headers.items():
            key = key.lower()
            headers[key] = f"{headers[key]}, {value}" if key in headers else value
        return (
            response.status if hasattr(response, "status") else response.code,
            headers,
            response.read().decode("utf-8", "replace"),
        )


def parse_revisions(output):
    revisions = []
    for line in output.splitlines():
        match = re.match(r"^(\S+)(?: \((?:effective )?head\))?\s*$", line.strip())
        if match:
            revisions.append(match.group(1))
    return revisions


def health_of(item):
    return (item["State"].get("Health") or {}).get("Status")


# ---- Rollback (same logic as 90-rollback-server.py) ---------------------------


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


def run_rollback(plan):
    detail = {"restored_refs": [], "groups": []}
    try:
        detail["restored_refs"] = restore_image_refs(plan)
        for group in plan["groups"]:
            result = run(
                group["command"], cwd=group["project_directory"], timeout=UP_TIMEOUT
            )
            append_log("rollback.log", f"up {' '.join(group['services'])}", result)
            detail["groups"].append(
                {"services": group["services"], "exit": result.returncode}
            )
        ok, state = wait_for_previous(plan)
        detail["state"] = state
        return ok and all(group["exit"] == 0 for group in detail["groups"]), detail
    except Exception as error:  # noqa: BLE001 - rollback must report, not crash
        detail["error"] = f"{type(error).__name__}: {redact(str(error))[:200]}"
        return False, detail


# ---- Verification checks -------------------------------------------------------


def check_containers_healthy(ctx):
    state = {}
    for name in CONTAINERS:
        item = inspect(name)
        state[name] = health_of(item)
        require(
            item["State"]["Status"] == "running" and state[name] == "healthy",
            f"{name} is {item['State']['Status']}/{state[name]}",
        )
    return state


def check_db_unchanged(ctx):
    item = inspect(DB)
    require(item["Id"] == ctx["before"]["db"]["id"], "db container was recreated")
    require(
        item["State"]["StartedAt"] == ctx["before"]["db"]["started_at"],
        "db container was restarted",
    )
    return {"id": item["Id"][:12]}


def check_images_built(ctx):
    expected = {
        API: ctx["built"]["new_api_image_id"],
        WORKER: ctx["built"]["new_api_image_id"],
        WEB: ctx["built"]["new_web_image_id"],
    }
    for name, image in expected.items():
        require(inspect(name)["Image"] == image, f"{name} does not run the built image")
    return {name: image[:19] for name, image in expected.items()}


def check_home(ctx):
    status, headers, body = nginx_get("/")
    require(status == 200, f"home returned {status}")
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
    title = unescape(match.group(1)).strip() if match else ""
    require(HOME_TITLE in title, "home title does not contain the expected site name")
    require("AURUM" not in body, "home page contains AURUM")
    require(
        "noindex" not in headers.get("x-robots-tag", "").lower(),
        "home has X-Robots-Tag noindex",
    )
    return {"title": title}


def check_csp(ctx):
    _, headers, _ = nginx_get("/")
    require(
        "frame-ancestors" in headers.get("content-security-policy", ""),
        "Content-Security-Policy with frame-ancestors missing on /",
    )
    return {"csp": True}


def check_capabilities(ctx):
    status, _, body = nginx_get("/api/v1/auth/capabilities")
    require(status == 200, f"capabilities returned {status}")
    current = json.loads(body)
    previous = ctx["before"]["capabilities"]
    differing = sorted(
        k for k in set(current) | set(previous) if current.get(k) != previous.get(k)
    )
    require(not differing, f"capabilities changed: {differing}")
    return {"keys": len(current)}


def check_listings(ctx):
    status, _, body = nginx_get("/api/v1/listings?page=1")
    require(status == 200, f"listings returned {status}")
    data = json.loads(body)
    require(
        isinstance(data, dict) and isinstance(data.get("items"), list),
        "listings JSON has no items list",
    )
    return {"items": len(data["items"])}


def check_catalog_makes(ctx):
    status, headers, body = nginx_get("/api/v1/catalog/makes")
    require(status == 200, f"catalog makes returned {status}")
    require(
        "max-age" in headers.get("cache-control", ""),
        "catalog makes has no Cache-Control max-age",
    )
    require(
        isinstance(json.loads(body).get("items"), list),
        "catalog makes JSON has no items list",
    )
    return {"cache_control": headers.get("cache-control")}


def check_api_ready(ctx):
    result = run(["docker", "exec", API, "python", "-c", READY_PROBE], timeout=60)
    require(
        result.returncode == 0, f"readiness probe failed (exit {result.returncode})"
    )
    data = json.loads(result.stdout)
    require(data.get("status") == "ok", f"readiness status is {data.get('status')!r}")
    require(isinstance(data.get("worker"), dict), "readiness has no worker object")
    return {"worker": data["worker"]}


def check_dealers(ctx):
    status, _, body = nginx_get("/api/v1/dealers?page=1")
    require(status == 200, f"dealers returned {status}")
    require(
        isinstance(json.loads(body).get("items"), list),
        "dealers JSON has no items list",
    )
    return {"status": status}


def check_missing_listings(ctx):
    result = {"unknown": nginx_get(f"/api/v1/listings/{UNKNOWN_LISTING_ID}")[0]}
    require(
        result["unknown"] in (404, 410), f"unknown listing returned {result['unknown']}"
    )
    archived_id = ctx["before"].get("archived_listing_id")
    if archived_id:
        result["archived"] = nginx_get(f"/api/v1/listings/{archived_id}")[0]
        expected = ctx["before"]["listing_probe_status"].get("archived")
        require(
            result["archived"] < 500, f"archived listing returned {result['archived']}"
        )
        require(
            result["archived"] == expected,
            f"archived listing status {result['archived']} != before {expected}",
        )
    return result


def check_login(ctx):
    status, _, body = nginx_get("/login?next=%2Fsell")
    require(status == 200, f"/login returned {status}")
    has_entry = REGISTER_ENTRY_TEXT in body
    if ctx["before"].get("login_has_register_entry"):
        require(has_entry, "registration entry disappeared from /login")
    return {"register_entry": has_entry}


CHECKS = (
    ("containers_healthy", check_containers_healthy),
    ("db_unchanged", check_db_unchanged),
    ("images_match_built", check_images_built),
    ("home_via_nginx", check_home),
    ("csp_frame_ancestors", check_csp),
    ("capabilities_unchanged", check_capabilities),
    ("listings_page", check_listings),
    ("catalog_makes_cache", check_catalog_makes),
    ("api_health_ready", check_api_ready),
    ("dealers_page", check_dealers),
    ("missing_listing_not_5xx", check_missing_listings),
    ("login_register_entry", check_login),
)


def run_checks(ctx, names=None):
    results = {}
    for name, fn in CHECKS:
        if names is not None and name not in names:
            continue
        try:
            results[name] = {"ok": True, "detail": fn(ctx)}
        except Exception as error:  # noqa: BLE001 - every check is reported by name
            results[name] = {
                "ok": False,
                "error": f"{type(error).__name__}: {redact(str(error))[:200]}",
            }
    return results


# ---- Steps ---------------------------------------------------------------------


def load_receipts():
    for name in (
        "before.json",
        "prepared.json",
        "built.json",
        "rollback.json",
        "env-diff.json",
    ):
        require(
            (BACKUP / name).is_file(),
            f"{BACKUP / name} missing; run the previous steps first",
        )
    require(
        not (BACKUP / "deployed.json").exists(),
        "deployed.json exists: this release was already deployed",
    )
    load = lambda name: json.loads((BACKUP / name).read_text())  # noqa: E731
    return {
        "before": load("before.json"),
        "prepared": load("prepared.json"),
        "built": load("built.json"),
        "plan": load("rollback.json"),
    }


def assert_unchanged(ctx):
    diff_sha = sha256_file(BACKUP / "env-diff.json")
    require(
        re.fullmatch(r"[0-9a-f]{64}", APPROVED_ENV_DIFF_SHA256),
        "APPROVED_ENV_DIFF_SHA256 is not filled in",
    )
    require(
        diff_sha == APPROVED_ENV_DIFF_SHA256 == ctx["prepared"]["env_diff_sha256"],
        "env-diff.json is not the reviewed version",
    )
    previous = Path(ctx["prepared"]["previous_release"])
    candidate = Path(ctx["prepared"]["candidate"])
    require(
        ACTIVE.is_symlink() and ACTIVE.resolve() == previous,
        "active release changed since prepare",
    )
    for name in CONTAINERS:
        item = inspect(name)
        recorded = ctx["before"]["containers"][name]
        require(
            item["Id"] == recorded["id"] and item["Image"] == recorded["image_id"],
            f"{name} changed since prepare",
        )
        require(health_of(item) == "healthy", f"{name} is not healthy before deploy")
    require(
        inspect(DB)["State"]["StartedAt"] == ctx["before"]["db"]["started_at"],
        "db restarted since prepare",
    )
    require(
        image_id_of(f"avtorinok-api:{TAG}") == ctx["built"]["new_api_image_id"],
        "api release tag moved since build",
    )
    require(
        image_id_of(f"avtorinok-web:{TAG}") == ctx["built"]["new_web_image_id"],
        "web release tag moved since build",
    )
    require(
        (candidate / ".env").is_symlink()
        and os.stat(candidate / ".env").st_mode & 0o777 == 0o600,
        "candidate .env is not protected",
    )
    return previous, candidate


def migrate(ctx, candidate):
    command = ctx["prepared"]["compose_command"] + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "api",
    ]
    head = ctx["built"]["preflight"]["alembic_head"]
    expected = ctx["prepared"]["expected_db_revision"]
    current = run(command + ["alembic", "current"], cwd=candidate, timeout=300)
    append_log("migrate.log", "alembic current (before)", current)
    revisions = parse_revisions(current.stdout)
    require(
        current.returncode == 0
        and len(revisions) == 1
        and revisions[0] in (expected, head),
        f"database revision {revisions} is neither {expected} nor {head}",
    )
    if revisions[0] != head:
        upgrade = run(
            command + ["alembic", "upgrade", "head"],
            cwd=candidate,
            timeout=MIGRATION_TIMEOUT,
        )
        append_log("migrate.log", "alembic upgrade head", upgrade)
        require(
            upgrade.returncode == 0,
            f"alembic upgrade failed (exit {upgrade.returncode}); see migrate.log",
        )
    after = run(command + ["alembic", "current"], cwd=candidate, timeout=300)
    append_log("migrate.log", "alembic current (after)", after)
    require(
        after.returncode == 0 and parse_revisions(after.stdout) == [head],
        "database is not at the new head after upgrade",
    )
    return {"from": revisions[0], "to": head}


def compose_up(ctx, candidate, services):
    command = (
        ctx["prepared"]["compose_command"]
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--wait",
            "--wait-timeout",
            WAIT_TIMEOUT,
        ]
        + services
    )
    result = run(command, cwd=candidate, timeout=UP_TIMEOUT)
    append_log("deploy.log", f"up {' '.join(services)}", result)
    require(
        result.returncode == 0,
        f"compose up {' '.join(services)} failed (exit {result.returncode}); see deploy.log",
    )


def switch_link(destination):
    temp = ACTIVE.with_name(f"avtorinok.{TAG}.next")
    require(not os.path.lexists(temp), f"{temp} already exists")
    os.symlink(str(destination), temp)
    os.replace(temp, ACTIVE)
    require(ACTIVE.resolve() == Path(destination), "symlink switch did not take effect")


def fail(payload, code):
    write_private(BACKUP / "deploy-failed.json", payload)
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(code)


def main():
    ctx = load_receipts()
    previous, candidate = assert_unchanged(ctx)
    log("migrating database")
    try:
        migration = migrate(ctx, candidate)
    except Exception as error:  # noqa: BLE001 - containers untouched at this point
        fail(
            {
                "deployed": False,
                "rolled_back": False,
                "failed_check": "migration",
                "error": f"{type(error).__name__}: {redact(str(error))[:300]}",
                "note": "containers were not touched; transactional DDL leaves the schema at the previous revision on failure",
            },
            1,
        )

    deploy_started = datetime.now(timezone.utc)
    failed_step, checks = None, {}
    try:
        log("up api worker")
        failed_step = "up_api_worker"
        compose_up(ctx, candidate, ["api", "worker"])
        log("up web")
        failed_step = "up_web"
        compose_up(ctx, candidate, ["web"])
        failed_step = None
        log("verification")
        checks = run_checks(ctx)
        failed = [name for name, result in checks.items() if not result["ok"]]
        if failed:
            time.sleep(RETRY_DELAY_SECONDS)
            checks.update(run_checks(ctx, set(failed)))
        failed = [name for name, result in checks.items() if not result["ok"]]
        if failed:
            failed_step = failed[0]
        else:
            failed_step = "symlink_switch"
            switch_link(candidate)
            failed_step = None
    except Exception as error:  # noqa: BLE001 - any failure here triggers rollback
        checks.setdefault(
            failed_step or "unexpected",
            {
                "ok": False,
                "error": f"{type(error).__name__}: {redact(str(error))[:200]}",
            },
        )
        failed_step = failed_step or "unexpected"

    if failed_step:
        log(f"FAILED at {failed_step}: rolling back application containers")
        rolled_back, detail = run_rollback(ctx["plan"])
        try:
            if ACTIVE.resolve() != previous:
                switch_link(previous)
            detail["symlink"] = str(ACTIVE.resolve())
        except Exception as error:  # noqa: BLE001 - report, the operator repoints by hand
            rolled_back = False
            detail["symlink_error"] = f"{type(error).__name__}: {redact(str(error))[:200]}"
        fail(
            {
                "deployed": False,
                "rolled_back": rolled_back,
                "failed_check": failed_step,
                "failed_checks": [name for name, r in checks.items() if not r["ok"]],
                "checks": checks,
                "rollback": detail,
                "migration": migration,
                "database": "left at the new head (additive, compatible with the previous api)",
            },
            1 if rolled_back else 2,
        )

    deployed = {
        **ctx["built"],
        "deployed_at_utc": deploy_started.isoformat(),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "migration": migration,
        "checks": checks,
        "containers_after": {
            name: {"id": inspect(name)["Id"], "image_id": inspect(name)["Image"]}
            for name in CONTAINERS
        },
    }
    write_private(BACKUP / "deployed.json", deployed)
    write_private(candidate / "deployment-receipt.json", deployed)
    plan = {
        **ctx["plan"],
        "deployed_release": str(candidate),
        "deployed_at_utc": deploy_started.isoformat(),
    }
    write_private(BACKUP / "rollback.json", plan)
    return {
        "deployed": TAG,
        "active_release": str(ACTIVE.resolve()),
        "migration": migration,
        "api_image_id": ctx["built"]["new_api_image_id"],
        "web_image_id": ctx["built"]["new_web_image_id"],
        "checks": {name: result["ok"] for name, result in checks.items()},
        "worker_heartbeat": checks["api_health_ready"]["detail"]["worker"],
        "login_has_register_entry": checks["login_register_entry"]["detail"][
            "register_entry"
        ],
        "rollback": str(BACKUP / "rollback.json"),
        "public_browser_check": "pending: /login?next=%2Fsell registration form in a real browser",
    }


if __name__ == "__main__":
    try:
        summary = main()
    except Abort as error:
        print(
            json.dumps(
                {
                    "deployed": False,
                    "rolled_back": False,
                    "failed_check": "precondition",
                    "error": redact(str(error)),
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - report the class without leaking values
        print(
            json.dumps(
                {
                    "deployed": False,
                    "rolled_back": False,
                    "failed_check": "unexpected",
                    "error": type(error).__name__,
                    "detail": redact(str(error))[:300],
                },
                ensure_ascii=False,
            )
        )
        sys.exit(2)
    print(json.dumps(summary, ensure_ascii=False))
