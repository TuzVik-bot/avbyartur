#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BACKUP_ROOT=${AVTORINOK_BACKUP_DIR:-${HOME:-.}/avtorinok-backups}

case "$BACKUP_ROOT" in
    /*) ;;
    *) BACKUP_ROOT="$ROOT_DIR/$BACKUP_ROOT" ;;
esac

umask 077
mkdir -p "$BACKUP_ROOT"
"$SCRIPT_DIR/backup.sh" --output-dir "$BACKUP_ROOT"
python3 "$SCRIPT_DIR/prune_backups.py" "$BACKUP_ROOT" --keep 7
