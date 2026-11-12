"""Web-only release generation-20261112-r1: snapshot, backup, unpack, overlay, build web.

Runs on the VPS via `ssh ... python3 - < 10-prepare-build-server.py`. Does not touch
running services, nginx, systemd, volumes or .env contents. Prints one JSON line.
"""
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

TAG = "generation-20261112-r1"
PREV_TAG = "audit-20261111-r1"
SRC_SHA256 = "__SRC_SHA256__"
RELEASES = Path("/home/suite/apps/releases")
ACTIVE = Path("/home/suite/apps/avtorinok")
PREV_DIR = RELEASES / PREV_TAG
CANDIDATE = RELEASES / TAG
PARTIAL = RELEASES / f".{TAG}.partial"
ARCHIVE = RELEASES / f"{TAG}.src.tar.gz"
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
OVERLAY = "docker-compose.generation.yml"
PREV_FILES = [
    "docker-compose.yml", "docker-compose.override.yml", "docker-compose.public-launch.yml",
    "docker-compose.feedback.yml", "docker-compose.yandex.yml", "docker-compose.google.yml",
    "docker-compose.seo-sorting.yml", "docker-compose.full.yml", "docker-compose.registry.yml",
    "docker-compose.editorial.yml", "docker-compose.footer.yml", "docker-compose.card-borders.yml",
    "docker-compose.button-spacing.yml", "docker-compose.content-pages.yml",
    "docker-compose.headlights.yml", "docker-compose.refero.yml", "docker-compose.audit.yml",
]
NEW_FILES = PREV_FILES + [OVERLAY]
DB = "avtorinok-db-1"
CONTAINERS = [f"avtorinok-{n}-1" for n in ("web", "api", "worker", "db", "test-mail")]


def log(msg):
    print(f"[prepare] {msg}", file=sys.stderr, flush=True)


