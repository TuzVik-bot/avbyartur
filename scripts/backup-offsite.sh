#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" = "--encrypted-bundle" ]; then
    shift
    exec python3 "$SCRIPT_DIR/backup-offsite-encrypted.py" "$@"
fi

usage() {
    printf '%s\n' 'Usage: backup-offsite.sh [--preflight] BACKUP_DIRECTORY' >&2
    printf '%s\n' '       backup-offsite.sh --encrypted-bundle [--preflight] ENCRYPTED_BUNDLE.age' >&2
    printf '%s\n' 'Set AVTORINOK_OFFSITE_TARGET to user@host:/absolute/path first.' >&2
    printf '%s\n' '--preflight validates the snapshot and remote prerequisites without writing remotely.' >&2
}

PREFLIGHT=0
if [ "${1:-}" = "--preflight" ]; then
    PREFLIGHT=1
    shift
fi
[ "$#" -eq 1 ] || { usage; exit 2; }
[ -n "${AVTORINOK_OFFSITE_TARGET:-}" ] || {
    printf '%s\n' 'AVTORINOK_OFFSITE_TARGET is required; no remote copy was attempted.' >&2
    exit 2
}

BACKUP_DIR=$1
[ -d "$BACKUP_DIR" ] && [ ! -L "$BACKUP_DIR" ] || {
    printf '%s\n' 'Backup directory is missing or is a symlink.' >&2
    exit 1
}
BACKUP_DIR=$(CDPATH= cd -- "$BACKUP_DIR" && pwd -P)
BACKUP_NAME=${BACKUP_DIR##*/}
case "$BACKUP_NAME" in
    avtorinok-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z|avtorinok-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z.*) ;;
    *) printf '%s\n' 'Backup directory name is not a completed timestamped snapshot.' >&2; exit 1 ;;
esac
case "$BACKUP_NAME" in
    *[!A-Za-z0-9_.-]*) printf '%s\n' 'Backup directory name contains unsupported characters.' >&2; exit 1 ;;
esac

for file in manifest.txt SHA256SUMS; do
    [ -f "$BACKUP_DIR/$file" ] && [ ! -L "$BACKUP_DIR/$file" ] || {
        printf 'Snapshot is incomplete or contains an unsafe entry: %s\n' "$file" >&2
        exit 1
    }
done

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
    printf '%s\n' 'Unsupported backup manifest: expected format version 1, 2, 3, 4, or 5 with its exact file set.' >&2
    exit 1
}

EXPECTED_ENTRIES=6
EXPECTED_CHECKSUMS=5
if [ "$FORMAT_VERSION" = 2 ]; then
    EXPECTED_ENTRIES=8
    EXPECTED_CHECKSUMS=7
    CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json manifest.txt SHA256SUMS'
elif [ "$FORMAT_VERSION" = 3 ]; then
    EXPECTED_ENTRIES=11
    EXPECTED_CHECKSUMS=10
    CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json manifest.txt SHA256SUMS'
elif [ "$FORMAT_VERSION" = 4 ]; then
    EXPECTED_ENTRIES=14
    EXPECTED_CHECKSUMS=13
    CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json drom-batch-03-10-makes.csv drom-batch-03-10-makes.json drom-batch-03-10-makes-report.json manifest.txt SHA256SUMS'
elif [ "$FORMAT_VERSION" = 5 ]; then
    EXPECTED_ENTRIES=32
    EXPECTED_CHECKSUMS=31
    CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json drom-batch-01-1-10-makes.csv drom-batch-01-1-10-makes-report.json drom-batch-02-10-makes.csv drom-batch-02-10-makes.json drom-batch-02-10-makes-report.json drom-batch-03-10-makes.csv drom-batch-03-10-makes.json drom-batch-03-10-makes-report.json drom-batch-04-10-makes.csv drom-batch-04-10-makes.json drom-batch-04-10-makes-report.json drom-batch-05-10-makes.csv drom-batch-05-10-makes.json drom-batch-05-10-makes-report.json drom-batch-06-10-makes.csv drom-batch-06-10-makes.json drom-batch-06-10-makes-report.json drom-batch-07-10-makes.csv drom-batch-07-10-makes.json drom-batch-07-10-makes-report.json drom-batch-08-10-makes.csv drom-batch-08-10-makes.json drom-batch-08-10-makes-report.json drom-batch-09-10-makes.csv drom-batch-09-10-makes.json drom-batch-09-10-makes-report.json manifest.txt SHA256SUMS'
else
    CHECKSUM_FILES='database.dump private-media.tar.gz catalog.json catalog-coverage.json manifest.txt SHA256SUMS'
fi
for file in $CHECKSUM_FILES; do
    [ -f "$BACKUP_DIR/$file" ] && [ ! -L "$BACKUP_DIR/$file" ] || {
        printf 'Snapshot is incomplete or contains an unsafe entry: %s\n' "$file" >&2
        exit 1
    }
