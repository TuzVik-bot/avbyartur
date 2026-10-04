import hashlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ENCRYPT = ROOT / "scripts" / "backup-encrypt.py"
DECRYPT = ROOT / "scripts" / "backup-decrypt.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import backup_snapshot

_decrypt_spec = importlib.util.spec_from_file_location("backup_decrypt", DECRYPT)
assert _decrypt_spec and _decrypt_spec.loader
backup_decrypt = importlib.util.module_from_spec(_decrypt_spec)
_decrypt_spec.loader.exec_module(backup_decrypt)

AGE = shutil.which("age")
AGE_KEYGEN = shutil.which("age-keygen")

BASE_FILES = (
    "database.dump",
    "private-media.tar.gz",
    "catalog.json",
    "catalog-coverage.json",
)
BATCH1 = ("drom-batch-01-1-10-makes.csv", "drom-batch-01-1-10-makes-report.json")
BATCH2 = (
    "drom-batch-02-10-makes.csv",
    "drom-batch-02-10-makes.json",
    "drom-batch-02-10-makes-report.json",
)
BATCH3 = (
    "drom-batch-03-10-makes.csv",
    "drom-batch-03-10-makes.json",
    "drom-batch-03-10-makes-report.json",
)
BATCH4_9 = tuple(
    f"drom-batch-{batch:02d}-10-makes{suffix}"
    for batch in range(4, 10)
    for suffix in (".csv", ".json", "-report.json")
)
LICENSED_BY_VERSION = {
    1: (),
    2: BATCH1,
    3: BATCH1 + BATCH2,
    4: BATCH1 + BATCH2 + BATCH3,
    5: BATCH1 + BATCH2 + BATCH3 + BATCH4_9,
}


