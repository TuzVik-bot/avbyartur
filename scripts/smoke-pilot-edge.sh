#!/bin/sh
set -eu

usage() {
    printf '%s\n' 'Usage: smoke-pilot-edge.sh --base-url URL' >&2
    printf '%s\n' 'Set SMOKE_BASIC_AUTH_USER and SMOKE_BASIC_AUTH_PASSWORD together to verify authenticated responses.' >&2
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

AUTH_USER=${SMOKE_BASIC_AUTH_USER:-}
AUTH_PASSWORD=${SMOKE_BASIC_AUTH_PASSWORD:-}
if [ -n "$AUTH_USER" ] || [ -n "$AUTH_PASSWORD" ]; then
    [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASSWORD" ] || {
        printf '%s\n' 'Set both SMOKE_BASIC_AUTH_USER and SMOKE_BASIC_AUTH_PASSWORD, or leave both unset.' >&2
        exit 2
    }
    HAVE_AUTH=1
else
    HAVE_AUTH=0
fi

command -v curl >/dev/null 2>&1 || {
    printf '%s\n' 'curl is required for the edge smoke.' >&2
    exit 1
}
if [ "$HAVE_AUTH" -eq 1 ]; then
    command -v base64 >/dev/null 2>&1 || {
        printf '%s\n' 'base64 is required when authenticated checks are enabled.' >&2
        exit 1
    }
fi

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/avtorinok-edge-smoke.XXXXXX")
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

check_response() {
    PATH_NAME=$1
    EXPECTED_STATUS=$2
    MODE=$3
    HEADER_FILE="$TMP_DIR/headers-${#PATH_NAME}-${MODE}"
    URL="$BASE_URL$PATH_NAME"
    if [ "$MODE" = auth ]; then
        # Send only a base64-encoded header through curl's config stdin; raw
        # credentials never appear in curl's command-line arguments or output.
        AUTH_HEADER=$(printf '%s:%s' "$AUTH_USER" "$AUTH_PASSWORD" | base64 | tr -d '\r\n')
        STATUS=$(printf 'header = "Authorization: Basic %s"\n' "$AUTH_HEADER" | \
            curl --silent --show-error --max-time 20 --config - --dump-header "$HEADER_FILE" \
                --output /dev/null --write-out '%{http_code}' "$URL") || STATUS=000
    else
        STATUS=$(curl --silent --show-error --max-time 20 --dump-header "$HEADER_FILE" \
            --output /dev/null --write-out '%{http_code}' "$URL") || STATUS=000
    fi
    if [ "$STATUS" != "$EXPECTED_STATUS" ]; then
        printf '[FAIL] %s %s expected HTTP %s, got %s\n' "$MODE" "$PATH_NAME" "$EXPECTED_STATUS" "$STATUS"
        return 1
    fi
    printf '[PASS] %s %s HTTP %s\n' "$MODE" "$PATH_NAME" "$STATUS"
    return 0
}

check_noindex() {
    PATH_NAME=$1
    HEADER_FILE="$TMP_DIR/headers-${#PATH_NAME}-anonymous"
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
for PATH_NAME in / /healthz /robots.txt /api/v1/listings; do
    check_response "$PATH_NAME" 401 anonymous || FAILURES=$((FAILURES + 1))
    check_noindex "$PATH_NAME" || FAILURES=$((FAILURES + 1))
done

if [ "$HAVE_AUTH" -eq 1 ]; then
    for PATH_NAME in / /healthz /robots.txt /api/v1/listings; do
        check_response "$PATH_NAME" 200 auth || FAILURES=$((FAILURES + 1))
    done
else
    printf '[SKIP] authenticated responses (credentials are not configured)\n'
fi

if [ "$FAILURES" -ne 0 ]; then
    printf '%s\n' "Edge smoke failed: $FAILURES check(s)." >&2
    exit 1
fi
printf '%s\n' 'Edge smoke passed; the anonymous pilot boundary is protected and noindexed.'
