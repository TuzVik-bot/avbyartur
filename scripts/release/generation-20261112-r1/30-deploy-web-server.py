"""Web-only deploy generation-20261112-r1: recreate web, verify, switch symlink; auto-rollback web.

Runs on the VPS via `ssh ... python3 - < 30-deploy-web-server.py`. Only the web container
is recreated (`--no-deps`); api, worker, db, test-mail must keep their container ids.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

TAG = "generation-20261112-r1"
PREV_TAG = "audit-20261111-r1"
RELEASES = Path("/home/suite/apps/releases")
ACTIVE = Path("/home/suite/apps/avtorinok")
PREV_DIR = RELEASES / PREV_TAG
CANDIDATE = RELEASES / TAG
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
PREV_FILES = [
    "docker-compose.yml", "docker-compose.override.yml", "docker-compose.public-launch.yml",
    "docker-compose.feedback.yml", "docker-compose.yandex.yml", "docker-compose.google.yml",
    "docker-compose.seo-sorting.yml", "docker-compose.full.yml", "docker-compose.registry.yml",
    "docker-compose.editorial.yml", "docker-compose.footer.yml", "docker-compose.card-borders.yml",
    "docker-compose.button-spacing.yml", "docker-compose.content-pages.yml",
    "docker-compose.headlights.yml", "docker-compose.refero.yml", "docker-compose.audit.yml",
]
NEW_FILES = PREV_FILES + ["docker-compose.generation.yml"]
PUBLIC_HOST = "xn--80aeylebmo7f.xn--90ais"
OTHERS = [f"avtorinok-{n}-1" for n in ("api", "worker", "db", "test-mail")]
WEB = "avtorinok-web-1"


def log(msg):
    print(f"[deploy] {msg}", file=sys.stderr, flush=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = build_opener(ProxyHandler({}), NoRedirect)


def get(path):
    req = Request("http://127.0.0.1" + path, headers={"Host": PUBLIC_HOST, "User-Agent": "avtorinok-release-check"})
    try:
        resp = OPENER.open(req, timeout=30)
    except HTTPError as e:
        resp = e
    with resp:
        return resp.code, {k.lower(): v for k, v in resp.headers.items()}, resp.read().decode("utf-8", "replace")


def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def compose(directory, files, *args, timeout=600):
    cmd = ["docker", "compose", "-p", "avtorinok", "--project-directory", str(directory)]
    for f in files:
        cmd += ["-f", str(directory / f)]
    return run(cmd + list(args), timeout=timeout)


def inspect(name):
    return json.loads(run(["docker", "inspect", name]).stdout)[0]


def checks(before):
    res = {}
    w = inspect(WEB)
    res["web_healthy"] = (w["State"].get("Health") or {}).get("Status") == "healthy"
    res["web_image_built"] = w["Image"] == json.loads((BACKUP / "built.json").read_text())["web_image"]
    res["others_unchanged"] = all(
        inspect(n)["Id"] == before[n]["id"] and inspect(n)["State"]["StartedAt"] == before[n]["started"]
        for n in OTHERS)
    code, headers, body = get("/")
    res["home"] = (code == 200 and "Автомобили Беларуси" in body and "AURUM" not in body
                   and "noindex" not in headers.get("x-robots-tag", ""))
    code, _, body = get("/login?next=%2Fsell")
    # The registration entry is rendered client-side; it is verified in a real browser after deploy.
    res["login_page"] = code == 200 and "Войти" in body
    code, _, body = get("/cars")
    if code == 200 and "Параметры поиска" in body and "Поколение" in body:
        main_part = body.split("Дополнительные параметры")[0]
        res["cars_generation_in_main"] = "Поколение" in main_part.split("Параметры поиска", 1)[-1]
    else:
        res["cars_generation_in_main"] = False
    return res


def rollback():
    log("rolling back web to previous chain")
    r = compose(PREV_DIR, PREV_FILES, "up", "-d", "--no-deps", "--no-build", "--wait", "--wait-timeout", "180", "web")
    if ACTIVE.resolve() != PREV_DIR:
        tmp = ACTIVE.with_name(".avtorinok.rollback-tmp")
        if tmp.is_symlink():
            tmp.unlink()
        os.symlink(str(PREV_DIR), tmp)
        os.replace(tmp, ACTIVE)
    return r.returncode == 0


def main():
    if ACTIVE.resolve() != PREV_DIR or not (BACKUP / "built.json").exists() or (BACKUP / "deployed.json").exists():
        print(json.dumps({"ok": False, "error": "preconditions failed"}))
        sys.exit(1)
    stored = json.loads((BACKUP / "before.json").read_text())
    for n in OTHERS:
        if inspect(n)["Id"] != stored[n]["id"]:
            print(json.dumps({"ok": False, "error": f"{n} changed since prepare"}))
            sys.exit(1)
    # web may have been recreated by an earlier auto-rollback; it must still run the previous image.
    if inspect(WEB)["Image"] != stored[WEB]["image"]:
        print(json.dumps({"ok": False, "error": "web image changed since prepare"}))
        sys.exit(1)
    log("up web")
    r = compose(CANDIDATE, NEW_FILES, "up", "-d", "--no-deps", "--no-build", "--wait", "--wait-timeout", "180", "web")
    (BACKUP / "deploy.log").write_text(r.stdout + r.stderr)
    res = {}
    if r.returncode == 0:
        res = checks(stored)
        if not all(res.values()):
            time.sleep(15)
            res = checks(stored)
    if r.returncode != 0 or not all(res.values()):
        ok = rollback()
        out = {"ok": False, "deployed": False, "rolled_back": ok, "checks": res, "up_rc": r.returncode}
        (BACKUP / "deploy-failed.json").write_text(json.dumps(out, indent=2))
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(1 if ok else 2)
    tmp = ACTIVE.with_name(".avtorinok.switch-tmp")
    if tmp.is_symlink():
        tmp.unlink()
    os.symlink(str(CANDIDATE), tmp)
    os.replace(tmp, ACTIVE)
    out = {"ok": True, "deployed": True, "active": str(ACTIVE.resolve()), "checks": res,
           "web_image": inspect(WEB)["Image"],
           "rollback": f"compose -p avtorinok --project-directory {PREV_DIR} <17 audit files> up -d --no-deps --no-build --wait web; ln -> {PREV_DIR}"}
    (BACKUP / "deployed.json").write_text(json.dumps(out, indent=2))
    for p in BACKUP.iterdir():
        p.chmod(0o600)
    print(json.dumps(out, ensure_ascii=False))


main()
