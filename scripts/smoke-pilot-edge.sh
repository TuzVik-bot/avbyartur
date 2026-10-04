#!/bin/sh
set -eu

usage() {
    printf '%s\n' 'Usage: smoke-pilot-edge.sh --base-url URL' >&2
}

BASE_URL=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --base-url)
            [ "$#" -ge 2 ] || { usage; exit 2; }
            BASE_URL=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

[ -n "$BASE_URL" ] || { usage; exit 2; }
case "$BASE_URL" in
    http://*|https://*) ;;
    *) printf '%s\n' 'Base URL must begin with http:// or https://.' >&2; exit 2 ;;
esac
case "$BASE_URL" in
    *'?'*|*'#'*) printf '%s\n' 'Base URL must not contain a query or fragment.' >&2; exit 2 ;;
esac
BASE_URL=${BASE_URL%/}

command -v curl >/dev/null 2>&1 || {
    printf '%s\n' 'curl is required for the edge smoke.' >&2
    exit 1
}

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/avtorinok-edge-smoke.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

check_response() {
    PATH_NAME=$1
    EXPECTED_STATUS=$2
    HEADER_FILE="$TMP_DIR/headers-${#PATH_NAME}"
    URL="$BASE_URL$PATH_NAME"
    STATUS=$(curl --silent --show-error --max-time 20 --dump-header "$HEADER_FILE" \
        --output /dev/null --write-out '%{http_code}' "$URL") || STATUS=000
    if [ "$STATUS" != "$EXPECTED_STATUS" ]; then
        printf '[FAIL] anonymous %s expected HTTP %s, got %s\n' "$PATH_NAME" "$EXPECTED_STATUS" "$STATUS"
        return 1
    fi
    printf '[PASS] anonymous %s HTTP %s\n' "$PATH_NAME" "$STATUS"
    return 0
}

check_noindex() {
    PATH_NAME=$1
    HEADER_FILE="$TMP_DIR/headers-${#PATH_NAME}"
    ROBOTS=$(awk 'tolower($0) ~ /^x-robots-tag:/ {
        sub(/^[^:]*:[[:space:]]*/, "")
        value = value (value ? "," : "") tolower($0)
    }
    END { print value }' "$HEADER_FILE")
    case ",$ROBOTS," in
        *,noindex,*) printf '[PASS] anonymous %s contains noindex\n' "$PATH_NAME"; return 0 ;;
        *) printf '[FAIL] anonymous %s is missing X-Robots-Tag: noindex\n' "$PATH_NAME"; return 1 ;;
    esac
}

FAILURES=0
for PATH_NAME in / /healthz /robots.txt /api/v1/listings /cars /trucks /buses /motorcycles \
    /special-equipment /agricultural-equipment /trailers /watercraft /parts /wheels /tires \
    /useful-information /vin-check /financing /customs-calculator; do
    check_response "$PATH_NAME" 200 || FAILURES=$((FAILURES + 1))
    check_noindex "$PATH_NAME" || FAILURES=$((FAILURES + 1))
done

for PATH_NAME in /api/v1/me /api/v1/admin/users; do
    check_response "$PATH_NAME" 401 || FAILURES=$((FAILURES + 1))
    check_noindex "$PATH_NAME" || FAILURES=$((FAILURES + 1))
done

if [ "$FAILURES" -ne 0 ]; then
    printf '%s\n' "Edge smoke failed: $FAILURES check(s)." >&2
    exit 1
fi
printf '%s\n' 'Edge smoke passed; portal routes are available without shared credentials, account APIs remain authenticated, and noindex is present.'
