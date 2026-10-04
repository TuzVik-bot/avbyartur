#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_FILE="$ROOT_DIR/.env"

if [ "${1:-}" = "--output" ]; then
    [ "$#" -eq 2 ] || { printf '%s\n' 'Usage: init-secrets.sh [--output PATH]' >&2; exit 2; }
    OUTPUT_FILE=$2
elif [ "$#" -ne 0 ]; then
    printf '%s\n' 'Usage: init-secrets.sh [--output PATH]' >&2
    exit 2
fi

case "$OUTPUT_FILE" in
    /*) ;;
    *) OUTPUT_FILE="$ROOT_DIR/$OUTPUT_FILE" ;;
esac

if [ -e "$OUTPUT_FILE" ]; then
    printf 'Refusing to overwrite existing secret file: %s\n' "$OUTPUT_FILE" >&2
    exit 1
fi

command -v openssl >/dev/null 2>&1 || { printf '%s\n' 'openssl is required' >&2; exit 1; }
OUTPUT_DIR=$(dirname -- "$OUTPUT_FILE")
mkdir -p "$OUTPUT_DIR"
umask 077
TEMP_FILE=$(mktemp "$OUTPUT_DIR/.avtorinok-env.XXXXXX")
trap 'rm -f "$TEMP_FILE"' EXIT HUP INT TERM

POSTGRES_PASSWORD=$(openssl rand -hex 32)
SESSION_SECRET=$(openssl rand -hex 32)
cat > "$TEMP_FILE" <<EOF
APP_ENV=production
POSTGRES_DB=avtorinok
POSTGRES_USER=avtorinok
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
SESSION_SECRET=$SESSION_SECRET
SESSION_COOKIE_SECURE=true
APP_PORT=8080
POSTGRES_VOLUME_NAME=avtorinok_postgres
PRIVATE_MEDIA_VOLUME=avtorinok_private_media
EOF
chmod 600 "$TEMP_FILE"
mv "$TEMP_FILE" "$OUTPUT_FILE"
trap - EXIT HUP INT TERM
printf 'Created %s with mode 600. Secret values were not printed.\n' "$OUTPUT_FILE"
