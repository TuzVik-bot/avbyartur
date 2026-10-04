"""Preflight or transfer one already-encrypted age backup bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

REMOTE_PATTERN = r"[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9_][A-Za-z0-9_.-]*"
REMOTE_RE = re.compile(rf"{REMOTE_PATTERN}\Z", re.ASCII)
TARGET_RE = re.compile(rf"({REMOTE_PATTERN}):(/(?:[A-Za-z0-9_.-]+/?)*)\Z", re.ASCII)
BUNDLE_RE = re.compile(r"avtorinok-[0-9]{8}T[0-9]{6}Z\.tar\.age\Z", re.ASCII)
SSH_OPTIONS = ("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")
CHUNK_SIZE = 1024 * 1024
AGE_HEADER = b"age-encryption.org/v1\n"


class OffsiteError(ValueError):
    pass


@contextmanager
def _bundle(path: Path, *, stage_for_transfer: bool):
    """Validate one safe source descriptor and optionally stage its exact bytes."""

    requested = path.expanduser()
    private_directory = None
    try:
        metadata = requested.lstat()
    except OSError as exc:
        raise OffsiteError("Encrypted bundle is missing or unreadable.") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise OffsiteError("Encrypted bundle must be a regular file, not a link or special file.")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise OffsiteError("Encrypted bundle must not be readable by group or other users.")
    if BUNDLE_RE.fullmatch(requested.name) is None:
        raise OffsiteError("Encrypted bundle must use the avtorinok-YYYYMMDDTHHMMSSZ.tar.age name.")
    try:
        descriptor = os.open(requested, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise OffsiteError("Could not safely open the encrypted bundle.") from exc

    try:
        if stage_for_transfer:
            private_directory = tempfile.TemporaryDirectory(prefix="avtorinok-offsite-")
            os.chmod(private_directory.name, 0o700, follow_symlinks=False)
            staged_bundle = Path(private_directory.name) / requested.name
        else:
            staged_bundle = requested

        staged_descriptor = None
        try:
            source_file = os.fdopen(descriptor, "rb")
            descriptor = -1
            with source_file as source:
                opened = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                    or stat.S_IMODE(opened.st_mode) & 0o077
                ):
                    raise OffsiteError("Encrypted bundle changed or has unsafe permissions.")
                if source.read(len(AGE_HEADER)) != AGE_HEADER:
                    raise OffsiteError("Input does not have an age-encrypted bundle header.")
                source.seek(0)
                if stage_for_transfer:
                    staged_descriptor = os.open(
                        staged_bundle,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )

                digest = hashlib.sha256()
                size = 0
                if staged_descriptor is None:
                    target_context = None
                else:
                    target_context = os.fdopen(staged_descriptor, "wb")

                if target_context is None:
                    while chunk := source.read(CHUNK_SIZE):
                        digest.update(chunk)
                        size += len(chunk)
                else:
                    with target_context as target:
                        os.fchmod(target.fileno(), 0o600)
                        while chunk := source.read(CHUNK_SIZE):
                            digest.update(chunk)
                            size += len(chunk)
                            if target.write(chunk) != len(chunk):
                                raise OffsiteError("Could not create a complete private bundle copy.")
                        target.flush()
                        os.fsync(target.fileno())

                after = os.fstat(source.fileno())
                if (
                    size != opened.st_size
                    or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                ):
                    raise OffsiteError("Encrypted bundle changed while it was being checked.")

            if staged_descriptor is not None:
                staged_metadata = staged_bundle.lstat()
                if (
                    not stat.S_ISREG(staged_metadata.st_mode)
                    or stat.S_IMODE(staged_metadata.st_mode) & 0o077
                    or staged_metadata.st_size != size
                ):
                    raise OffsiteError("Private encrypted-bundle copy is incomplete or unsafe.")
            yield staged_bundle, digest.hexdigest(), size
        except BaseException:
            if staged_descriptor is not None:
                try:
                    os.close(staged_descriptor)
                except OSError:
                    pass
            raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if private_directory is not None:
            private_directory.cleanup()


def _target(value: str | None) -> tuple[str, str]:
    if not value:
        raise OffsiteError("AVTORINOK_OFFSITE_TARGET is required; no remote copy was attempted.")
    match = TARGET_RE.fullmatch(value)
    if match is None:
        raise OffsiteError("Target must use user@host:/absolute/path syntax.")
    remote, remote_dir = match.groups()
    normalized_path = remote_dir.rstrip("/") or "/"
    components = normalized_path[1:].split("/") if normalized_path != "/" else []
    if normalized_path == "/" or any(part in {"", ".", ".."} for part in components):
        raise OffsiteError("Remote path must be a safe non-root absolute path.")
    return remote, normalized_path


def _run_ssh(remote: str, command: str) -> subprocess.CompletedProcess[str]:
    if REMOTE_RE.fullmatch(remote) is None:
        raise OffsiteError("Target must use a safe user@host destination.")
    return subprocess.run(
        ["ssh", *SSH_OPTIONS, remote, command],
        text=True,
        capture_output=True,
        check=False,
    )


def _remote_preflight(remote: str, remote_dir: str, final_path: str) -> int:
    parent = remote_dir.rsplit("/", 1)[0] or "/"
    q_dir, q_parent, q_final = map(shlex.quote, (remote_dir, parent, final_path))
    command = f"""set -eu
