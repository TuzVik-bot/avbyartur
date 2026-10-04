#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BACKUP_ROOT=${AVTORINOK_BACKUP_DIR:-${HOME:-.}/avtorinok-backups}

if [ "${1:-}" = "--output-dir" ]; then
    [ "$#" -eq 2 ] || { printf '%s\n' 'Usage: backup.sh [--output-dir DIRECTORY]' >&2; exit 2; }
    BACKUP_ROOT=$2
elif [ "$#" -ne 0 ]; then
    printf '%s\n' 'Usage: backup.sh [--output-dir DIRECTORY]' >&2
    exit 2
fi

case "$BACKUP_ROOT" in
    /*) ;;
    *) BACKUP_ROOT="$ROOT_DIR/$BACKUP_ROOT" ;;
esac

command -v docker >/dev/null 2>&1 || { printf '%s\n' 'docker is required' >&2; exit 1; }
LICENSED_DIR="$ROOT_DIR/data/licensed"
DROM_SOURCE="$LICENSED_DIR/drom-batch-01-1-10-makes.csv"
DROM_REPORT="$LICENSED_DIR/drom-batch-01-1-10-makes-report.json"
ALLOW_EMPTY_LICENSED=${AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED:-0}
case "$ALLOW_EMPTY_LICENSED" in
    0|1) ;;
    *) printf '%s\n' 'AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED must be 0 or 1' >&2; exit 2 ;;
esac
if [ -L "$LICENSED_DIR" ] || { [ -e "$LICENSED_DIR" ] && [ ! -d "$LICENSED_DIR" ]; }; then
    printf '%s\n' 'data/licensed exists but is not a safe directory' >&2
    exit 1
fi
FORMAT_VERSION=1
DROM_SOURCE_BYTES=0
DROM_REPORT_BYTES=0
LICENSED_FILES=
DROM_INCLUDED_NAMES=
DROM_BATCH_MANIFEST=
DROM_TOTAL_BYTES=0
ALL_DROM_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json'
for BATCH_NUMBER in 02 03 04 05 06 07 08 09; do
    BATCH_BASE="drom-batch-$BATCH_NUMBER-10-makes"
    ALL_DROM_FILES="$ALL_DROM_FILES $BATCH_BASE.csv $BATCH_BASE.json $BATCH_BASE-report.json"
done
if [ -f "$DROM_SOURCE" ] && [ ! -L "$DROM_SOURCE" ] && [ -r "$DROM_SOURCE" ] \
    && [ -f "$DROM_REPORT" ] && [ ! -L "$DROM_REPORT" ] && [ -r "$DROM_REPORT" ]; then
    FORMAT_VERSION=2
    DROM_SOURCE_BYTES=$(LC_ALL=C wc -c < "$DROM_SOURCE" | awk '{ print $1 }')
    DROM_REPORT_BYTES=$(LC_ALL=C wc -c < "$DROM_REPORT" | awk '{ print $1 }')
    DROM_TOTAL_BYTES=$((DROM_SOURCE_BYTES + DROM_REPORT_BYTES))
    LICENSED_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json'
    DROM_INCLUDED_NAMES='drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json'
    DROM_BATCH_MANIFEST="licensed_drom_source_bytes=$DROM_SOURCE_BYTES
licensed_drom_report_bytes=$DROM_REPORT_BYTES
licensed_data_classification=proprietary-permissioned"
    BATCH_GAP_SEEN=0
    NEW_BATCH_COUNT=0
    for BATCH_NUMBER in 02 03 04 05 06 07 08 09; do
        BATCH_DISPLAY=${BATCH_NUMBER#0}
        BATCH_BASE="drom-batch-$BATCH_NUMBER-10-makes"
        BATCH_CSV="$LICENSED_DIR/$BATCH_BASE.csv"
        BATCH_JSON="$LICENSED_DIR/$BATCH_BASE.json"
        BATCH_REPORT="$LICENSED_DIR/$BATCH_BASE-report.json"
        BATCH_PRESENT=0
        for BATCH_FILE in "$BATCH_CSV" "$BATCH_JSON" "$BATCH_REPORT"; do
            if [ -e "$BATCH_FILE" ] || [ -L "$BATCH_FILE" ]; then
                BATCH_PRESENT=1
            fi
        done
        if [ "$BATCH_PRESENT" -eq 0 ]; then
            BATCH_GAP_SEEN=1
            continue
        fi
        if [ "$BATCH_GAP_SEEN" -eq 1 ]; then
            if [ "$BATCH_NUMBER" = 03 ]; then
                printf '%s\n' 'Batch 3 permissioned Drom artifacts require a complete batch 2 set' >&2
            else
                printf 'Batch %s permissioned Drom artifacts require complete preceding batches.\n' "$BATCH_DISPLAY" >&2
            fi
            exit 1
        fi
        if [ ! -f "$BATCH_CSV" ] || [ -L "$BATCH_CSV" ] || [ ! -r "$BATCH_CSV" ] \
            || [ ! -f "$BATCH_JSON" ] || [ -L "$BATCH_JSON" ] || [ ! -r "$BATCH_JSON" ] \
            || [ ! -f "$BATCH_REPORT" ] || [ -L "$BATCH_REPORT" ] || [ ! -r "$BATCH_REPORT" ]; then
            printf 'Batch %s permissioned Drom artifacts must be a complete safe CSV/JSON/report set.\n' "$BATCH_DISPLAY" >&2
            exit 1
        fi
        BATCH_SOURCE_BYTES=$(LC_ALL=C wc -c < "$BATCH_CSV" | awk '{ print $1 }')
        BATCH_DATA_BYTES=$(LC_ALL=C wc -c < "$BATCH_JSON" | awk '{ print $1 }')
        BATCH_REPORT_BYTES=$(LC_ALL=C wc -c < "$BATCH_REPORT" | awk '{ print $1 }')
        case "$BATCH_SOURCE_BYTES:$BATCH_DATA_BYTES:$BATCH_REPORT_BYTES" in
            *[!0-9:]*|:*|*::*|*:) printf '%s\n' 'Licensed source size check returned an invalid value' >&2; exit 1 ;;
        esac
        LICENSED_FILES="$LICENSED_FILES $BATCH_BASE.csv $BATCH_BASE.json $BATCH_BASE-report.json"
        DROM_INCLUDED_NAMES="$DROM_INCLUDED_NAMES,$BATCH_BASE.csv,$BATCH_BASE.json,$BATCH_BASE-report.json"
        DROM_TOTAL_BYTES=$((DROM_TOTAL_BYTES + BATCH_SOURCE_BYTES + BATCH_DATA_BYTES + BATCH_REPORT_BYTES))
        DROM_BATCH_MANIFEST="$DROM_BATCH_MANIFEST
$(printf 'licensed_drom_batch_%s_source_bytes=%s\nlicensed_drom_batch_%s_data_bytes=%s\nlicensed_drom_batch_%s_report_bytes=%s' "$BATCH_NUMBER" "$BATCH_SOURCE_BYTES" "$BATCH_NUMBER" "$BATCH_DATA_BYTES" "$BATCH_NUMBER" "$BATCH_REPORT_BYTES")"
        case "$BATCH_NUMBER" in
            02) FORMAT_VERSION=3 ;;
            03) FORMAT_VERSION=4 ;;
            04|05|06|07|08|09) FORMAT_VERSION=5; NEW_BATCH_COUNT=$((NEW_BATCH_COUNT + 1)) ;;
        esac
    done
    if [ "$NEW_BATCH_COUNT" -ne 0 ] && [ "$NEW_BATCH_COUNT" -ne 6 ]; then
        printf '%s\n' 'Batches 4-9 permissioned Drom artifacts must be a complete set before a version-5 backup can be created.' >&2
        exit 1
    fi
elif [ "$ALLOW_EMPTY_LICENSED" = 1 ] \
    && [ ! -e "$DROM_SOURCE" ] && [ ! -L "$DROM_SOURCE" ] \
    && [ ! -e "$DROM_REPORT" ] && [ ! -L "$DROM_REPORT" ]; then
    LICENSED_ARTIFACTS_PRESENT=0
    for LICENSED_FILE in $ALL_DROM_FILES; do
        if [ -e "$LICENSED_DIR/$LICENSED_FILE" ] || [ -L "$LICENSED_DIR/$LICENSED_FILE" ]; then
            LICENSED_ARTIFACTS_PRESENT=1
            break
        fi
    done
    [ "$LICENSED_ARTIFACTS_PRESENT" -eq 0 ] || {
        printf '%s\n' 'Required permissioned Drom artifacts are missing or unsafe' >&2
        exit 1
    }
    FORMAT_VERSION=1
    printf '%s\n' 'No licensed Drom artifacts are present; creating an explicit version-1 recovery snapshot.' >&2
else
    printf '%s\n' 'Required permissioned Drom artifacts are missing or unsafe' >&2
    exit 1
fi
case "$DROM_TOTAL_BYTES" in
    *[!0-9]*|"") printf '%s\n' 'Licensed source size check returned an invalid value' >&2; exit 1 ;;
esac
cd "$ROOT_DIR"

select_running_container() {
    SERVICE=$1
    CANDIDATES=$(docker compose ps -q --status running "$SERVICE" 2>/dev/null || true)
    CANDIDATE_COUNT=$(printf '%s\n' "$CANDIDATES" | awk '{ for (field = 1; field <= NF; field++) count++ } END { print count + 0 }')
    case "$CANDIDATE_COUNT" in
        0) ;;
        1) printf '%s\n' "$CANDIDATES" | awk 'NF { print $1; exit }' ;;
        *)
            printf 'Ambiguous running Compose containers for service %s; refusing backup before mutating services:\n%s\n' "$SERVICE" "$CANDIDATES" >&2
            return 1
            ;;
    esac
}

if ! WAS_API=$(select_running_container api); then
    exit 1
fi
if ! WAS_WORKER=$(select_running_container worker); then
    exit 1
fi
if ! WAS_WEB=$(select_running_container web); then
    exit 1
fi

umask 077
mkdir -p "$BACKUP_ROOT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

capture_image_metadata() {
    if [ -n "$1" ]; then
        docker inspect --format '{{.Config.Image}}|{{.Image}}' "$1"
    else
        printf '%s\n' 'unavailable|unavailable'
    fi
}

API_IMAGE_METADATA=$(capture_image_metadata "$WAS_API")
WORKER_IMAGE_METADATA=$(capture_image_metadata "$WAS_WORKER")
WEB_IMAGE_METADATA=$(capture_image_metadata "$WAS_WEB")
for IMAGE_METADATA in "$API_IMAGE_METADATA" "$WORKER_IMAGE_METADATA" "$WEB_IMAGE_METADATA"; do
    case "$IMAGE_METADATA" in
        *'|'*) ;;
        *) printf '%s\n' 'Could not capture Compose application image identity' >&2; exit 1 ;;
    esac
done
API_IMAGE_REF=${API_IMAGE_METADATA%%|*}
API_IMAGE_ID=${API_IMAGE_METADATA#*|}
WORKER_IMAGE_REF=${WORKER_IMAGE_METADATA%%|*}
WORKER_IMAGE_ID=${WORKER_IMAGE_METADATA#*|}
WEB_IMAGE_REF=${WEB_IMAGE_METADATA%%|*}
WEB_IMAGE_ID=${WEB_IMAGE_METADATA#*|}

QUIESCED=0
STAGING=

finish() {
    STATUS=$?
    trap - EXIT HUP INT TERM
    if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
        rm -rf "$STAGING"
    fi
    if [ "$QUIESCED" -eq 1 ]; then
        RESTART_FAILED=0
        [ -z "$WAS_API" ] || docker compose start api || RESTART_FAILED=1
        [ -z "$WAS_WORKER" ] || docker compose start worker || RESTART_FAILED=1
        [ -z "$WAS_WEB" ] || docker compose start web || RESTART_FAILED=1
        if [ "$RESTART_FAILED" -ne 0 ]; then
            printf '%s\n' 'Backup services did not all restart; inspect docker compose ps and logs.' >&2
            [ "$STATUS" -ne 0 ] || STATUS=1
        fi
    fi
    exit "$STATUS"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

QUIESCED=1
docker compose stop web api worker

MEDIA_BYTES=$(docker compose run --rm --no-deps -T --entrypoint python api -c 'import os; print(sum(os.path.getsize(os.path.join(root, name)) for root, _, files in os.walk("/app/private-media") for name in files))')
DB_BYTES=$(docker compose exec -T db sh -ec 'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --command "SELECT pg_database_size(current_database())"')
AVAILABLE_KB=$(df -Pk "$BACKUP_ROOT" | awk 'NR == 2 { print $4 }')
MIN_FREE_KB=${AVTORINOK_BACKUP_MIN_FREE_KB:-2097152}
case "$MEDIA_BYTES:$DB_BYTES:$DROM_TOTAL_BYTES:$AVAILABLE_KB:$MIN_FREE_KB" in
    *[!0-9:]*|:*|*::*|*:) printf '%s\n' 'Backup size or free-space check returned an invalid value' >&2; exit 1 ;;
esac
ESTIMATED_KB=$(((MEDIA_BYTES + DB_BYTES + DROM_TOTAL_BYTES) / 1024))
REQUIRED_KB=$((ESTIMATED_KB * 120 / 100 + MIN_FREE_KB))
if [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    printf 'Insufficient free space for backup: need about %s KiB, have %s KiB.\n' "$REQUIRED_KB" "$AVAILABLE_KB" >&2
    exit 1
fi

STAGING=$(mktemp -d "$BACKUP_ROOT/.avtorinok-$STAMP.XXXXXX")
INCLUDES=database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json
if [ -n "$DROM_INCLUDED_NAMES" ]; then
    INCLUDES="$INCLUDES,$DROM_INCLUDED_NAMES"
fi
for LICENSED_FILE in $LICENSED_FILES; do
    cp "$LICENSED_DIR/$LICENSED_FILE" "$STAGING/$LICENSED_FILE"
done
docker compose exec -T db sh -ec 'pg_dump --format=custom --no-owner --username="$POSTGRES_USER" "$POSTGRES_DB"' > "$STAGING/database.dump"
docker compose run --rm --no-deps -T --entrypoint python api -c 'import sys,tarfile; archive=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); archive.add("/app/private-media", arcname="."); archive.close()' > "$STAGING/private-media.tar.gz"
cp data/catalog.json "$STAGING/catalog.json"
cp data/catalog-coverage.json "$STAGING/catalog-coverage.json"
{
cat <<EOF
format_version=$FORMAT_VERSION
created_at_utc=$STAMP
postgres_major=17
postgres_image=postgres:17.11-alpine
application_api_image=$API_IMAGE_REF
application_api_image_id=$API_IMAGE_ID
application_worker_image=$WORKER_IMAGE_REF
application_worker_image_id=$WORKER_IMAGE_ID
application_web_image=$WEB_IMAGE_REF
application_web_image_id=$WEB_IMAGE_ID
media_estimate_bytes=$MEDIA_BYTES
database_estimate_bytes=$DB_BYTES
EOF
if [ "$FORMAT_VERSION" -ge 2 ]; then
    printf '%s\n' "$DROM_BATCH_MANIFEST"
fi
printf 'includes=%s\n' "$INCLUDES"
} > "$STAGING/manifest.txt"

CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json'
for LICENSED_FILE in $LICENSED_FILES; do
    CHECKSUM_FILES="$CHECKSUM_FILES $LICENSED_FILE"
done
CHECKSUM_FILES="$CHECKSUM_FILES manifest.txt"
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$STAGING" && sha256sum $CHECKSUM_FILES > SHA256SUMS)
elif command -v shasum >/dev/null 2>&1; then
    (cd "$STAGING" && shasum -a 256 $CHECKSUM_FILES > SHA256SUMS)
else
    printf '%s\n' 'sha256sum or shasum is required' >&2
    exit 1
fi

chmod -R go-rwx "$STAGING"
chmod 600 "$STAGING/database.dump" "$STAGING/private-media.tar.gz" "$STAGING/catalog.json" "$STAGING/catalog-coverage.json" "$STAGING/manifest.txt" "$STAGING/SHA256SUMS"
for LICENSED_FILE in $LICENSED_FILES; do
    chmod 600 "$STAGING/$LICENSED_FILE"
done
FINAL_DIR="$BACKUP_ROOT/avtorinok-$STAMP"
if [ -e "$FINAL_DIR" ]; then
    FINAL_DIR=$(mktemp -d "$BACKUP_ROOT/avtorinok-$STAMP.XXXXXX")
    rmdir "$FINAL_DIR"
fi
mv "$STAGING" "$FINAL_DIR"
STAGING=
printf 'Backup created: %s\n' "$FINAL_DIR"