@unittest.skipUnless(AGE and AGE_KEYGEN, "real age and age-keygen binaries are required")
class BackupEncryptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key_dir = tempfile.TemporaryDirectory()
        cls.identity = Path(cls.key_dir.name) / "recipient-identity.txt"
        subprocess.run([AGE_KEYGEN, "-o", str(cls.identity)], check=True, capture_output=True)
        cls.identity.chmod(0o600)
        cls.recipient = subprocess.run(
            [AGE_KEYGEN, "-y", str(cls.identity)], check=True, capture_output=True, text=True
        ).stdout.strip()
        cls.other_identity = Path(cls.key_dir.name) / "different-identity.txt"
        subprocess.run([AGE_KEYGEN, "-o", str(cls.other_identity)], check=True, capture_output=True)
        cls.other_identity.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls.key_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backup = self.root / "avtorinok-20261001T120000Z"
        self.backup.mkdir(mode=0o700)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{Path(AGE).parent}{os.pathsep}{self.env.get('PATH', '')}"

    def write_snapshot(self, version=5):
        licensed = LICENSED_BY_VERSION[version]
        payloads = BASE_FILES + licensed
        for filename in payloads:
            (self.backup / filename).write_bytes(f"test snapshot payload: {filename}\n".encode())
        manifest = [
            f"format_version={version}",
            "created_at_utc=20261001T120000Z",
            "includes=" + ",".join(payloads),
        ]
        if version > 1:
            manifest.append("licensed_data_classification=proprietary-permissioned")
        (self.backup / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="ascii")
        checksum_names = payloads + ("manifest.txt",)
        sums = [
            f"{hashlib.sha256((self.backup / name).read_bytes()).hexdigest()}  {name}"
            for name in checksum_names
        ]
        (self.backup / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="ascii")
        for path in self.backup.iterdir():
            path.chmod(0o600)
        return set(checksum_names + ("SHA256SUMS",))

    def encrypt(self, backup=None, output=None, recipient=None):
        backup = backup or self.backup
        output = output or self.root / f"{backup.name}.tar.age"
        return subprocess.run(
            [
                sys.executable,
                str(ENCRYPT),
                str(backup),
                "--recipient",
                recipient or self.recipient,
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        ), output

    def decrypt(self, bundle, identity=None, output=None):
        output = output or self.root / self.backup.name
        return subprocess.run(
            [
                sys.executable,
                str(DECRYPT),
                str(bundle),
                "--identity",
                str(identity or self.identity),
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            env=self.env,
            check=False,
        ), output

    def make_encrypted_tar(self, bundle, members):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, kind, body, linkname in members:
                info = tarfile.TarInfo(name)
                info.mode = 0o600
                if kind == "directory":
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                elif kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = linkname
                    archive.addfile(info)
                else:
                    info.size = len(body)
                    archive.addfile(info, io.BytesIO(body))
        with bundle.open("wb") as encrypted_output:
            subprocess.run(
                [AGE, "--encrypt", "--recipient", self.recipient],
                input=stream.getvalue(),
                stdout=encrypted_output,
                stderr=subprocess.PIPE,
                check=True,
            )
        bundle.chmod(0o600)

    def test_encrypts_and_round_trips_all_supported_snapshot_versions(self):
        for version in range(1, 6):
            with self.subTest(format_version=version):
                if self.backup.exists():
                    shutil.rmtree(self.backup)
                self.backup.mkdir(mode=0o700)
                original_files = self.write_snapshot(version)
                bundle = self.root / f"{self.backup.name}.v{version}.tar.age"
                encrypted, bundle = self.encrypt(output=bundle)
                self.assertEqual(encrypted.returncode, 0, encrypted.stderr)
                self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o600)
                self.assertNotIn(b"test snapshot payload", bundle.read_bytes())

                restored = self.root / f"restored-v{version}" / self.backup.name
                restored.parent.mkdir(mode=0o700)
                decrypted, output = self.decrypt(bundle, output=restored)
                self.assertEqual(decrypted.returncode, 0, decrypted.stderr)
                self.assertEqual(output, restored)
                self.assertEqual({p.name for p in restored.iterdir()}, original_files)
                self.assertEqual(stat.S_IMODE(restored.stat().st_mode), 0o700)
                for filename in original_files:
                    path = restored / filename
                    self.assertTrue(stat.S_ISREG(path.lstat().st_mode))
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertEqual(path.read_bytes(), (self.backup / filename).read_bytes())
                shutil.rmtree(self.backup)

    def test_wrong_identity_does_not_leave_a_restored_snapshot(self):
        self.write_snapshot(2)
        encrypted, bundle = self.encrypt()
        self.assertEqual(encrypted.returncode, 0, encrypted.stderr)

        restored_parent = self.root / "wrong-key-restore"
        restored_parent.mkdir(mode=0o700)
        restored = restored_parent / self.backup.name
        decrypted, _ = self.decrypt(bundle, identity=self.other_identity, output=restored)

        self.assertNotEqual(decrypted.returncode, 0)
        self.assertIn("age decryption failed", decrypted.stderr.lower())
        self.assertFalse(restored.exists())
        self.assertFalse(any(self.root.glob(".avtorinok-*.incoming-*")))

    def test_tampered_ciphertext_does_not_leave_a_restored_snapshot(self):
        self.write_snapshot(3)
        encrypted, bundle = self.encrypt()
        self.assertEqual(encrypted.returncode, 0, encrypted.stderr)
        data = bytearray(bundle.read_bytes())
        data[len(data) // 2] ^= 0x01
        bundle.write_bytes(data)

        restored_parent = self.root / "tampered-restore"
        restored_parent.mkdir(mode=0o700)
        restored = restored_parent / self.backup.name
        decrypted, _ = self.decrypt(bundle, output=restored)

        self.assertNotEqual(decrypted.returncode, 0)
        self.assertIn("age decryption failed", decrypted.stderr.lower())
        self.assertFalse(restored.exists())
        self.assertFalse(any(self.root.glob(".avtorinok-*.incoming-*")))

    def test_decrypt_rejects_path_traversal_and_symlink_entries_before_output(self):
        root_name = self.backup.name
        cases = {
            "traversal": [("../escaped.txt", "file", b"escaped", "")],
            "symlink": [(f"{root_name}/private-link", "symlink", b"", "../../outside")],
            "unexpected": [(f"{root_name}/unexpected.txt", "file", b"unexpected", "")],
        }
        for label, malicious_members in cases.items():
            with self.subTest(entry=label):
                bundle = self.root / f"malicious-{label}.tar.age"
                self.make_encrypted_tar(
                    bundle,
                    [(root_name, "directory", b"", "")] + malicious_members,
                )
                parent = self.root / f"restore-{label}"
                parent.mkdir(mode=0o700)
                destination = parent / root_name
                decrypted, _ = self.decrypt(bundle, output=destination)

                self.assertNotEqual(decrypted.returncode, 0)
                self.assertIn("unsafe archive", decrypted.stderr.lower())
                self.assertFalse(destination.exists())
                self.assertFalse((parent / "escaped.txt").exists())
                self.assertFalse(any(self.root.glob(".avtorinok-*.incoming-*")))

    def test_encryption_rejects_a_changed_checksum_before_creating_bundle(self):
        self.write_snapshot(2)
        (self.backup / "database.dump").write_text("changed after manifest\n", encoding="ascii")

        encrypted, bundle = self.encrypt()

        self.assertNotEqual(encrypted.returncode, 0)
        self.assertIn("checksum", encrypted.stderr.lower())
        self.assertFalse(bundle.exists())

    def test_encrypt_does_not_overwrite_an_existing_bundle(self):
        self.write_snapshot(1)
        existing = self.root / f"{self.backup.name}.tar.age"
        existing.write_bytes(b"keep-existing-bundle")
        existing.chmod(0o600)

        encrypted, _ = self.encrypt(output=existing)

        self.assertNotEqual(encrypted.returncode, 0)
        self.assertIn("already exists", encrypted.stderr.lower())
        self.assertEqual(existing.read_bytes(), b"keep-existing-bundle")


def _write_snapshot_for_validation_race(snapshot: Path, version: int = 5) -> tuple[str, ...]:
    payloads = BASE_FILES + LICENSED_BY_VERSION[version]
    for filename in payloads:
        (snapshot / filename).write_bytes(f"test snapshot payload: {filename}\n".encode())
    manifest = [
        f"format_version={version}",
        "created_at_utc=20261001T120000Z",
        "includes=" + ",".join(payloads),
    ]
    if version > 1:
        manifest.append("licensed_data_classification=proprietary-permissioned")
    (snapshot / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="ascii")
    checksum_names = payloads + ("manifest.txt",)
    checksum_bytes = "\n".join(
        f"{hashlib.sha256((snapshot / name).read_bytes()).hexdigest()}  {name}"
        for name in checksum_names
    ) + "\n"
    (snapshot / "SHA256SUMS").write_text(checksum_bytes, encoding="ascii")
    for path in snapshot.iterdir():
        path.chmod(0o600)
    return payloads


class SnapshotValidationRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = Path(self.temp.name) / "avtorinok-20261001T120000Z"
        self.snapshot.mkdir(mode=0o700)
        _write_snapshot_for_validation_race(self.snapshot)

    def test_manifest_bytes_cannot_change_after_the_parsed_read(self):
        original_read = backup_snapshot._read_limited
        v5_payloads = BASE_FILES + LICENSED_BY_VERSION[5]

        def replace_manifest_after_read(path, description, limit):
            content = original_read(path, description, limit)
            if description == "snapshot manifest":
                replacement = (
                    "format_version=1\n"
                    "created_at_utc=20261001T120000Z\n"
                    "includes=" + ",".join(BASE_FILES) + "\n"
                ).encode("ascii")
                (self.snapshot / "manifest.txt").write_bytes(replacement)
                names = v5_payloads + ("manifest.txt",)
                sums = "\n".join(
                    f"{hashlib.sha256((self.snapshot / name).read_bytes()).hexdigest()}  {name}"
                    for name in names
                ) + "\n"
                (self.snapshot / "SHA256SUMS").write_text(sums, encoding="ascii")
            return content

        with mock.patch.object(
            backup_snapshot, "_read_limited", side_effect=replace_manifest_after_read
        ), self.assertRaises(backup_snapshot.SnapshotError):
            backup_snapshot.validate_snapshot(self.snapshot)

    def test_checksum_bytes_cannot_change_after_the_parsed_read(self):
        original_read = backup_snapshot._read_limited

        def replace_checksum_after_read(path, description, limit):
            content = original_read(path, description, limit)
            if description == "snapshot checksum manifest":
                Path(path).write_bytes(content.replace(b"\n", b"\r\n"))
            return content

        with mock.patch.object(
            backup_snapshot, "_read_limited", side_effect=replace_checksum_after_read
        ), self.assertRaises(backup_snapshot.SnapshotError):
            backup_snapshot.validate_snapshot(self.snapshot)

    def test_limited_manifest_read_detects_mutation_on_its_open_descriptor(self):
        manifest = self.snapshot / "manifest.txt"
        original_fdopen = backup_snapshot.os.fdopen

        class MutatingReader:
            def __init__(self, descriptor, mode):
                self.source = original_fdopen(descriptor, mode)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self.source.close()

            def fileno(self):
                return self.source.fileno()

            def read(self, size):
                content = self.source.read(size)
                with manifest.open("ab") as changed:
                    changed.write(b"x")
                return content

        with mock.patch.object(backup_snapshot.os, "fdopen", side_effect=MutatingReader), self.assertRaises(
            backup_snapshot.SnapshotError
        ):
            backup_snapshot._read_limited(manifest, "snapshot manifest", 1024 * 1024)


class TarMetadataSafetyTests(unittest.TestCase):
    MAX_METADATA_BYTES = 64 * 1024
    SNAPSHOT_NAME = "avtorinok-20261001T120000Z"

    class _Process:
        def __init__(self, stdout):
            self.stdout = stdout

    class _CountingTarReader:
        def __init__(self, prefix: bytes, metadata_bytes: int):
            self.prefix = prefix
            self.position = 0
            self.metadata_remaining = metadata_bytes
            self.metadata_bytes_read = 0

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                size = 1024 * 1024
            if self.position < len(self.prefix):
                chunk = self.prefix[self.position : self.position + size]
                self.position += len(chunk)
                return chunk
            count = min(size, self.metadata_remaining)
            self.metadata_remaining -= count
            self.metadata_bytes_read += count
            return b"x" * count

    def _root_header(self) -> bytes:
        root = tarfile.TarInfo(self.SNAPSHOT_NAME + "/")
        root.type = tarfile.DIRTYPE
        return root.tobuf(format=tarfile.PAX_FORMAT)

    def test_pax_and_gnu_extension_headers_are_rejected_before_payload_reads(self):
        extension_types = (
            tarfile.XHDTYPE,
            tarfile.XGLTYPE,
            tarfile.GNUTYPE_LONGNAME,
            tarfile.GNUTYPE_LONGLINK,
            tarfile.GNUTYPE_SPARSE,
        )
        for extension_type in extension_types:
            with self.subTest(extension_type=extension_type):
                malicious = tarfile.TarInfo("PaxHeaders.0/manifest.txt")
                malicious.type = extension_type
                malicious.size = self.MAX_METADATA_BYTES + 1
                reader = self._CountingTarReader(
                    self._root_header() + malicious.tobuf(format=tarfile.PAX_FORMAT),
                    malicious.size,
                )
                with tempfile.TemporaryDirectory() as temp, self.assertRaises(
                    backup_snapshot.SnapshotError
                ):
                    backup_decrypt._read_archive(
                        self._Process(reader), self.SNAPSHOT_NAME, Path(temp)
                    )
                self.assertEqual(reader.metadata_bytes_read, 0)

    def test_small_pax_header_still_round_trips_through_archive_reader(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
            root = tarfile.TarInfo(self.SNAPSHOT_NAME + "/")
            root.type = tarfile.DIRTYPE
            archive.addfile(root)
            member = tarfile.TarInfo(self.SNAPSHOT_NAME + "/manifest.txt")
            member.size = 1
            member.pax_headers = {"comment": "small safe metadata"}
            archive.addfile(member, io.BytesIO(b"x"))
        with tempfile.TemporaryDirectory() as temp:
            restored, total = backup_decrypt._read_archive(
                self._Process(io.BytesIO(stream.getvalue())),
                self.SNAPSHOT_NAME,
                Path(temp),
            )
            self.assertEqual((restored / "manifest.txt").read_bytes(), b"x")
            self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
