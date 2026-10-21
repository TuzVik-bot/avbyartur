#!/usr/bin/env python3
"""Read-only guards for the 2026-10-21 Avtorinok web-only release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys


ACTIVE_LINK = Path("/home/suite/apps/avtorinok")
MANIFEST_RELATIVE = Path("deploy-backup/pre-deploy-state.json")
FINAL_SOURCE_MANIFEST = Path("deploy-backup/final-source.sha256")


def run(command: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(
            command,
            cwd=cwd,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() if exc.stderr else "command failed"
        raise RuntimeError(f"{command[0]} failed: {detail}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_containers() -> dict[str, dict[str, str]]:
    identifiers = run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            "label=com.docker.compose.project=avtorinok",
        ]
    ).split()
    template = (
        "{{.Id}}|{{.Name}}|{{.Config.Image}}|{{.Image}}|"
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}"
        "{{else}}none{{end}}"
    )
    containers: dict[str, dict[str, str]] = {}
    for identifier in identifiers:
        row = run(["docker", "inspect", "--format", template, identifier])
        container_id, raw_name, image_tag, image_id, status, health = row.split("|", 5)
        name = raw_name.lstrip("/")
        containers[name] = {
            "id": container_id,
            "image_tag": image_tag,
            "image_id": image_id,
            "status": status,
            "health": health,
        }
    return containers


def current_volumes(names: list[str]) -> dict[str, dict[str, str]]:
    volumes: dict[str, dict[str, str]] = {}
    template = "{{.Name}}|{{.Mountpoint}}|{{.Driver}}|{{.Scope}}"
    for name in names:
        row = run(["docker", "volume", "inspect", "--format", template, name])
        volume_name, mountpoint, driver, scope = row.split("|", 3)
        volumes[volume_name] = {
            "mountpoint": mountpoint,
            "driver": driver,
            "scope": scope,
        }
    return volumes


def verify_source_manifest(candidate: Path) -> None:
    manifest_path = candidate / FINAL_SOURCE_MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"final source manifest is missing: {manifest_path}")

    expected: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64 or relative in expected:
            raise RuntimeError("final source manifest is malformed")
        expected[relative] = digest

    actual: dict[str, str] = {}
    backup = candidate / "deploy-backup"
    for path in sorted(candidate.rglob("*")):
        if not path.is_file() or path.is_symlink() or backup in path.parents:
            continue
        relative = path.relative_to(candidate).as_posix()
        actual[relative] = sha256(path)
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
        raise RuntimeError(
            "candidate source differs from final manifest "
            f"(missing={len(missing)}, extra={len(extra)}, changed={len(changed)})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prebuild", "preswitch", "post"))
    args = parser.parse_args()

    candidate = Path(__file__).resolve().parents[1]
    manifest_path = candidate / MANIFEST_RELATIVE
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"baseline manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = Path(manifest["active_release_before"]).resolve(strict=True)
    expected_active = candidate.resolve(strict=True) if args.phase == "post" else baseline
    actual_active = run(["readlink", "-f", str(ACTIVE_LINK)])
    if actual_active != str(expected_active):
        raise RuntimeError(
            f"active release changed: expected {expected_active}, found {actual_active}"
        )

    env_path = Path(manifest["runtime_env_path"]).resolve(strict=True)
    candidate_env = candidate / ".env"
    if not candidate_env.is_symlink() or candidate_env.resolve(strict=True) != env_path:
        raise RuntimeError("candidate .env must remain a symlink to the original runtime env file")
    env_mode = format(stat.S_IMODE(env_path.stat().st_mode), "o")
    env_hash = sha256(env_path)
    if env_mode != "600" or env_hash != manifest["runtime_env_sha256"]:
        raise RuntimeError("runtime .env mode or SHA-256 changed")

    expected_containers = {item["name"]: item for item in manifest["containers_before"]}
    actual_containers = current_containers()
    if set(actual_containers) != set(expected_containers):
        raise RuntimeError("Avtorinok running container set changed")
    for name, expected in expected_containers.items():
        actual = actual_containers[name]
        if actual["status"] != "running" or actual["health"] != "healthy":
            raise RuntimeError(f"container is not healthy: {name}")
        if args.phase == "post" and name == "avtorinok-web-1":
            if actual["image_tag"] != f"avtorinok-web:{manifest['candidate_tag']}":
                raise RuntimeError("post-switch web image tag does not match the candidate")
            if actual["image_id"] == expected["image_id"]:
                raise RuntimeError("post-switch web still uses the previous image")
        elif actual["id"] != expected["id"] or actual["image_id"] != expected["image_id"]:
            raise RuntimeError(f"container changed unexpectedly: {name}")

    expected_volumes = manifest["volumes_before"]
    actual_volumes = current_volumes(sorted(expected_volumes))
    if actual_volumes != expected_volumes:
        raise RuntimeError("named volume identity or mountpoint changed")

    rollback_tag = manifest["web_image_tag_before"]
    rollback_id = run(["docker", "image", "inspect", "--format", "{{.Id}}", rollback_tag])
    if rollback_id != manifest["web_image_id_before"]:
        raise RuntimeError("previous web image is missing or changed")
    if Path(manifest["rollback_release"]).resolve(strict=True) != baseline:
        raise RuntimeError("recorded rollback release no longer resolves to the original release")

    if args.phase in ("preswitch", "post"):
        verify_source_manifest(candidate)
        candidate_tag = f"avtorinok-web:{manifest['candidate_tag']}"
        image_id, platform = run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Id}}|{{.Os}}/{{.Architecture}}",
                candidate_tag,
            ]
        ).split("|", 1)
        if platform != "linux/amd64":
            raise RuntimeError(f"candidate web image has wrong platform: {platform}")

        configured_images = set(
            run(
                [
                    "docker",
                    "compose",
                    "-p",
                    "avtorinok",
                    "--env-file",
                    str(env_path),
                    "-f",
                    str(candidate / "docker-compose.yml"),
                    "-f",
                    str(candidate / "docker-compose.override.yml"),
                    "config",
                    "--images",
                ],
                cwd=candidate,
            ).splitlines()
        )
        expected_images = {
            item["image_tag"] for item in expected_containers.values() if item["name"] != "avtorinok-test-mail-1"
        }
        expected_images.discard(manifest["web_image_tag_before"])
        expected_images.add(candidate_tag)
        if configured_images != expected_images:
            raise RuntimeError("candidate Compose images differ from the web-only release plan")

    print(
        json.dumps(
            {
                "phase": args.phase,
                "active_release": actual_active,
                "env_mode": env_mode,
                "env_sha256": env_hash,
                "containers": sorted(actual_containers),
                "volumes": sorted(actual_volumes),
                "rollback_image": rollback_tag,
                "result": "pass",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"preflight failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
