#!/bin/sh
set -eu

case "${1:---dry-run}" in
    --dry-run)
        set -- --dry-run
        ;;
    --apply)
        set --
        ;;
    *)
        printf '%s\n' 'Usage: import-catalog.sh [--dry-run|--apply]' >&2
        exit 2
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$ROOT_DIR"
docker compose exec -T api python -m app.cli import-catalog --path /app/data/catalog.json "$@"
