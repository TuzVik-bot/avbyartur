#!/bin/sh
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ "$#" -ne 2 ] || [ "$1" != "--yes" ]; then
    printf '%s\n' 'Usage: restore.sh --yes BACKUP_DIRECTORY' >&2
    printf '%s\n' 'This replaces the active database and switches the app to a new private-media volume.' >&2
    exit 2
fi
BACKUP_DIR=$2
case "$BACKUP_DIR" in
    /*) ;;
    *) BACKUP_DIR="$ROOT_DIR/$BACKUP_DIR" ;;
esac

for file in manifest.txt SHA256SUMS; do
    [ -f "$BACKUP_DIR/$file" ] || { printf 'Missing backup file: %s\n' "$file" >&2; exit 1; }
done
[ -f "$ROOT_DIR/.env" ] || { printf '%s\n' 'Create the runtime .env first' >&2; exit 1; }

FORMAT_VERSION=$(LC_ALL=C awk -F= '
    $1 == "format_version" { version_count++; version = $2 }
    $1 == "includes" { includes_count++; includes = $2 }
    END {
        version_one = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json"
        version_two = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json"
        version_three = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json"
        version_four = "database.dump,private-media.tar.gz,catalog.json,catalog-coverage.json,drom-batch-01-1-10-makes.csv,drom-batch-01-1-10-makes-report.json,drom-batch-02-10-makes.csv,drom-batch-02-10-makes.json,drom-batch-02-10-makes-report.json,drom-batch-03-10-makes.csv,drom-batch-03-10-makes.json,drom-batch-03-10-makes-report.json"
        version_five = version_four
        for (batch = 4; batch <= 9; batch++) {
            suffix = sprintf("%02d", batch)
            base = "drom-batch-" suffix "-10-makes"
            version_five = version_five "," base ".csv," base ".json," base "-report.json"
        }
        if (version_count != 1 || includes_count != 1) exit 1
        if (version == "1" && includes == version_one) print version
        else if (version == "2" && includes == version_two) print version
        else if (version == "3" && includes == version_three) print version
        else if (version == "4" && includes == version_four) print version
        else if (version == "5" && includes == version_five) print version
        else exit 1
    }
' "$BACKUP_DIR/manifest.txt") || {
    printf '%s\n' 'Unsupported backup manifest: expected format version 1, 2, 3, 4, or 5 with its exact file set' >&2
    exit 1
}

CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json manifest.txt'
LICENSED_FILES=
case "$FORMAT_VERSION" in
    2) LICENSED_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json' ;;
    3) LICENSED_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json' ;;
    4) LICENSED_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json drom-batch-03-10-makes.csv drom-batch-03-10-makes.json drom-batch-03-10-makes-report.json' ;;
    5) LICENSED_FILES='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json drom-batch-03-10-makes.csv drom-batch-03-10-makes.json drom-batch-03-10-makes-report.json drom-batch-04-10-makes.csv drom-batch-04-10-makes.json drom-batch-04-10-makes-report.json drom-batch-05-10-makes.csv drom-batch-05-10-makes.json drom-batch-05-10-makes-report.json drom-batch-06-10-makes.csv drom-batch-06-10-makes.json drom-batch-06-10-makes-report.json drom-batch-07-10-makes.csv drom-batch-07-10-makes.json drom-batch-07-10-makes-report.json drom-batch-08-10-makes.csv drom-batch-08-10-makes.json drom-batch-08-10-makes-report.json drom-batch-09-10-makes.csv drom-batch-09-10-makes.json drom-batch-09-10-makes-report.json' ;;
esac
if [ -n "$LICENSED_FILES" ]; then
    for licensed_name in $LICENSED_FILES; do
        CHECKSUM_FILES="$CHECKSUM_FILES $licensed_name"
    done
    LICENSED_DIR="$ROOT_DIR/data/licensed"
    if [ -L "$LICENSED_DIR" ] || { [ -e "$LICENSED_DIR" ] && [ ! -d "$LICENSED_DIR" ]; }; then
        printf '%s\n' 'data/licensed exists but is not a safe directory' >&2
        exit 1
    fi
    for licensed_name in $LICENSED_FILES; do
        licensed_path="$LICENSED_DIR/$licensed_name"
        [ ! -e "$licensed_path" ] || [ -f "$licensed_path" ] || {
            printf 'Licensed restore target is not a regular file: %s\n' "$licensed_path" >&2
            exit 1
        }
    done
fi
for file in $CHECKSUM_FILES; do
    [ -f "$BACKUP_DIR/$file" ] || { printf 'Missing backup file: %s\n' "$file" >&2; exit 1; }
done

if ! LC_ALL=C awk -v format_version="$FORMAT_VERSION" '
    BEGIN {
        FS = "  "
        expected["database.dump"] = 1
        expected["private-media.tar.gz"] = 1
        expected["catalog.json"] = 1
        expected["catalog-coverage.json"] = 1
        expected["manifest.txt"] = 1
        if (format_version == "2") {
            expected["drom-batch-01-1-10-makes.csv"] = 1
            expected["drom-batch-01-1-10-makes-report.json"] = 1
        } else if (format_version == "3" || format_version == "4" || format_version == "5") {
            expected["drom-batch-01-1-10-makes.csv"] = 1
            expected["drom-batch-01-1-10-makes-report.json"] = 1
            expected["drom-batch-02-10-makes.csv"] = 1
            expected["drom-batch-02-10-makes.json"] = 1
            expected["drom-batch-02-10-makes-report.json"] = 1
        }
        if (format_version == "4" || format_version == "5") {
            expected["drom-batch-03-10-makes.csv"] = 1
            expected["drom-batch-03-10-makes.json"] = 1
            expected["drom-batch-03-10-makes-report.json"] = 1
        }
        if (format_version == "5") {
            for (batch = 4; batch <= 9; batch++) {
                suffix = sprintf("%02d", batch)
                base = "drom-batch-" suffix "-10-makes"
                expected[base ".csv"] = 1
                expected[base ".json"] = 1
                expected[base "-report.json"] = 1
            }
        }
    }
    {
        if (NF != 2 || length($1) != 64 || $1 !~ /^[[:xdigit:]]+$/) invalid = 1
        if (!($2 in expected) || ($2 in seen)) invalid = 1
        seen[$2] = 1
    }
    END {
        expected_count = format_version == "5" ? 31 : format_version == "4" ? 13 : format_version == "3" ? 10 : format_version == "2" ? 7 : 5
        if (NR != expected_count || invalid) exit 1
        for (name in expected) {
            if (!(name in seen)) exit 1
        }
    }
' "$BACKUP_DIR/SHA256SUMS"; then
    printf '%s\n' 'Invalid checksum manifest: expected one SHA-256 entry for each file required by the backup format' >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS)
elif command -v shasum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && shasum -a 256 -c SHA256SUMS)
else
    printf '%s\n' 'sha256sum or shasum is required' >&2
    exit 1
fi

PRIVATE_MEDIA_VOLUME=$(sed -n 's/^PRIVATE_MEDIA_VOLUME=//p' "$ROOT_DIR/.env" | head -n 1)
case "$PRIVATE_MEDIA_VOLUME" in
    ''|*[!A-Za-z0-9_.-]*) printf '%s\n' 'PRIVATE_MEDIA_VOLUME in .env is missing or invalid' >&2; exit 1 ;;
esac

cd "$ROOT_DIR"
WAS_API=$(docker compose ps -q --status running api 2>/dev/null || true)
WAS_WORKER=$(docker compose ps -q --status running worker 2>/dev/null || true)
WAS_WEB=$(docker compose ps -q --status running web 2>/dev/null || true)
RESTORE_STOPPED=0
RESTORE_COMPLETED=0
RESTORE_DATABASE_COMMIT_POSSIBLE=0
ENV_TEMP=
LICENSED_STAGING=

finish_restore() {
    STATUS=$?
    trap - EXIT HUP INT TERM
    if [ -n "$ENV_TEMP" ] && [ -f "$ENV_TEMP" ]; then
        rm -f "$ENV_TEMP" || printf '%s\n' 'Could not remove the temporary restore .env file.' >&2
    fi
    if [ -n "$LICENSED_STAGING" ] && [ -d "$LICENSED_STAGING" ]; then
        rm -rf "$LICENSED_STAGING" || printf '%s\n' 'Could not remove the temporary licensed-source restore directory.' >&2
    fi
    if [ "$RESTORE_STOPPED" -eq 1 ] && [ "$RESTORE_COMPLETED" -eq 0 ]; then
        if [ "$RESTORE_DATABASE_COMMIT_POSSIBLE" -eq 1 ]; then
            if docker compose stop web api worker; then
                printf '%s\n' 'Restore failed after database replacement may have started; app services were stopped to avoid serving mismatched data. Inspect docker compose ps and logs.' >&2
            else
                printf '%s\n' 'Restore failed after database replacement may have started; app services could not all be stopped. Inspect docker compose ps and logs.' >&2
                [ "$STATUS" -ne 0 ] || STATUS=1
            fi
        else
            RESTART_FAILED=0
            [ -z "$WAS_API" ] || docker compose start api || RESTART_FAILED=1
            [ -z "$WAS_WORKER" ] || docker compose start worker || RESTART_FAILED=1
            [ -z "$WAS_WEB" ] || docker compose start web || RESTART_FAILED=1
            if [ "$RESTART_FAILED" -ne 0 ]; then
                printf '%s\n' 'Restore failed and one or more previously running services did not restart; inspect docker compose ps and logs.' >&2
                [ "$STATUS" -ne 0 ] || STATUS=1
            fi
        fi
    fi
    exit "$STATUS"
}
trap finish_restore EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

BACKUP_ROOT=${AVTORINOK_BACKUP_DIR:-${HOME:-.}/avtorinok-backups}
case "$BACKUP_ROOT" in
    /*) ;;
    *) BACKUP_ROOT="$ROOT_DIR/$BACKUP_ROOT" ;;
esac
mkdir -p "$BACKUP_ROOT/pre-restore"
printf '%s\n' 'Creating a pre-restore backup before replacing the database.'
LICENSED_ARTIFACTS='drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json'
for batch in 02 03 04 05 06 07 08 09; do
    base="drom-batch-$batch-10-makes"
    LICENSED_ARTIFACTS="$LICENSED_ARTIFACTS $base.csv $base.json $base-report.json"
done
LICENSED_ARTIFACTS_PRESENT=0
for licensed_name in $LICENSED_ARTIFACTS; do
    if [ -e "$ROOT_DIR/data/licensed/$licensed_name" ] || [ -L "$ROOT_DIR/data/licensed/$licensed_name" ]; then
        LICENSED_ARTIFACTS_PRESENT=1
        break
    fi
done
if [ "$LICENSED_ARTIFACTS_PRESENT" -eq 0 ]; then
    AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED=1 "$SCRIPT_DIR/backup.sh" --output-dir "$BACKUP_ROOT/pre-restore"
else
    "$SCRIPT_DIR/backup.sh" --output-dir "$BACKUP_ROOT/pre-restore"
fi

RESTORE_STOPPED=1
docker compose stop web api worker

RESTORE_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RESTORE_VOLUME="${PRIVATE_MEDIA_VOLUME}_restore_${RESTORE_STAMP}_$$"
docker volume create "$RESTORE_VOLUME" >/dev/null
docker run --rm -i -v "$RESTORE_VOLUME:/target" busybox:1.37.0 tar -xzf - -C /target < "$BACKUP_DIR/private-media.tar.gz"

RESTORE_DATABASE_COMMIT_POSSIBLE=1
docker compose exec -T db sh -ec 'pg_restore --clean --if-exists --no-owner --exit-on-error --single-transaction --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' < "$BACKUP_DIR/database.dump"

CATALOG_TEMP=$(mktemp "$ROOT_DIR/data/.catalog.restore.XXXXXX")
COVERAGE_TEMP=$(mktemp "$ROOT_DIR/data/.coverage.restore.XXXXXX")
cp "$BACKUP_DIR/catalog.json" "$CATALOG_TEMP"
cp "$BACKUP_DIR/catalog-coverage.json" "$COVERAGE_TEMP"
chmod 644 "$CATALOG_TEMP" "$COVERAGE_TEMP"
mv "$CATALOG_TEMP" "$ROOT_DIR/data/catalog.json"
mv "$COVERAGE_TEMP" "$ROOT_DIR/data/catalog-coverage.json"
docker compose run --rm --no-deps api python -m app.cli import-catalog --path /app/data/catalog.json

if [ -n "$LICENSED_FILES" ]; then
    mkdir -p "$LICENSED_DIR"
    LICENSED_STAGING=$(mktemp -d "$ROOT_DIR/data/.licensed.restore.XXXXXX")
    for licensed_name in $LICENSED_FILES; do
        cp "$BACKUP_DIR/$licensed_name" "$LICENSED_STAGING/$licensed_name"
    done
    for licensed_name in $LICENSED_FILES; do
        chmod 600 "$LICENSED_STAGING/$licensed_name"
    done
    for licensed_name in $LICENSED_FILES; do
        mv "$LICENSED_STAGING/$licensed_name" "$LICENSED_DIR/$licensed_name"
    done
    rmdir "$LICENSED_STAGING"
    LICENSED_STAGING=
fi

ENV_TEMP=$(mktemp "$ROOT_DIR/.env.restore.XXXXXX")
sed "s/^PRIVATE_MEDIA_VOLUME=.*/PRIVATE_MEDIA_VOLUME=$RESTORE_VOLUME/" "$ROOT_DIR/.env" > "$ENV_TEMP"
chmod 600 "$ENV_TEMP"
mv "$ENV_TEMP" "$ROOT_DIR/.env"
ENV_TEMP=

docker compose up -d db api worker web
ready=0
attempt=0
while [ "$attempt" -lt 30 ]; do
    if docker compose exec -T api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=3)' >/dev/null 2>&1; then
        ready=1
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done
if [ "$ready" -ne 1 ]; then
    printf '%s\n' 'Restore finished, but API readiness did not pass; inspect logs and keep the pre-restore backup.' >&2
    exit 1
fi
RESTORE_COMPLETED=1
printf 'Restored database and media. Active media volume: %s. Previous volume and pre-restore backup were retained.\n' "$RESTORE_VOLUME"
