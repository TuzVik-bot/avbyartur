import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prune_backups import prune


class BackupRetentionTests(unittest.TestCase):
    def test_prunes_oldest_timestamped_backups_and_keeps_other_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backups = [root / f"avtorinok-202609{day:02d}T030000Z" for day in range(2, 10)]
            backups.insert(0, root / "avtorinok-20260901T030000Z.ABC123")
            for backup in backups:
                backup.mkdir()
                (backup / "database.dump").write_bytes(b"backup")
            unrelated = root / "notes"
            unrelated.mkdir()
            staging = root / ".avtorinok-20260930T030000Z.tmp"
            staging.mkdir()
            outside = root / "outside-target"
            outside.mkdir()
            protected_link = root / "avtorinok-20260801T030000Z"
            protected_link.symlink_to(outside, target_is_directory=True)

            removed = prune(root)

            self.assertEqual([path.name for path in removed], [backups[1].name, backups[0].name])
            self.assertTrue(all(path.is_dir() for path in backups[2:]))
            self.assertTrue(unrelated.is_dir())
            self.assertTrue(staging.is_dir())
            self.assertTrue(protected_link.is_symlink())
            self.assertTrue(outside.is_dir())

    def test_rejects_zero_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prune(Path(directory), keep=0)


if __name__ == "__main__":
    unittest.main()
