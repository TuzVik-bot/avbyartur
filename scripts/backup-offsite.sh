#!/bin/sh
set -eu

# Off-host copies leave this host only as age-encrypted bundles. The former
# plaintext rsync of a snapshot directory (database dump, private media) was
# removed; create a bundle with backup-encrypt.py and send it with
# --encrypted-bundle, or run scripts/backup-offsite-daily.py.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "${1:-}" = "--encrypted-bundle" ]; then
    shift
    exec python3 "$SCRIPT_DIR/backup-offsite-encrypted.py" "$@"
fi

printf '%s\n' 'Usage: backup-offsite.sh --encrypted-bundle [--preflight] ENCRYPTED_BUNDLE.tar.age' >&2
printf '%s\n' 'Plaintext snapshot transfer is not supported; no remote copy was attempted.' >&2
printf '%s\n' 'Set AVTORINOK_OFFSITE_TARGET to user@host:/absolute/path first.' >&2
exit 2
