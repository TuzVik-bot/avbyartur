"""Validate and stream an Avtorinok snapshot into an age-encrypted tar bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from backup_snapshot import CHUNK_BYTES, SnapshotError, SnapshotInfo, validate_snapshot


class _DigestingReader:
    def __init__(self, source, expected_size: int):
        self.source = source
        self.expected_size = expected_size
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = CHUNK_BYTES
        chunk = self.source.read(size)
        self.bytes_read += len(chunk)
        self.digest.update(chunk)
        return chunk


def _age_binary() -> str:
    binary = shutil.which("age")
    if not binary:
        raise SnapshotError("The age executable is required; install it or add it to PATH.")
    return binary


def _check_output_parent(path: Path, snapshot: SnapshotInfo) -> None:
    try:
        metadata = path.parent.lstat()
    except OSError as exc:
        raise SnapshotError("Bundle output parent must already exist.") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise SnapshotError("Bundle output parent must be a real directory, not a symlink.")
    parent = path.parent.resolve(strict=True)
    try:
        parent.relative_to(snapshot.path)
    except ValueError:
        pass
    else:
        raise SnapshotError("Bundle output must be outside the source snapshot directory.")
    if path.exists() or path.is_symlink():
        raise SnapshotError("Bundle output already exists; refusing to overwrite it.")


def _add_snapshot_file(archive: tarfile.TarFile, snapshot: SnapshotInfo, filename: str) -> None:
    path = snapshot.path / filename
    try:
        before = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise SnapshotError(f"Could not safely open snapshot file {filename}.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise SnapshotError(f"Snapshot file {filename} changed while it was being opened.")
        if opened.st_size > snapshot.total_bytes:
            raise SnapshotError(f"Snapshot file {filename} changed size while being packaged.")
        info = tarfile.TarInfo(f"{snapshot.name}/{filename}")
        info.type = tarfile.REGTYPE
        info.mode = 0o600
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        info.size = opened.st_size
        reader = _DigestingReader(source, opened.st_size)
        archive.addfile(info, reader)
        after = os.fstat(source.fileno())
        if reader.bytes_read != opened.st_size or reader.digest.hexdigest() != snapshot.file_hashes[filename]:
            raise SnapshotError(f"Snapshot file {filename} changed while it was being packaged.")
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise SnapshotError(f"Snapshot file {filename} changed while it was being packaged.")


def encrypt_snapshot(snapshot_path: Path, recipient: str, output_path: Path | None = None) -> Path:
    snapshot = validate_snapshot(snapshot_path)
    output = output_path or snapshot.path.with_name(f"{snapshot.name}.tar.age")
    output = output.expanduser().absolute()
    _check_output_parent(output, snapshot)

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".backup-encrypt-", suffix=".tmp", dir=output.parent
        )
    except OSError as exc:
        raise SnapshotError("Could not create a protected temporary bundle file.") from exc
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as encrypted_output:
            try:
                process = subprocess.Popen(
                    [_age_binary(), "--encrypt", "--recipient", recipient],
                    stdin=subprocess.PIPE,
                    stdout=encrypted_output,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                raise SnapshotError("Could not start age encryption.") from exc
            try:
                assert process.stdin is not None
                with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                    root = tarfile.TarInfo(snapshot.name + "/")
                    root.type = tarfile.DIRTYPE
                    root.mode = 0o700
                    root.uid = 0
                    root.gid = 0
                    root.uname = ""
                    root.gname = ""
                    root.mtime = 0
                    archive.addfile(root)
                    for filename in snapshot.entries:
                        _add_snapshot_file(archive, snapshot, filename)
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            except (BrokenPipeError, OSError, tarfile.TarError, SnapshotError) as exc:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                process.wait()
                if process.stderr:
                    process.stderr.read()
                if isinstance(exc, SnapshotError):
                    raise
                raise SnapshotError("Could not stream the snapshot into age encryption.") from exc

            encrypted_output.flush()
            os.fsync(encrypted_output.fileno())
            stderr = process.stderr.read() if process.stderr else b""
            status = process.wait()
            if status != 0:
                raise SnapshotError("age encryption failed; check the recipient key and retry.")
            del stderr
        try:
            os.link(temporary_path, output)
        except FileExistsError as exc:
            raise SnapshotError("Bundle output already exists; refusing to overwrite it.") from exc
        except OSError as exc:
            raise SnapshotError("Could not publish the encrypted bundle without overwriting a file.") from exc
        os.chmod(output, 0o600, follow_symlinks=False)
        return output
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="completed avtorinok-YYYYMMDDTHHMMSSZ snapshot directory")
    parser.add_argument("--recipient", required=True, help="age public recipient (age1...)")
    parser.add_argument("--output", type=Path, help="encrypted bundle path; defaults beside the snapshot")
    args = parser.parse_args()
    try:
        output = encrypt_snapshot(args.snapshot, args.recipient, args.output)
    except (OSError, SnapshotError, ValueError) as exc:
        print(f"Backup encryption failed: {exc}", file=sys.stderr)
        return 1
    print(f"Encrypted snapshot bundle created: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
