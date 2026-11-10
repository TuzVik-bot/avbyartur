"""Prepare release audit-20261111-r1 on the production host (no service changes).

Run as: ssh fortebit-prod python3 - < 10-prepare-server.py

Takes a pre-release snapshot (before.json), a verified database dump, rollback
image tags, extracts the uploaded source into a new release directory, writes
the release overlay and validates the resolved Compose configuration. It never
starts, stops or recreates containers, never reads .env contents and never
prints environment values (only variable names).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from html import unescape
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

# ---- Constants the lead checks or fills before running -----------------------
TAG = "audit-20261111-r1"
EXPECTED_ACTIVE_RELEASE = Path("/home/suite/apps/releases/refero-20261108-r1")
SRC_SHA256 = "d8def7286d14ca9b29345bd4023cdf107a42a2fe324622b913f5e8200e0df572"
EXPECTED_DB_REVISION = "0033_listing_in_transit"
EXPECTED_WEB_CONFIG_FILE_COUNT = 16
EXPECTED_WEB_LAST_OVERLAY = "docker-compose.refero.yml"
# Relative paths present in the running API's data mount but absent from the
# new source tree; anything not listed here aborts the prepare step.
ALLOWED_MISSING_DATA_FILES = frozenset()

# ---- Fixed layout -------------------------------------------------------------
RELEASES = Path("/home/suite/apps/releases")
ACTIVE = Path("/home/suite/apps/avtorinok")
BACKUP = Path("/home/suite/backups/avtorinok") / TAG
CANDIDATE = RELEASES / TAG
PARTIAL = RELEASES / f".{TAG}.partial"
SRC_TARBALL = RELEASES / f"{TAG}.src.tar.gz"
OVERLAY_NAME = "docker-compose.audit.yml"
PROJECT = "avtorinok"
NGINX = "http://127.0.0.1"
PUBLIC_HOST = "xn--80aeylebmo7f.xn--90ais"
HOME_TITLE = "Автомобили Беларуси"
REGISTER_ENTRY_TEXT = "Создать аккаунт"
UNKNOWN_LISTING_ID = "00000000-0000-0000-0000-000000000000"
WEB, API, WORKER, DB, MAIL = (
    f"avtorinok-{name}-1" for name in ("web", "api", "worker", "db", "test-mail")
)
CONTAINERS = (WEB, API, WORKER, DB, MAIL)
POSTGRES_VOLUME = "avtorinok_postgres"
MEDIA_VOLUME = "avtorinok_private_media"
GIB = 1024**3
PRUNE_BELOW_BYTES = 9 * GIB
MIN_FREE_BYTES = 7 * GIB
WAIT_TIMEOUT = "180"
FEATURE_FLAGS = (
    "LISTING_AUTO_PUBLISH_ENABLED",
    "PUBLIC_GUEST_CONTACT_ENABLED",
    "PUBLIC_REGISTRATION_ENABLED",
    "EMAIL_REGISTRATION_ENABLED",
    "EMAIL_REGISTRATION_PILOT_ENABLED",
    "SMS_LOGIN_ENABLED",
    "ONLINER_SYNC_ENABLED",
    "TEST_MAIL_ENABLED",
    "SESSION_COOKIE_SECURE",
    "APP_ENV",
)
LABEL_FILES = "com.docker.compose.project.config_files"
LABEL_WORKDIR = "com.docker.compose.project.working_dir"
LABEL_ENVFILE = "com.docker.compose.project.environment_file"
LABEL_PROJECT = "com.docker.compose.project"
LABEL_SERVICE = "com.docker.compose.service"


class Abort(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Abort(message)


def log(message):
    print(f"[prepare] {message}", file=sys.stderr, flush=True)


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


def must(cmd, what, *, cwd=None, timeout=900):
    result = run(cmd, cwd=cwd, timeout=timeout)
    require(
        result.returncode == 0,
        f"{what} failed (exit {result.returncode}): {tail(result.stderr)}",
    )
    return result.stdout


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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def home_snapshot():
    status, headers, body = nginx_get("/")
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S)
    title = unescape(match.group(1)).strip() if match else None
    return {
        "status": status,
        "title": title,
        "title_ok": bool(title and HOME_TITLE in title),
        "aurum_present": "AURUM" in body,
        "x_robots_noindex": "noindex" in headers.get("x-robots-tag", "").lower(),
        "csp_frame_ancestors": "frame-ancestors"
        in headers.get("content-security-policy", ""),
    }


def container_record(item):
    labels = item["Config"].get("Labels") or {}
    record = {
        "id": item["Id"],
        "image_id": item["Image"],
        "image": item["Config"]["Image"],
        "started_at": item["State"]["StartedAt"],
        "status": item["State"]["Status"],
        "health": (item["State"].get("Health") or {}).get("Status"),
        "restart_count": item.get("RestartCount"),
        "service": labels.get(LABEL_SERVICE),
        "project": labels.get(LABEL_PROJECT),
        "config_files": [
            part for part in labels.get(LABEL_FILES, "").split(",") if part
        ],
        "working_dir": labels.get(LABEL_WORKDIR),
        "environment_files": [
            part for part in labels.get(LABEL_ENVFILE, "").split(",") if part
        ],
        "port_bindings": item["HostConfig"].get("PortBindings") or {},
        "mounts": [
            {
                "type": m["Type"],
                "name": m.get("Name"),
                "source": m["Source"],
                "destination": m["Destination"],
                "rw": m.get("RW"),
            }
            for m in item["Mounts"]
        ],
    }
    return record


def docker_port_set(port_bindings):
    result = set()
    for container_port, bindings in (port_bindings or {}).items():
        for binding in bindings or []:
            result.add(
                (
                    binding.get("HostIp") or "",
                    str(binding.get("HostPort") or ""),
                    container_port,
                )
            )
    return sorted(result)


def compose_port_set(service):
    result = set()
    for port in service.get("ports") or []:
        protocol = port.get("protocol") or "tcp"
        result.add(
            (
                port.get("host_ip") or "",
                str(port.get("published") or ""),
                f"{port['target']}/{protocol}",
            )
        )
    return sorted(result)


def compose_base(project_dir, files, env_files=()):
    command = [
        "docker",
        "compose",
        "-p",
        PROJECT,
        "--project-directory",
        str(project_dir),
    ]
    for env_file in env_files:
        command.extend(["--env-file", env_file])
    for item in files:
        command.extend(["-f", str(item)])
    return command


def compose_config(base, cwd, what):
    # The resolved config contains interpolated secrets: parse it in memory only.
    return json.loads(must(base + ["config", "--format", "json"], what, cwd=cwd))


def free_bytes():
    paths = [RELEASES]
    root = run(["docker", "info", "--format", "{{.DockerRootDir}}"]).stdout.strip()
    paths.append(Path(root) if root else Path("/"))
    values = []
    for path in paths:
        try:
            values.append(shutil.disk_usage(path).free)
        except OSError:
            values.append(shutil.disk_usage("/").free)
    return min(values)


def ensure_disk():
    before = free_bytes()
    pruned = False
    if before < PRUNE_BELOW_BYTES:
        log(
            f"free {before / GIB:.2f} GiB < 9 GiB: pruning build cache older than 72h and dangling images"
        )
        must(
            ["docker", "builder", "prune", "-f", "--filter", "until=72h"],
            "docker builder prune",
            timeout=1800,
        )
        must(
            ["docker", "image", "prune", "-f"],
            "docker image prune (dangling only)",
            timeout=1800,
        )
        pruned = True
    after = free_bytes()
    require(
        after >= MIN_FREE_BYTES,
        f"only {after / GIB:.2f} GiB free after pruning; need >= 7 GiB",
    )
    return {"free_before_bytes": before, "free_after_bytes": after, "pruned": pruned}


def check_running_state(containers):
    for name, item in containers.items():
        require(item["State"]["Status"] == "running", f"{name} is not running")
        health = (item["State"].get("Health") or {}).get("Status")
        require(health == "healthy", f"{name} health is {health!r}, expected 'healthy'")
        labels = item["Config"].get("Labels") or {}
        require(
            labels.get(LABEL_PROJECT) == PROJECT,
            f"{name} does not belong to compose project {PROJECT}",
        )


def check_volumes(containers):
    def named(item):
        return {
            m.get("Name"): m["Destination"]
            for m in item["Mounts"]
            if m["Type"] == "volume"
        }

    require(
        named(containers[DB]).get(POSTGRES_VOLUME) == "/var/lib/postgresql/data",
        "db is not using avtorinok_postgres",
    )
    for name in (API, WORKER):
        require(
            named(containers[name]).get(MEDIA_VOLUME) == "/app/private-media",
            f"{name} is not using {MEDIA_VOLUME}",
        )


def check_env_mode(path):
    """Stat only (follows symlinks); the file is never opened."""
    require(os.path.exists(path), f"{path} does not exist")
    mode = os.stat(path).st_mode & 0o777
    require(mode == 0o600, f"{path} mode is {oct(mode)}, expected 0o600")
    return os.path.realpath(path)


def check_env_file(path):
    require(
        path.is_symlink(), f"{path} must be a symlink to the protected runtime env file"
    )
    return check_env_mode(path)


def alembic_current_running():
    output = must(
        ["docker", "exec", API, "alembic", "current"],
        "alembic current (running api)",
        timeout=120,
    )
    revisions = [
        m.group(1)
        for m in (
            re.match(r"^(\S+)(?: \((?:effective )?head\))?\s*$", line)
            for line in output.splitlines()
        )
        if m
    ]
    require(
        len(revisions) == 1,
        f"unexpected alembic current output ({len(revisions)} revisions)",
    )
    return revisions[0]


def psql_scalar(sql):
    script = f'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1 -c "{sql}"'
    return must(
        ["docker", "exec", DB, "sh", "-c", script], "psql query", timeout=120
    ).strip()


def http_snapshot():
    status, _, body = nginx_get("/api/v1/auth/capabilities")
    require(status == 200, f"capabilities returned {status}")
    capabilities = json.loads(body)
    require(isinstance(capabilities, dict), "capabilities is not a JSON object")
    home = home_snapshot()
    require(
        home["status"] == 200 and home["title_ok"],
        f"home check failed before release: status {home['status']}",
    )
    require(
        not home["aurum_present"],
        "home page contains AURUM before release; wrong vhost",
    )
    login_status, _, login_body = nginx_get("/login?next=%2Fsell")
    archived_id = (
        psql_scalar(
            "SELECT id FROM listings WHERE status = 'archived' ORDER BY id LIMIT 1"
        )
        or None
    )
    if archived_id is not None:
        require(
            re.fullmatch(r"[0-9a-f-]{36}", archived_id),
            "unexpected archived listing id format",
        )
    probes = {"unknown": nginx_get(f"/api/v1/listings/{UNKNOWN_LISTING_ID}")[0]}
    if archived_id:
        probes["archived"] = nginx_get(f"/api/v1/listings/{archived_id}")[0]
    return {
        "capabilities": capabilities,
        "home": home,
        "login_status": login_status,
        "login_has_register_entry": REGISTER_ENTRY_TEXT in login_body,
        "archived_listing_id": archived_id,
        "listing_probe_status": probes,
    }


def dump_database():
    dump = BACKUP / "database.dump"
    fd = os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as target:
        result = subprocess.run(
            [
                "docker",
                "exec",
                DB,
                "sh",
                "-c",
                'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
            ],
            stdout=target,
            stderr=subprocess.PIPE,
            check=False,
            timeout=3600,
        )
    require(
        result.returncode == 0,
        f"pg_dump failed: {tail(result.stderr.decode('utf-8', 'replace'))}",
    )
    size = dump.stat().st_size
    require(size > 1024 * 1024, f"database dump is suspiciously small ({size} bytes)")
    with dump.open("rb") as source:
        listing = subprocess.run(
            ["docker", "exec", "-i", DB, "pg_restore", "-l"],
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=600,
        )
    require(listing.returncode == 0, "pg_restore -l could not read the dump")
    entries = sum(
        1
        for line in listing.stdout.decode("utf-8", "replace").splitlines()
        if line and not line.startswith(";")
    )
    require(entries > 0, "pg_restore -l listed no entries")
    digest = sha256_file(dump)
    write_private(BACKUP / "database.sha256", f"{digest}  database.dump\n".encode())
    return {"path": str(dump), "bytes": size, "sha256": digest, "toc_entries": entries}


def tag_rollback_images(containers):
    web_image = containers[WEB]["Image"]
    api_image = containers[API]["Image"]
    require(
        containers[WORKER]["Image"] == api_image,
        "worker and api run different images; review the rollback plan by hand",
    )
    tags = {
        f"avtorinok-web:rollback-{TAG}": web_image,
        f"avtorinok-api:rollback-{TAG}": api_image,
    }
    for tag, image in tags.items():
        existing = image_id_of(tag)
        require(existing in (None, image), f"{tag} already points to a different image")
        must(["docker", "tag", image, tag], f"docker tag {tag}")
        require(
            image_id_of(tag) == image, f"{tag} does not resolve to the running image"
        )
    return tags


def safe_extract(archive, destination):
    dest = os.path.realpath(destination)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        require(members, "source archive is empty")
        for member in members:
            path = PurePosixPath(member.name)
            require(
                not path.is_absolute() and ".." not in path.parts,
                f"unsafe archive member path: {member.name}",
            )
            require(
                member.isfile() or member.isdir() or member.issym(),
                f"unsupported archive member type: {member.name}",
            )
            require(
                not (
                    path.name == ".env"
                    or (path.name.startswith(".env.") and path.name != ".env.example")
                ),
                f"archive must not contain env files: {member.name}",
            )
            if member.issym():
                require(
                    not PurePosixPath(member.linkname).is_absolute(),
                    f"absolute symlink in archive: {member.name}",
                )
                target = os.path.normpath(
                    os.path.join(dest, os.path.dirname(member.name), member.linkname)
                )
                require(
                    target == dest or target.startswith(dest + os.sep),
                    f"symlink escapes the release: {member.name}",
                )
        if hasattr(tarfile, "data_filter"):
            tar.extractall(destination, members=members, filter="data")
        else:
            tar.extractall(destination, members=members)
    return len(members)


def verify_source_archive(config_file_names):
    """Checksum and member names of the uploaded archive, before anything is written."""
    require(
        re.fullmatch(r"[0-9a-f]{64}", SRC_SHA256),
        "SRC_SHA256 is not filled in (64 lowercase hex chars)",
    )
    require(SRC_TARBALL.is_file(), f"{SRC_TARBALL} not found; upload it first")
    actual = sha256_file(SRC_TARBALL)
    require(actual == SRC_SHA256, f"source archive sha256 mismatch: {actual}")
    with tarfile.open(SRC_TARBALL, "r:gz") as tar:
        names = {PurePosixPath(m.name).as_posix() for m in tar.getmembers() if m.isfile()}
    for required in ["backend/Dockerfile", "web/Dockerfile", "data/catalog.json", *config_file_names]:
        require(required in names, f"source archive is missing {required}")
    return names


def extract_source():
    actual = sha256_file(SRC_TARBALL)
    require(actual == SRC_SHA256, f"source archive changed after verification: {actual}")
    PARTIAL.mkdir(mode=0o755)
    members = safe_extract(SRC_TARBALL, PARTIAL)
    os.rename(PARTIAL, CANDIDATE)
    for required in (
        "docker-compose.yml",
        "backend/Dockerfile",
        "web/Dockerfile",
        "data/catalog.json",
    ):
        require((CANDIDATE / required).is_file(), f"release is missing {required}")
    return {"sha256": actual, "members": members}


def write_overlay():
    overlay = (
        "services:\n"
        "  api:\n"
        f"    image: avtorinok-api:{TAG}\n"
        "  worker:\n"
        f"    image: avtorinok-api:{TAG}\n"
        "  web:\n"
        f"    image: avtorinok-web:{TAG}\n"
        "    build:\n"
        "      args:\n"
        '        AVTORINOK_PUBLIC_INDEXING_ENABLED: "true"\n'
    )
    (CANDIDATE / OVERLAY_NAME).write_text(overlay)


def named_volume_sources(service):
    return {
        v.get("source")
        for v in service.get("volumes") or []
        if v.get("type") == "volume"
    }


def validate_candidate_config(resolved, containers):
    services = resolved.get("services", {})
    for name in ("api", "worker", "web", "db"):
        require(name in services, f"resolved compose config has no service {name}")
    require(
        services["api"]["image"] == f"avtorinok-api:{TAG}",
        "api image is not the release tag",
    )
    require(
        services["worker"]["image"] == f"avtorinok-api:{TAG}",
        "worker image is not the release tag",
    )
    require(
        services["web"]["image"] == f"avtorinok-web:{TAG}",
        "web image is not the release tag",
    )
    require(
        services["db"]["image"] == containers[DB]["Config"]["Image"],
        "db image would change; the db container must not be recreated",
    )
    for name in ("api", "worker", "db"):
        require(not services[name].get("ports"), f"{name} must not publish ports")
    require(
        compose_port_set(services["web"])
        == docker_port_set(containers[WEB]["HostConfig"].get("PortBindings")),
        "web published port differs from the running container",
    )
    volumes = resolved.get("volumes", {})
    by_name = {spec.get("name"): key for key, spec in volumes.items()}
    require(
        POSTGRES_VOLUME in by_name and MEDIA_VOLUME in by_name,
        "named volumes changed in resolved config",
    )
    require(
        by_name[POSTGRES_VOLUME] in named_volume_sources(services["db"]),
        "db does not mount the postgres volume",
    )
    for name in ("api", "worker"):
        require(
            by_name[MEDIA_VOLUME] in named_volume_sources(services[name]),
            f"{name} does not mount the media volume",
        )
    web_env = services["web"].get("environment") or {}
    require(
        str(web_env.get("AVTORINOK_PUBLIC_INDEXING_ENABLED")).lower() == "true",
        "web AVTORINOK_PUBLIC_INDEXING_ENABLED is not true",
    )
    build_args = (services["web"].get("build") or {}).get("args") or {}
    require(
        str(build_args.get("AVTORINOK_PUBLIC_INDEXING_ENABLED")).lower() == "true",
        "web build arg AVTORINOK_PUBLIC_INDEXING_ENABLED is not true",
    )
    for name in ("api", "worker", "web"):
        for volume in services[name].get("volumes") or []:
            if volume.get("type") == "bind":
                require(
                    Path(volume["source"]).exists(),
                    f"{name} bind source is missing: {volume['source']}",
                )


def list_files(root):
    result = set()
    for directory, _, files in os.walk(root):
        for file in files:
            result.add(os.path.relpath(os.path.join(directory, file), root))
    return result


def check_data_files(containers, archive_names):
    sources = [
        m["Source"]
        for m in containers[API]["Mounts"]
        if m["Destination"] == "/app/data"
    ]
    require(len(sources) == 1, "running api has no single /app/data mount")
    release = {name[len("data/"):] for name in archive_names if name.startswith("data/")}
    missing = sorted(list_files(sources[0]) - release)
    unexpected = [name for name in missing if name not in ALLOWED_MISSING_DATA_FILES]
    require(
        not unexpected,
        f"data files present in the running api mount but missing in the release: {unexpected[:20]}",
    )
    return {"old_data_dir": sources[0], "missing_allowed": missing}


def env_map(entries):
    result = {}
    for entry in entries or []:
        key, _, value = entry.partition("=")
        result[key] = value
    return result


def flag_status(name, old, new):
    if name not in old and name not in new:
        return "absent"
    if name not in old:
        return "added"
    if name not in new:
        return "removed"
    return "same" if old[name] == new[name] else "changed"


def env_diff(resolved, containers):
    """Names-only comparison of the running container env vs the resolved compose env."""
    report = {}
    for service, container in (("api", API), ("worker", WORKER), ("web", WEB)):
        item = containers[container]
        new = {
            k: "" if v is None else str(v)
            for k, v in (resolved["services"][service].get("environment") or {}).items()
        }
        old = env_map(item["Config"].get("Env"))
        image = json.loads(
            must(
                ["docker", "image", "inspect", item["Image"]],
                f"image inspect {service}",
            )
        )[0]
        image_names = set(env_map(image["Config"].get("Env")))
        entry = {
            "added": sorted(set(new) - set(old)),
            "removed": sorted(set(old) - set(new) - image_names),
            "changed": sorted(k for k in set(new) & set(old) if new[k] != old[k]),
        }
        if service in ("api", "worker"):
            entry["feature_flags"] = {
                flag: flag_status(flag, old, new) for flag in FEATURE_FLAGS
            }
        report[service] = entry
        del new, old
    return report


def previous_chains(containers):
    groups = {}
    for name, service in ((API, "api"), (WORKER, "worker"), (WEB, "web")):
        record = container_record(containers[name])
        require(
            record["working_dir"] and record["config_files"],
            f"{name} has no compose labels",
        )
        for file in record["config_files"]:
            require(Path(file).is_file(), f"previous compose file missing: {file}")
        for env_file in record["environment_files"]:
            require(
                os.path.exists(env_file) and os.stat(env_file).st_mode & 0o777 == 0o600,
                f"previous env file missing or not 600: {env_file}",
            )
        key = (
            record["working_dir"],
            tuple(record["config_files"]),
            tuple(record["environment_files"]),
        )
        groups.setdefault(key, []).append(service)
    plan = []
    for (working_dir, files, env_files), services in groups.items():
        require(
            Path(working_dir).is_dir(), f"previous working dir missing: {working_dir}"
        )
        if not env_files:
            check_env_mode(Path(working_dir) / ".env")
        base = compose_base(working_dir, files, env_files)
        resolved = compose_config(
            base, working_dir, f"compose config for previous chain in {working_dir}"
        )
        for service in services:
            container = containers[f"avtorinok-{service}-1"]
            require(
                resolved["services"][service]["image"] == container["Config"]["Image"],
                f"previous chain for {service} does not resolve to the running image ref",
            )
            require(
                image_id_of(container["Config"]["Image"]) == container["Image"],
                f"image ref {container['Config']['Image']} no longer points to the running {service} image",
            )
        if "web" in services:
            require(
                compose_port_set(resolved["services"]["web"])
                == docker_port_set(containers[WEB]["HostConfig"].get("PortBindings")),
                "previous web chain resolves a different port",
            )
        plan.append(
            {
                "services": services,
                "project_directory": working_dir,
                "command": base
                + [
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--wait",
                    "--wait-timeout",
                    WAIT_TIMEOUT,
                ]
                + services,
            }
        )
    plan.sort(key=lambda group: 0 if "api" in group["services"] else 1)
    return plan


def main():
    require(ACTIVE.is_symlink(), f"{ACTIVE} is not a symlink")
    previous = ACTIVE.resolve()
    require(
        previous == EXPECTED_ACTIVE_RELEASE,
        f"active release is {previous}, expected {EXPECTED_ACTIVE_RELEASE}",
    )
    containers = {name: inspect(name) for name in CONTAINERS}
    check_running_state(containers)
    env_real = check_env_file(ACTIVE / ".env")
    check_volumes(containers)
    web_record = container_record(containers[WEB])
    require(
        len(web_record["config_files"]) == EXPECTED_WEB_CONFIG_FILE_COUNT,
        f"web compose chain has {len(web_record['config_files'])} files, expected {EXPECTED_WEB_CONFIG_FILE_COUNT}",
    )
    require(
        Path(web_record["config_files"][-1]).name == EXPECTED_WEB_LAST_OVERLAY,
        "web compose chain does not end with the refero overlay",
    )
    require(
        Path(web_record["working_dir"]) == EXPECTED_ACTIVE_RELEASE,
        "web container was not started from the active release",
    )
    require(
        len({Path(item).name for item in web_record["config_files"]})
        == len(web_record["config_files"]),
        "duplicate compose file names in web chain",
    )
    for path in (CANDIDATE, PARTIAL, BACKUP):
        require(
            not os.path.lexists(path),
            f"{path} already exists; this release was prepared before (inspect it by hand)",
        )
    require(BACKUP.parent.is_dir(), f"{BACKUP.parent} does not exist")

    log("snapshot: alembic, HTTP, containers")
    revision = alembic_current_running()
    require(
        revision == EXPECTED_DB_REVISION,
        f"database is at {revision}, expected {EXPECTED_DB_REVISION}",
    )
    snapshot = http_snapshot()
    log("rollback readiness: previous compose chains")
    rollback_groups = previous_chains(containers)
    archive_names = verify_source_archive(
        [Path(item).name for item in web_record["config_files"]]
    )
    data_check = check_data_files(containers, archive_names)

    # Everything below writes: disk cleanup, receipts, dump, tags, release dir.
    disk = ensure_disk()
    BACKUP.mkdir(mode=0o700)
    os.chmod(BACKUP, 0o700)
    before = {
        "tag": TAG,
        "taken_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_release": str(previous),
        "candidate": str(CANDIDATE),
        "env_realpath": env_real,
        "env_mode": "0o600",
        "alembic_current": revision,
        "containers": {
            name: container_record(item) for name, item in containers.items()
        },
        "db": {
            "id": containers[DB]["Id"],
            "started_at": containers[DB]["State"]["StartedAt"],
            "image": containers[DB]["Config"]["Image"],
        },
        "disk": disk,
        **snapshot,
    }
    write_private(BACKUP / "before.json", before)

    log("pg_dump")
    dump = dump_database()
    rollback_tags = tag_rollback_images(containers)

    log("extracting source")
    source = extract_source()
    os.symlink(env_real, CANDIDATE / ".env")
    require(
        check_env_file(CANDIDATE / ".env") == env_real,
        "candidate .env does not resolve to the active env file",
    )
    write_overlay()
    compose_files = [
        CANDIDATE / Path(item).name for item in web_record["config_files"]
    ] + [CANDIDATE / OVERLAY_NAME]
    for file in compose_files:
        require(file.is_file(), f"release is missing compose file {file.name}")
    compose_command = compose_base(CANDIDATE, compose_files)
    resolved = compose_config(
        compose_command, CANDIDATE, "compose config for the release"
    )
    validate_candidate_config(resolved, containers)
    diff = env_diff(resolved, containers)
    del resolved
    write_private(BACKUP / "env-diff.json", diff)
    diff_sha = sha256_file(BACKUP / "env-diff.json")

    rollback = {
        "tag": TAG,
        "symlink_target": str(previous),
        "groups": rollback_groups,
        "expected_image_ids": {
            name: containers[name]["Image"] for name in (API, WORKER, WEB)
        },
        "image_refs": {
            name: containers[name]["Config"]["Image"] for name in (API, WORKER, WEB)
        },
        "rollback_tags": rollback_tags,
        "database": "not downgraded; migrations are additive and compatible with the previous api image",
    }
    write_private(BACKUP / "rollback.json", rollback)
    prepared = {
        "tag": TAG,
        "previous_release": str(previous),
        "candidate": str(CANDIDATE),
        "compose_files": [str(item) for item in compose_files],
        "compose_command": compose_command,
        "expected_db_revision": EXPECTED_DB_REVISION,
        "source": source,
        "dump": dump,
        "data_check": data_check,
        "env_diff_sha256": diff_sha,
        "web_ports": docker_port_set(containers[WEB]["HostConfig"].get("PortBindings")),
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_private(BACKUP / "prepared.json", prepared)
    return {
        "prepared": True,
        "candidate": str(CANDIDATE),
        "backup": str(BACKUP),
        "dump_bytes": dump["bytes"],
        "dump_toc_entries": dump["toc_entries"],
        "disk_free_gib": round(free_bytes() / GIB, 2),
        "pruned": disk["pruned"],
        "alembic_current": revision,
        "login_has_register_entry": snapshot["login_has_register_entry"],
        "listing_probe_status": snapshot["listing_probe_status"],
        "csp_before": snapshot["home"]["csp_frame_ancestors"],
        "rollback_groups": [
            {"services": g["services"], "project_directory": g["project_directory"]}
            for g in rollback_groups
        ],
        "rollback_tags": sorted(rollback_tags),
        "data_missing_allowed": data_check["missing_allowed"],
        "env_diff": diff,
        "env_diff_sha256": diff_sha,
        "next": "review env_diff, then put env_diff_sha256 into APPROVED_ENV_DIFF_SHA256 of 30-deploy-server.py",
    }


if __name__ == "__main__":
    try:
        summary = main()
    except Abort as error:
        print(
            json.dumps(
                {"prepared": False, "error": redact(str(error))}, ensure_ascii=False
            )
        )
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - report the class without leaking values
        print(
            json.dumps(
                {
                    "prepared": False,
                    "error": type(error).__name__,
                    "detail": redact(str(error))[:300],
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    print(json.dumps(summary, ensure_ascii=False))
