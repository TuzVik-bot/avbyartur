"""Decrypt an age bundle into a validated, restore-compatible snapshot directory."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from backup_snapshot import (
    ARCHIVE_FILE_NAMES,
    CHUNK_BYTES,
    MAX_ARCHIVE_BYTES,
    MAX_FILE_BYTES,
    MAX_TAR_EXTENSION_BYTES,
    MAX_TOTAL_BYTES,
    SNAPSHOT_NAME_RE,
    SnapshotError,
    SnapshotInfo,
    validate_snapshot,
)


class _LimitedReader:
    def __init__(self, source, limit: int):
        self.source = source
        self.limit = limit
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = CHUNK_BYTES
        chunk = self.source.read(size)
        self.bytes_read += len(chunk)
        if self.bytes_read > self.limit:
            raise SnapshotError("Decrypted archive exceeds the supported total-size limit.")
        return chunk


class _PrefixReader:
    """Replay a bounded prefix while preserving the wrapped stream position."""

    def __init__(self, source, prefix: bytes):
        self.source = source
        self.prefix = prefix
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise SnapshotError("Unsafe archive: unbounded metadata read requested.")
        remaining = self.prefix[self.offset :]
        if not remaining:
            return self.source.read(size)
        prefix = remaining[:size]
        self.offset += len(prefix)
        if len(prefix) == size:
            return prefix
        return prefix + self.source.read(size - len(prefix))

    def tell(self) -> int:
        return self.source.tell() - (len(self.prefix) - self.offset)


def _validate_pax_metadata(content: bytes) -> None:
    """Reject sparse metadata and oversized file sizes before tarfile handles it."""

    position = 0
    while position < len(content):
        if content[position] == 0:
            if any(content[position:]):
                raise SnapshotError("Unsafe archive: malformed PAX metadata.")
            return
        separator = content.find(b" ", position)
        if separator < 0:
            raise SnapshotError("Unsafe archive: malformed PAX metadata.")
        length_text = content[position:separator]
        if not length_text.isdigit() or len(length_text) > 6:
            raise SnapshotError("Unsafe archive: malformed PAX metadata.")
        record_length = int(length_text)
        record_end = position + record_length
        if (
            record_length < separator - position + 4
            or record_end > len(content)
            or content[record_end - 1 : record_end] != b"\n"
        ):
            raise SnapshotError("Unsafe archive: malformed PAX metadata.")
        field = content[separator + 1 : record_end - 1]
        key, equals, value = field.partition(b"=")
        if not key or equals != b"=":
            raise SnapshotError("Unsafe archive: malformed PAX metadata.")
        if key.startswith(b"GNU.sparse"):
            raise SnapshotError("Unsafe archive: sparse PAX metadata is not supported.")
        if key == b"size":
            if not value.isdigit() or len(value) > 16:
                raise SnapshotError("Unsafe archive: invalid PAX member size.")
            member_size = int(value)
            if member_size > MAX_FILE_BYTES:
                raise SnapshotError("Archive file exceeds the supported file-size limit.")
        position = record_end


class _BoundedTarInfo(tarfile.TarInfo):
    """Bound extension parsing before tarfile reads extension-controlled data."""

    def _proc_member(self, archive):
        unsupported_extensions = {
            getattr(tarfile, "XGLTYPE", b"g"),
            getattr(tarfile, "SOLARIS_XHDTYPE", b"X"),
            getattr(tarfile, "GNUTYPE_LONGNAME", b"L"),
            getattr(tarfile, "GNUTYPE_LONGLINK", b"K"),
            getattr(tarfile, "GNUTYPE_SPARSE", b"S"),
        }
        if self.type in unsupported_extensions:
            raise SnapshotError("Unsafe archive: global and GNU extension headers are not supported.")
        return super()._proc_member(archive)

    def _proc_pax(self, archive):
        if self.type != getattr(tarfile, "XHDTYPE", b"x"):
            raise SnapshotError("Unsafe archive: unsupported PAX extension header.")
        if self.size < 0 or self.size > MAX_TAR_EXTENSION_BYTES:
            raise SnapshotError("Unsafe archive: PAX metadata exceeds the supported size limit.")

        original = archive.fileobj
        padded_size = self._block(self.size)
        extension = original.read(padded_size)
        if len(extension) != padded_size:
            raise SnapshotError("Unsafe archive: truncated PAX extension header.")
        _validate_pax_metadata(extension[: self.size])

        archive.fileobj = _PrefixReader(original, extension)
        try:
            member = super()._proc_pax(archive)
        finally:
            archive.fileobj = original
        if member is not None and (member.size < 0 or member.size > MAX_FILE_BYTES):
            raise SnapshotError("Archive file exceeds the supported file-size limit.")
        return member


def _age_binary() -> str:
    binary = shutil.which("age")
    if not binary:
        raise SnapshotError("The age executable is required; install it or add it to PATH.")
    return binary


def _check_bundle_and_identity(bundle: Path, identity: Path) -> None:
    try:
        bundle_stat = bundle.lstat()
    except OSError as exc:
        raise SnapshotError("Encrypted bundle is missing or unreadable.") from exc
    if not stat.S_ISREG(bundle_stat.st_mode):
        raise SnapshotError("Encrypted bundle must be a regular file, not a link or special file.")
    max_ciphertext_bytes = MAX_ARCHIVE_BYTES + MAX_TOTAL_BYTES // 100 + 1024 * 1024
    if bundle_stat.st_size <= 0 or bundle_stat.st_size > max_ciphertext_bytes:
        raise SnapshotError("Encrypted bundle is empty or exceeds the supported size limit.")

    try:
        identity_stat = identity.lstat()
    except OSError as exc:
        raise SnapshotError("Age identity file is missing or unreadable.") from exc
    if not stat.S_ISREG(identity_stat.st_mode) or stat.S_IMODE(identity_stat.st_mode) & 0o077:
        raise SnapshotError("Age identity must be a regular file with permissions 600 or stricter.")


def _write_member(archive: tarfile.TarFile, member: tarfile.TarInfo, destination: Path) -> None:
    if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
        raise SnapshotError("Unsafe archive entry: only ordinary snapshot files are accepted.")
    if member.size < 0 or member.size > MAX_FILE_BYTES:
        raise SnapshotError("Archive file exceeds the supported file-size limit.")
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except OSError as exc:
        raise SnapshotError("Unsafe or duplicate archive entry; no files were published.") from exc
    os.fchmod(descriptor, 0o600)
    source = archive.extractfile(member)
    if source is None:
        os.close(descriptor)
        destination.unlink(missing_ok=True)
        raise SnapshotError("Archive file could not be read safely.")
    copied = 0
    try:
        with os.fdopen(descriptor, "wb") as target, source:
            while copied < member.size:
                chunk = source.read(min(CHUNK_BYTES, member.size - copied))
                if not chunk:
                    raise SnapshotError("Encrypted archive ended before a file was complete.")
                target.write(chunk)
                copied += len(chunk)
            target.flush()
            os.fsync(target.fileno())
        if copied != member.size:
            raise SnapshotError("Encrypted archive file size did not match its header.")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _read_archive(process: subprocess.Popen[bytes], output_name: str, staging: Path) -> tuple[Path, int]:
    assert process.stdout is not None
    limited = _LimitedReader(process.stdout, MAX_ARCHIVE_BYTES)
    root_name: str | None = None
    snapshot_root: Path | None = None
    seen_files: set[str] = set()
    member_count = 0
    total_file_bytes = 0
    try:
        with tarfile.open(fileobj=limited, mode="r|", tarinfo=_BoundedTarInfo) as archive:
            for member in archive:
                member_count += 1
                if member_count > len(ARCHIVE_FILE_NAMES) + 1:
                    raise SnapshotError("Unsafe archive: too many entries.")
                if root_name is None:
                    candidate = member.name.removesuffix("/")
                    if (
                        SNAPSHOT_NAME_RE.fullmatch(candidate) is None
                        or candidate != output_name
                        or member.type != tarfile.DIRTYPE
                        or member.size != 0
                        or member.name not in {candidate, candidate + "/"}
                    ):
                        raise SnapshotError("Unsafe archive root directory.")
                    root_name = candidate
                    snapshot_root = staging / candidate
                    snapshot_root.mkdir(mode=0o700)
                    continue

                prefix = root_name + "/"
                if not member.name.startswith(prefix):
                    raise SnapshotError("Unsafe archive entry: path is outside the snapshot directory.")
                filename = member.name[len(prefix) :]
                if not filename or "/" in filename or filename not in ARCHIVE_FILE_NAMES:
                    raise SnapshotError("Unsafe archive entry: path traversal or unexpected file.")
                if filename in seen_files:
                    raise SnapshotError("Unsafe archive entry: duplicate snapshot file.")
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
                    raise SnapshotError("Unsafe archive entry: links and special files are not accepted.")
                if member.size < 0 or member.size > MAX_FILE_BYTES:
                    raise SnapshotError("Archive file exceeds the supported file-size limit.")
                total_file_bytes += member.size
                if total_file_bytes > MAX_TOTAL_BYTES:
                    raise SnapshotError("Decrypted archive exceeds the supported total-size limit.")
                assert snapshot_root is not None
                _write_member(archive, member, snapshot_root / filename)
                seen_files.add(filename)

            tar_stream = archive.fileobj
            buffered = getattr(tar_stream, "buf", b"")
            if buffered and any(buffered):
                raise SnapshotError("Unsafe archive: unexpected data follows its end marker.")

        while chunk := limited.read(CHUNK_BYTES):
            if any(chunk):
                raise SnapshotError("Unsafe archive: unexpected data follows its end marker.")
        if root_name is None or snapshot_root is None:
            raise SnapshotError("Encrypted bundle does not contain a snapshot archive.")
        return snapshot_root, total_file_bytes
    except (OSError, tarfile.TarError) as exc:
        raise SnapshotError("Encrypted bundle could not be read as a safe tar archive.") from exc


def _publish_snapshot(staged_snapshot: Path, final_path: Path, snapshot: SnapshotInfo) -> Path:
    created_directory = False
    published = False
    published_files: list[Path] = []
    try:
        os.mkdir(final_path, 0o700)
        created_directory = True
        os.chmod(final_path, 0o700, follow_symlinks=False)
        for filename in snapshot.entries:
            source = staged_snapshot / filename
            target = final_path / filename
            os.link(source, target, follow_symlinks=False)
            published_files.append(target)
        directory_fd = os.open(final_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        published = True
        return final_path
    except FileExistsError as exc:
        raise SnapshotError("Restore output already exists; refusing to overwrite it.") from exc
    except OSError as exc:
        raise SnapshotError("Could not publish the validated snapshot without overwriting files.") from exc
    finally:
        if created_directory and not published:
            for path in published_files:
                path.unlink(missing_ok=True)
            final_path.rmdir()


def decrypt_bundle(bundle_path: Path, identity_path: Path, output_path: Path) -> Path:
    bundle = bundle_path.expanduser()
    identity = identity_path.expanduser()
    output = output_path.expanduser().absolute()
    _check_bundle_and_identity(bundle, identity)
    try:
        parent_stat = output.parent.lstat()
    except OSError as exc:
        raise SnapshotError("Restore output parent must already exist.") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise SnapshotError("Restore output parent must be a real directory, not a symlink.")
    if output.exists() or output.is_symlink():
        raise SnapshotError("Restore output already exists; refusing to overwrite it.")

    try:
        staging = Path(tempfile.mkdtemp(prefix=".avtorinok-restore.incoming-", dir=output.parent))
        os.chmod(staging, 0o700, follow_symlinks=False)
    except OSError as exc:
        raise SnapshotError("Could not create a protected temporary restore directory.") from exc
    try:
        try:
            process = subprocess.Popen(
                [_age_binary(), "--decrypt", "--identity", str(identity), str(bundle)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise SnapshotError("Could not start age decryption.") from exc

        try:
            staged_snapshot, _ = _read_archive(process, output.name, staging)
            stderr = process.stderr.read() if process.stderr else b""
            status = process.wait()
            if status != 0:
                raise SnapshotError("Age decryption failed; verify the identity and bundle integrity.")
            del stderr
        except BaseException as exc:
            if process.poll() is None:
                if process.stdout and not process.stdout.closed:
                    process.stdout.close()
                process.wait()
            stderr = process.stderr.read() if process.stderr else b""
            if process.returncode not in (None, 0):
                raise SnapshotError("Age decryption failed; verify the identity and bundle integrity.") from exc
            del stderr
            raise

        snapshot = validate_snapshot(staged_snapshot)
        if snapshot.name != output.name:
            raise SnapshotError("Snapshot directory name does not match the archive destination.")
        return _publish_snapshot(staged_snapshot, output, snapshot)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="encrypted .tar.age backup bundle")
    parser.add_argument("--identity", required=True, type=Path, help="age private identity file (mode 600 or stricter)")
    parser.add_argument("--output", required=True, type=Path, help="new snapshot directory; must not exist")
    args = parser.parse_args()
    try:
        output = decrypt_bundle(args.bundle, args.identity, args.output)
    except (OSError, SnapshotError, ValueError) as exc:
        print(f"Backup decryption failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated backup snapshot restored to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