command -v rsync >/dev/null
if command -v sha256sum >/dev/null 2>&1; then :; elif command -v shasum >/dev/null 2>&1; then :; else exit 127; fi
MV_HELP=$(mv --help 2>/dev/null || true)
printf '%s' "$MV_HELP" | grep -q -- '-T'
printf '%s' "$MV_HELP" | grep -q -- '-n'
if test -e {q_dir} || test -L {q_dir}; then
    test -d {q_dir} && test ! -L {q_dir} && test -w {q_dir}
    CHECK_PATH={q_dir}
else
    test -d {q_parent} && test -w {q_parent}
    CHECK_PATH={q_parent}
fi
test ! -e {q_final} && test ! -L {q_final}
df -Pk "$CHECK_PATH" | awk 'NR == 2 {{ print $4 }}'"""
    result = _run_ssh(remote, command)
    if result.returncode != 0:
        raise OffsiteError("Remote encrypted-bundle preflight failed; no remote files were created or changed.")
    value = result.stdout.strip()
    if not value.isdecimal():
        raise OffsiteError("Remote free-space check returned an invalid value.")
    return int(value)


def _transfer(remote: str, remote_dir: str, bundle: Path, digest: str) -> None:
    name = bundle.name
    final_path = f"{remote_dir}/{name}"
    staging_path = f"{remote_dir}/.{name}.incoming.{os.getpid()}"
    q_dir, q_stage, q_final = map(shlex.quote, (remote_dir, staging_path, final_path))
    setup = f"""set -eu
umask 077
if test -e {q_dir} || test -L {q_dir}; then
    test -d {q_dir} && test ! -L {q_dir} && test -w {q_dir}
else
    mkdir -p {q_dir}
fi
test ! -e {q_final} && test ! -L {q_final}
mkdir -m 700 {q_stage}"""
    result = _run_ssh(remote, setup)
    if result.returncode != 0:
        raise OffsiteError("Remote destination is unavailable or the encrypted bundle already exists.")

    transport = "ssh " + shlex.join(SSH_OPTIONS)
    rsync = subprocess.run(
        ["rsync", "-e", transport, "--archive", "--", str(bundle), f"{remote}:{staging_path}/"],
        text=True,
        capture_output=True,
        check=False,
    )
    if rsync.returncode != 0:
        raise OffsiteError("Encrypted bundle transfer failed; remote staging data was retained for inspection.")

    q_name = shlex.quote(name)
    q_digest = shlex.quote(digest)
    finalize = f"""set -eu
cd {q_stage}
if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\\n' {q_digest} {q_name} | sha256sum -c -
else
    printf '%s  %s\\n' {q_digest} {q_name} | shasum -a 256 -c -
fi
test ! -e {q_final} && test ! -L {q_final}
mv -T -n {q_stage}/{q_name} {q_final}
test ! -e {q_stage}/{q_name} && test ! -L {q_stage}/{q_name}
rmdir {q_stage}"""
    result = _run_ssh(remote, finalize)
    if result.returncode != 0:
        raise OffsiteError("Remote checksum verification failed or no-clobber publish failed; encrypted staging data was retained.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true", help="check the remote destination without writing to it")
    parser.add_argument("bundle", type=Path, help="age-encrypted snapshot bundle")
    args = parser.parse_args()
    try:
        remote, remote_dir = _target(os.environ.get("AVTORINOK_OFFSITE_TARGET"))
        if not shutil.which("ssh") or not shutil.which("rsync"):
            raise OffsiteError("ssh and rsync are required for off-host delivery.")
        with _bundle(args.bundle, stage_for_transfer=not args.preflight) as (
            bundle,
            digest,
            size_bytes,
        ):
            final_path = f"{remote_dir}/{bundle.name}"
            free_kib = _remote_preflight(remote, remote_dir, final_path)
            required_kib = ((size_bytes + 1023) // 1024) * 110 // 100
            if free_kib < required_kib:
                raise OffsiteError(
                    f"Remote target has insufficient free space: need at least {required_kib} KiB, have {free_kib} KiB."
                )
            if args.preflight:
                print(f"Encrypted bundle preflight OK: destination is writable and free ({remote}:{final_path})")
                return 0
            _transfer(remote, remote_dir, bundle, digest)
    except (OSError, OffsiteError, ValueError) as exc:
        print(f"Encrypted off-host delivery failed: {exc}", file=sys.stderr)
        return 1 if not str(exc).startswith("AVTORINOK_OFFSITE_TARGET is required") else 2
    print(f"Verified encrypted bundle copied: {remote}:{remote_dir}/{bundle.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