done
ENTRY_COUNT=0
for entry in "$BACKUP_DIR"/* "$BACKUP_DIR"/.[!.]* "$BACKUP_DIR"/..?*; do
    [ -e "$entry" ] || [ -L "$entry" ] || continue
    ENTRY_COUNT=$((ENTRY_COUNT + 1))
done
[ "$ENTRY_COUNT" = "$EXPECTED_ENTRIES" ] || { printf '%s\n' 'Snapshot has unexpected top-level entries.' >&2; exit 1; }

if ! LC_ALL=C awk -v format_version="$FORMAT_VERSION" -v expected_count="$EXPECTED_CHECKSUMS" '
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
        if (NR != expected_count || invalid) exit 1
        for (name in expected) if (!(name in seen)) exit 1
    }
' "$BACKUP_DIR/SHA256SUMS"; then
    printf '%s\n' 'Invalid checksum manifest: expected one SHA-256 entry for each required backup file.' >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS) || { printf '%s\n' 'Snapshot checksum verification failed.' >&2; exit 1; }
elif command -v shasum >/dev/null 2>&1; then
    (cd "$BACKUP_DIR" && shasum -a 256 -c SHA256SUMS) || { printf '%s\n' 'Snapshot checksum verification failed.' >&2; exit 1; }
else
    printf '%s\n' 'sha256sum or shasum is required to verify the snapshot.' >&2
    exit 1
fi

case "$AVTORINOK_OFFSITE_TARGET" in
    *:/*) REMOTE=${AVTORINOK_OFFSITE_TARGET%%:*}; REMOTE_DIR=${AVTORINOK_OFFSITE_TARGET#*:} ;;
    *) printf '%s\n' 'Target must use user@host:/absolute/path syntax.' >&2; exit 2 ;;
esac
case "$REMOTE" in ''|*[!A-Za-z0-9_.@-]*) printf '%s\n' 'Remote host contains unsupported characters.' >&2; exit 2 ;; esac
case "$REMOTE_DIR" in /*) ;; *) printf '%s\n' 'Remote path must be absolute.' >&2; exit 2 ;; esac
case "$REMOTE_DIR" in
    *[!A-Za-z0-9_./-]*|*'..'*|*//* ) printf '%s\n' 'Remote path contains unsupported characters.' >&2; exit 2 ;;
esac

command -v ssh >/dev/null 2>&1 && command -v rsync >/dev/null 2>&1 || {
    printf '%s\n' 'ssh and rsync are required for off-host delivery.' >&2
    exit 1
}

FINAL_DIR=${REMOTE_DIR%/}/$BACKUP_NAME
STAGING_DIR=${REMOTE_DIR%/}/.$BACKUP_NAME.incoming.$$
SSH_OPTIONS='-o BatchMode=yes -o StrictHostKeyChecking=yes'

if [ "$PREFLIGHT" -eq 1 ]; then
    REMOTE_PARENT=${REMOTE_DIR%/*}
    [ -n "$REMOTE_PARENT" ] || REMOTE_PARENT=/
    LOCAL_SIZE_KB=$(du -sk "$BACKUP_DIR" | awk '{print $1}')
    case "$LOCAL_SIZE_KB" in *[!0-9]*|'') printf '%s\n' 'Could not determine local snapshot size.' >&2; exit 1 ;; esac
    REMOTE_FREE_KB=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$REMOTE" "set -eu
        command -v rsync >/dev/null
        if command -v sha256sum >/dev/null 2>&1; then :; elif command -v shasum >/dev/null 2>&1; then :; else exit 127; fi
        MV_HELP=\$(mv --help 2>/dev/null || true)
        printf '%s' \"\$MV_HELP\" | grep -q -- '-T'
        printf '%s' \"\$MV_HELP\" | grep -q -- '-n'
        if test -e '$REMOTE_DIR'; then
            test -d '$REMOTE_DIR' && test -w '$REMOTE_DIR'
        else
            test -d '$REMOTE_PARENT' && test -w '$REMOTE_PARENT'
        fi
        test ! -e '$FINAL_DIR' && test ! -L '$FINAL_DIR'
        if test -e '$REMOTE_DIR'; then CHECK_PATH='$REMOTE_DIR'; else CHECK_PATH='$REMOTE_PARENT'; fi
        df -Pk "\$CHECK_PATH" | awk 'NR == 2 { print \$4 }'") || {
        printf '%s\n' 'Remote preflight failed; no remote files were created or changed.' >&2
        exit 1
    }
    case "$REMOTE_FREE_KB" in *[!0-9]*|'') printf '%s\n' 'Remote free-space check returned an invalid value.' >&2; exit 1 ;; esac
    REQUIRED_FREE_KB=$((LOCAL_SIZE_KB * 110 / 100))
    if [ "$REMOTE_FREE_KB" -lt "$REQUIRED_FREE_KB" ]; then
        printf 'Remote target has insufficient free space: need at least %s KiB, have %s KiB.\n' "$REQUIRED_FREE_KB" "$REMOTE_FREE_KB" >&2
        exit 1
    fi
    printf 'Off-host preflight OK: local snapshot verified; remote target is writable and destination is free (%s:%s)\n' "$REMOTE" "$FINAL_DIR"
    exit 0
fi

ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$REMOTE" "mkdir -p '$REMOTE_DIR' && test ! -e '$FINAL_DIR' && mkdir '$STAGING_DIR'" || {
    printf '%s\n' 'Remote destination is unavailable or the snapshot already exists; no existing backup was changed.' >&2
    exit 1
}

if ! rsync -e "ssh $SSH_OPTIONS" --archive -- "$BACKUP_DIR/" "$REMOTE:$STAGING_DIR/"; then
    printf '%s\n' 'Snapshot transfer failed; remote staging data was retained for inspection.' >&2
    exit 1
fi

if ! ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$REMOTE" "cd '$STAGING_DIR' && if command -v sha256sum >/dev/null 2>&1; then sha256sum -c SHA256SUMS; elif command -v shasum >/dev/null 2>&1; then shasum -a 256 -c SHA256SUMS; else exit 127; fi && test ! -e '$FINAL_DIR' && mv -T -n -- '$STAGING_DIR' '$FINAL_DIR' && test ! -e '$STAGING_DIR' && test -d '$FINAL_DIR'"; then
    printf '%s\n' 'Remote verification or finalization failed; remote staging data was retained for inspection.' >&2
    exit 1
fi

printf 'Verified snapshot copied to %s:%s\n' "$REMOTE" "$FINAL_DIR"