def fail(msg, **extra):
    print(json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


def run(cmd, timeout=600, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


def compose(directory, files, *args, timeout=600):
    cmd = ["docker", "compose", "-p", "avtorinok", "--project-directory", str(directory)]
    for f in files:
        cmd += ["-f", str(directory / f)]
    return run(cmd + list(args), timeout=timeout)


def inspect(name):
    r = run(["docker", "inspect", name])
    if r.returncode != 0:
        fail(f"container {name} missing")
    return json.loads(r.stdout)[0]


def web_config(directory, files):
    r = compose(directory, files, "config", "--format", "json")
    if r.returncode != 0:
        fail("compose config failed", stderr=r.stderr[-800:])
    return json.loads(r.stdout)


def main():
    # ---- read-only checks ----
    if ACTIVE.resolve() != PREV_DIR:
        fail(f"active link is {ACTIVE.resolve()}, expected {PREV_DIR}")
    for p in (CANDIDATE, PARTIAL, BACKUP):
        if p.exists():
            fail(f"{p} already exists")
    before = {}
    for name in CONTAINERS:
        info = inspect(name)
        health = (info["State"].get("Health") or {}).get("Status")
        if info["State"]["Status"] != "running" or health not in (None, "healthy"):
            fail(f"{name} not healthy: {info['State']['Status']}/{health}")
        before[name] = {"id": info["Id"], "image": info["Image"], "started": info["State"]["StartedAt"],
                        "config_image": info["Config"]["Image"]}
    if before["avtorinok-web-1"]["config_image"] != f"avtorinok-web:{PREV_TAG}":
        fail("web is not running the audit image")
    env_link = PREV_DIR / ".env"
    env_real = os.path.realpath(env_link)
    if oct(os.stat(env_real).st_mode & 0o777) != "0o600":
        fail(".env mode is not 600")
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != SRC_SHA256:
        fail("archive sha256 mismatch", got=digest)
    free_gib = os.statvfs("/home").f_bavail * os.statvfs("/home").f_frsize / 2**30
    if free_gib < 5:
        fail(f"free disk {free_gib:.1f} GiB < 5")

    # ---- writes: backup ----
    BACKUP.mkdir(parents=True, mode=0o700)
    (BACKUP / "before.json").write_text(json.dumps(before, indent=2))
    log("pg_dump")
    dump = BACKUP / "database.dump"
    with dump.open("wb") as target:
        r = subprocess.run(["docker", "exec", DB, "sh", "-c",
                            'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
                           stdout=target, stderr=subprocess.PIPE, timeout=3600)
    if r.returncode != 0 or dump.stat().st_size < 1024 * 1024:
        fail("pg_dump failed or too small")
    with dump.open("rb") as src:
        r = subprocess.run(["docker", "exec", "-i", DB, "pg_restore", "-l"], stdin=src,
                           capture_output=True, timeout=600)
    if r.returncode != 0:
        fail("pg_restore -l failed")
    toc = sum(1 for line in r.stdout.decode().splitlines() if line and not line.startswith(";"))
    for p in BACKUP.iterdir():
        p.chmod(0o600)
    r = run(["docker", "tag", before["avtorinok-web-1"]["image"], f"avtorinok-web:rollback-{TAG}"])
    if r.returncode != 0:
        fail("rollback tag failed")

    # ---- unpack ----
    log("extracting")
    PARTIAL.mkdir(mode=0o755)
    with tarfile.open(ARCHIVE) as tar:
        for m in tar.getmembers():
            target = (PARTIAL / m.name).resolve()
            if not str(target).startswith(str(PARTIAL.resolve())) or m.issym() or m.islnk():
                if m.issym() or m.islnk():
                    continue
                fail(f"unsafe member {m.name}")
        tar.extractall(PARTIAL, members=[m for m in tar.getmembers() if not (m.issym() or m.islnk())])
    if (PARTIAL / ".env").exists():
        fail("archive contains .env")
    os.symlink(env_real, PARTIAL / ".env")
    (PARTIAL / "docker-compose.audit.yml").write_bytes((PREV_DIR / "docker-compose.audit.yml").read_bytes())
    (PARTIAL / OVERLAY).write_text(
        "services:\n"
        "  web:\n"
        f"    image: avtorinok-web:{TAG}\n"
        "    build:\n"
        "      args:\n"
        '        AVTORINOK_PUBLIC_INDEXING_ENABLED: "true"\n'
    )
    PARTIAL.rename(CANDIDATE)

    # ---- compose config comparison ----
    old = web_config(PREV_DIR, PREV_FILES)
    new = web_config(CANDIDATE, NEW_FILES)
    for svc in ("api", "worker", "db", "test-mail"):
        o, n = old["services"].get(svc), new["services"].get(svc)
        # test-mail runs from an older separate chain and is absent from both; that is fine.
        if (o is None) != (n is None) or (o is not None and o.get("image") != n.get("image")):
            fail(f"service {svc} image differs between chains")
    ow, nw = dict(old["services"]["web"]), dict(new["services"]["web"])
    if nw.get("image") != f"avtorinok-web:{TAG}":
        fail("new web image tag wrong")
    if (nw.get("build") or {}).get("args", {}).get("AVTORINOK_PUBLIC_INDEXING_ENABLED") != "true":
        fail("indexing build arg missing")
    diff_keys = []
    for key in set(ow) | set(nw):
        if key in ("image", "build"):
            continue
        a, b = json.dumps(ow.get(key), sort_keys=True), json.dumps(nw.get(key), sort_keys=True)
        if a.replace(str(PREV_DIR), "@") != b.replace(str(CANDIDATE), "@"):
            diff_keys.append(key)
    if diff_keys:
        fail("web service config differs beyond image", keys=diff_keys)
    if old.get("volumes") != new.get("volumes"):
        fail("named volumes differ")

    # ---- build web ----
    log("building web (this takes a while)")
    t0 = time.time()
    r = compose(CANDIDATE, NEW_FILES, "build", "web", timeout=3600)
    (BACKUP / "build.log").write_text(r.stdout + r.stderr)
    (BACKUP / "build.log").chmod(0o600)
    if r.returncode != 0:
        fail("web build failed", tail=(r.stdout + r.stderr)[-2500:])
    r = run(["docker", "image", "inspect", f"avtorinok-web:{TAG}", "--format",
             "{{.Id}} {{.Architecture}}"])
    image_id, arch = r.stdout.split()
    if arch != "amd64" or image_id == before["avtorinok-web-1"]["image"]:
        fail("built image invalid", arch=arch)
    built = {"web_image": image_id, "build_seconds": round(time.time() - t0), "toc_entries": toc,
             "dump_bytes": dump.stat().st_size, "src_sha256": digest}
    (BACKUP / "built.json").write_text(json.dumps(built, indent=2))
    (BACKUP / "built.json").chmod(0o600)
    built.update(ok=True, free_gib=round(os.statvfs("/home").f_bavail * os.statvfs("/home").f_frsize / 2**30, 1))
    print(json.dumps(built))


main()
