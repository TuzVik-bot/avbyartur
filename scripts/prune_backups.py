#!/usr/bin/env python3

import argparse
import re
import shutil
from pathlib import Path


BACKUP_NAME = re.compile(r"^avtorinok-(\d{8}T\d{6}Z)(?:\.[A-Za-z0-9]+)?$")


def prune(backup_root: Path, keep: int = 7) -> list[Path]:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    root = backup_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("backup root must be a directory")

    backups = sorted(
        (
            item for item in root.iterdir()
            if not item.is_symlink() and item.is_dir() and BACKUP_NAME.fullmatch(item.name)
        ),
        key=lambda item: (BACKUP_NAME.fullmatch(item.name).group(1), item.name),
        reverse=True,
    )
    removed = backups[keep:]
    for backup in removed:
        shutil.rmtree(backup)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep the newest timestamped Avtorinok backups.")
    parser.add_argument("backup_root", type=Path)
    parser.add_argument("--keep", type=int, default=7)
    args = parser.parse_args()
    removed = prune(args.backup_root, args.keep)
    print(f"Applied {args.keep}-backup retention; removed {len(removed)} older backups.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
