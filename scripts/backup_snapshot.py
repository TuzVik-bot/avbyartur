"""Validation shared by the age backup bundle commands."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

BASE_FILES = (
    "database.dump",
    "private-media.tar.gz",
    "catalog.json",
    "catalog-coverage.json",
)
BATCH1_FILES = ("drom-batch-01-1-10-makes.csv", "drom-batch-01-1-10-makes-report.json")
BATCH2_FILES = (
    "drom-batch-02-10-makes.csv",
    "drom-batch-02-10-makes.json",
    "drom-batch-02-10-makes-report.json",
)
BATCH3_FILES = (
    "drom-batch-03-10-makes.csv",
    "drom-batch-03-10-makes.json",
    "drom-batch-03-10-makes-report.json",
)
BATCH4_9_FILES = tuple(
    f"drom-batch-{batch:02d}-10-makes{suffix}"
    for batch in range(4, 10)
    for suffix in (".csv", ".json", "-report.json")
)
LICENSED_FILES_BY_VERSION = {
    1: (),
    2: BATCH1_FILES,
    3: BATCH1_FILES + BATCH2_FILES,
    4: BATCH1_FILES + BATCH2_FILES + BATCH3_FILES,
    5: BATCH1_FILES + BATCH2_FILES + BATCH3_FILES + BATCH4_9_FILES,
}
ARCHIVE_FILE_NAMES = frozenset(
    BASE_FILES
    + BATCH1_FILES
    + BATCH2_FILES
    + BATCH3_FILES
    + BATCH4_9_FILES
    + ("manifest.txt", "SHA256SUMS")
)
SNAPSHOT_NAME_RE = re.compile(r"avtorinok-[0-9]{8}T[0-9]{6}Z(?:\.[A-Za-z0-9_.-]+)?\Z")

# Streaming keeps memory use bounded. These caps also limit disk use when a
# decrypted archive contains a forged, extremely large tar member.
MAX_FILE_BYTES = 250 * 1024**3
MAX_TOTAL_BYTES = 500 * 1024**3
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 16 * 1024**2
MAX_TAR_EXTENSION_BYTES = 64 * 1024
CHUNK_BYTES = 1024 * 1024


class SnapshotError(ValueError):
    """A snapshot or bundle violates the supported backup contract."""


@dataclass(frozen=True)
class SnapshotInfo:
    path: Path
    name: str
    version: int
    payload_files: tuple[str, ...]
    entries: tuple[str, ...]
    file_hashes: dict[str, str]
    total_bytes: int


def _regular_file(path: Path, description: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise SnapshotError(f"Missing or unreadable {description}.") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise SnapshotError(f"{description} must be a regular file, not a link or special file.")
    return metadata


def _read_limited(path: Path, description: str, limit: int) -> bytes:
    metadata = _regular_file(path, description)
    if metadata.st_size > limit:
        raise SnapshotError(f"{description} exceeds the supported file-size limit.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SnapshotError(f"Could not safely open {description}.") from exc
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise SnapshotError(f"{description} changed while it was being opened.")
        content = source.read(limit + 1)
        after = os.fstat(source.fileno())
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or len(content) != opened.st_size:
            raise SnapshotError(f"{description} changed while it was being read.")
        if len(content) > limit:
            raise SnapshotError(f"{description} exceeds the supported file-size limit.")
        return content


def _hash_file(path: Path, description: str) -> tuple[str, int, os.stat_result]:
    before = _regular_file(path, description)
    if before.st_size > MAX_FILE_BYTES:
        raise SnapshotError(f"{description} exceeds the supported file-size limit.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SnapshotError(f"Could not safely open {description}.") from exc
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise SnapshotError(f"{description} changed while it was being opened.")
        while chunk := source.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise SnapshotError(f"{description} exceeds the supported file-size limit.")
            digest.update(chunk)
        after = os.fstat(source.fileno())
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or size != opened.st_size:
            raise SnapshotError(f"{description} changed while it was being checked.")
    return digest.hexdigest(), size, before


def _expected_files(version: int) -> tuple[str, ...]:
    return BASE_FILES + LICENSED_FILES_BY_VERSION[version]


def _manifest_version_and_files(content: bytes) -> tuple[int, tuple[str, ...]]:
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise SnapshotError("Snapshot manifest is not valid ASCII.") from exc
    versions = [line.partition("=")[2] for line in lines if line.startswith("format_version=")]
    includes = [line.partition("=")[2] for line in lines if line.startswith("includes=")]
    if len(versions) != 1 or len(includes) != 1 or versions[0] not in {"1", "2", "3", "4", "5"}:
        raise SnapshotError("Unsupported snapshot manifest; expected format version 1 through 5.")
    version = int(versions[0])
    files = _expected_files(version)
    if includes[0] != ",".join(files):
        raise SnapshotError("Snapshot manifest file set does not match its declared version.")
    return version, files


def _parse_checksums(content: bytes, required_names: set[str]) -> dict[str, str]:
    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise SnapshotError("Snapshot checksum manifest is not valid ASCII.") from exc
    checksums: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([A-Za-z0-9_.-]+)", line, flags=re.ASCII)
        if match is None:
            raise SnapshotError("Invalid snapshot checksum manifest.")
        digest, filename = match.groups()
        if filename not in required_names or filename in checksums:
            raise SnapshotError("Invalid snapshot checksum manifest file set.")
        checksums[filename] = digest.lower()
    if set(checksums) != required_names:
        raise SnapshotError("Snapshot checksum manifest is missing or has extra entries.")
    return checksums


def validate_snapshot(snapshot_path: str | os.PathLike[str]) -> SnapshotInfo:
    """Validate a complete v1-v5 snapshot and return the checked file hashes."""
    requested = Path(snapshot_path).expanduser()
    try:
        root_metadata = requested.lstat()
    except OSError as exc:
        raise SnapshotError("Snapshot directory is missing or unreadable.") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise SnapshotError("Snapshot path must be a real directory, not a symlink.")
    if SNAPSHOT_NAME_RE.fullmatch(requested.name) is None:
        raise SnapshotError("Snapshot directory name is not a completed timestamped backup.")
    root = requested.resolve(strict=True)

    manifest = _read_limited(root / "manifest.txt", "snapshot manifest", 1024 * 1024)
    version, payload_files = _manifest_version_and_files(manifest)
    names = payload_files + ("manifest.txt", "SHA256SUMS")
    if {entry.name for entry in root.iterdir()} != set(names):
        raise SnapshotError("Snapshot has missing or unexpected top-level entries.")

    required_checksums = set(payload_files + ("manifest.txt",))
    checksum_bytes = _read_limited(root / "SHA256SUMS", "snapshot checksum manifest", 1024 * 1024)
    expected_hashes = _parse_checksums(checksum_bytes, required_checksums)
    parsed_hashes = {
        "manifest.txt": hashlib.sha256(manifest).hexdigest(),
        "SHA256SUMS": hashlib.sha256(checksum_bytes).hexdigest(),
    }

    file_hashes: dict[str, str] = {}
    total_bytes = 0
    for filename in payload_files + ("manifest.txt", "SHA256SUMS"):
        digest, size, _ = _hash_file(root / filename, f"snapshot file {filename}")
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise SnapshotError("Snapshot exceeds the supported total-size limit.")
        file_hashes[filename] = digest
        if filename in parsed_hashes and parsed_hashes[filename] != digest:
            raise SnapshotError(f"Snapshot {filename} changed after it was read.")
        if filename in expected_hashes and expected_hashes[filename] != digest:
            raise SnapshotError(f"Snapshot checksum verification failed for {filename}.")

    return SnapshotInfo(
        path=root,
        name=requested.name,
        version=version,
        payload_files=payload_files,
        entries=names,
        file_hashes=file_hashes,
        total_bytes=total_bytes,
    )
