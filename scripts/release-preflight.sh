#!/bin/sh
set -eu

usage() {
    cat >&2 <<'EOF'
Usage: release-preflight.sh --release-dir DIR [options]

Read-only checks for a release directory and an optional active/rollback layout.
Options:
  --active-link PATH       Validate the deployment symlink target.
  --expect-active          Require --active-link to point at --release-dir.
  --rollback-dir DIR       Validate a distinct release that can be used for rollback.
  --env-file PATH          Use this protected runtime env file for Compose checks.
  --require-env            Fail if no .env or --env-file is present.
  --compose-file PATH      Compose file (defaults to DIR/docker-compose.yml).
  --override-file PATH     Additional Compose override to include in effective config.
  --expected-image-tag TAG Candidate tag required on API and web images.
  --skip-compose           Skip the read-only `docker compose config` check.
  --source-archive PATH    Verify archive SHA-256 and safe member names/types.
  --sha256 HEX             Required expected SHA-256 for --source-archive.
EOF
}

RELEASE_DIR=
ACTIVE_LINK=
EXPECT_ACTIVE=0
ROLLBACK_DIR=
ENV_FILE=
REQUIRE_ENV=0
COMPOSE_FILE=
OVERRIDE_FILE=
EXPECTED_IMAGE_TAG=
SKIP_COMPOSE=0
SOURCE_ARCHIVE=
EXPECTED_SHA=

while [ "$#" -gt 0 ]; do
    case "$1" in
        --release-dir) [ "$#" -ge 2 ] || { usage; exit 2; }; RELEASE_DIR=$2; shift 2 ;;
        --active-link) [ "$#" -ge 2 ] || { usage; exit 2; }; ACTIVE_LINK=$2; shift 2 ;;
        --expect-active) EXPECT_ACTIVE=1; shift ;;
        --rollback-dir) [ "$#" -ge 2 ] || { usage; exit 2; }; ROLLBACK_DIR=$2; shift 2 ;;
        --env-file) [ "$#" -ge 2 ] || { usage; exit 2; }; ENV_FILE=$2; shift 2 ;;
        --require-env) REQUIRE_ENV=1; shift ;;
        --compose-file) [ "$#" -ge 2 ] || { usage; exit 2; }; COMPOSE_FILE=$2; shift 2 ;;
        --override-file) [ "$#" -ge 2 ] || { usage; exit 2; }; OVERRIDE_FILE=$2; shift 2 ;;
        --expected-image-tag) [ "$#" -ge 2 ] || { usage; exit 2; }; EXPECTED_IMAGE_TAG=$2; shift 2 ;;
        --skip-compose) SKIP_COMPOSE=1; shift ;;
        --source-archive) [ "$#" -ge 2 ] || { usage; exit 2; }; SOURCE_ARCHIVE=$2; shift 2 ;;
        --sha256) [ "$#" -ge 2 ] || { usage; exit 2; }; EXPECTED_SHA=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage; exit 2 ;;
    esac
done

[ -n "$RELEASE_DIR" ] || { usage; exit 2; }
[ -z "$SOURCE_ARCHIVE" ] || [ -n "$EXPECTED_SHA" ] || {
    printf '%s\n' '--source-archive requires --sha256.' >&2
    exit 2
}
[ -z "$EXPECTED_SHA" ] || [ -n "$SOURCE_ARCHIVE" ] || {
    printf '%s\n' '--sha256 requires --source-archive.' >&2
    exit 2
}
case "$EXPECTED_SHA" in
    '') ;;
    *)
        [ "${#EXPECTED_SHA}" -eq 64 ] || { printf '%s\n' '--sha256 must contain 64 hexadecimal characters.' >&2; exit 2; }
        case "$EXPECTED_SHA" in *[!0-9A-Fa-f]*) printf '%s\n' '--sha256 must be hexadecimal.' >&2; exit 2 ;; esac
        ;;
esac

absolute_dir() {
    TARGET=$1
    [ -d "$TARGET" ] && [ ! -L "$TARGET" ] || return 1
    CDPATH= cd -- "$TARGET" && pwd -P
}

mode_of() {
    if stat -c '%a' "$1" >/dev/null 2>&1; then
        stat -c '%a' "$1"
    else
        stat -f '%Lp' "$1"
    fi
}

check_layout() {
    LABEL=$1
    DIR=$2
    REAL=$(absolute_dir "$DIR") || {
        printf '[FAIL] %s directory is missing, not a directory, or is a symlink: %s\n' "$LABEL" "$DIR"
        FAILURES=$((FAILURES + 1))
        return
    }
    case "$(basename "$REAL")" in
        *[!A-Za-z0-9_.-]*|'')
            printf '[FAIL] %s directory name contains unsupported characters: %s\n' "$LABEL" "$(basename "$REAL")"
            FAILURES=$((FAILURES + 1))
            ;;
    esac
    for REQUIRED in docker-compose.yml backend/Dockerfile web/Dockerfile scripts/backup.sh scripts/restore.sh data/catalog.json; do
        if [ -f "$REAL/$REQUIRED" ] && [ ! -L "$REAL/$REQUIRED" ]; then
            printf '[PASS] %s contains %s\n' "$LABEL" "$REQUIRED"
        else
            printf '[FAIL] %s is missing safe required file %s\n' "$LABEL" "$REQUIRED"
            FAILURES=$((FAILURES + 1))
        fi
    done
}

FAILURES=0
check_layout release "$RELEASE_DIR"
RELEASE_REAL=$(absolute_dir "$RELEASE_DIR" 2>/dev/null || true)

if [ -n "$ROLLBACK_DIR" ]; then
    check_layout rollback "$ROLLBACK_DIR"
    ROLLBACK_REAL=$(absolute_dir "$ROLLBACK_DIR" 2>/dev/null || true)
    if [ -n "$RELEASE_REAL" ] && [ -n "$ROLLBACK_REAL" ] && [ "$RELEASE_REAL" = "$ROLLBACK_REAL" ]; then
        printf '[FAIL] rollback directory must be distinct from the release directory\n'
        FAILURES=$((FAILURES + 1))
    else
        printf '[PASS] rollback directory is distinct\n'
    fi
fi

if [ -n "$ACTIVE_LINK" ]; then
    if [ ! -L "$ACTIVE_LINK" ]; then
        printf '[FAIL] active link is missing or is not a symlink: %s\n' "$ACTIVE_LINK"
        FAILURES=$((FAILURES + 1))
    elif ACTIVE_REAL=$(CDPATH= cd -- "$ACTIVE_LINK" 2>/dev/null && pwd -P); then
        printf '[PASS] active link resolves to an existing release directory\n'
        if [ "$EXPECT_ACTIVE" -eq 1 ] && [ "$ACTIVE_REAL" != "$RELEASE_REAL" ]; then
            printf '[FAIL] active link does not point to the requested release\n'
            FAILURES=$((FAILURES + 1))
        elif [ "$EXPECT_ACTIVE" -eq 1 ]; then
            printf '[PASS] active link points to the requested release\n'
        fi
        if [ -n "${ROLLBACK_REAL:-}" ] && [ "$ACTIVE_REAL" = "$ROLLBACK_REAL" ]; then
            printf '[FAIL] active link points to the rollback candidate\n'
            FAILURES=$((FAILURES + 1))
        fi
    else
        printf '[FAIL] active link target is unavailable\n'
        FAILURES=$((FAILURES + 1))
    fi
elif [ "$EXPECT_ACTIVE" -eq 1 ]; then
    printf '%s\n' '--expect-active requires --active-link.' >&2
    exit 2
else
    printf '[SKIP] active symlink check (no --active-link)\n'
fi

if [ -n "$SOURCE_ARCHIVE" ]; then
    if [ ! -f "$SOURCE_ARCHIVE" ] || [ -L "$SOURCE_ARCHIVE" ]; then
        printf '[FAIL] source archive is missing or is a symlink\n'
        FAILURES=$((FAILURES + 1))
    else
        if command -v sha256sum >/dev/null 2>&1; then
            ACTUAL_SHA=$(sha256sum "$SOURCE_ARCHIVE" | awk '{print $1}')
        elif command -v shasum >/dev/null 2>&1; then
            ACTUAL_SHA=$(shasum -a 256 "$SOURCE_ARCHIVE" | awk '{print $1}')
        else
            printf '[FAIL] sha256sum or shasum is required for archive verification\n'
            FAILURES=$((FAILURES + 1))
            ACTUAL_SHA=
        fi
        EXPECTED_SHA_NORMALIZED=$(printf '%s' "$EXPECTED_SHA" | tr '[:upper:]' '[:lower:]')
        if [ -n "$ACTUAL_SHA" ] && [ "$ACTUAL_SHA" != "$EXPECTED_SHA_NORMALIZED" ]; then
            printf '[FAIL] source archive SHA-256 does not match\n'
            FAILURES=$((FAILURES + 1))
        elif [ -n "$ACTUAL_SHA" ]; then
            printf '[PASS] source archive SHA-256 matches\n'
        fi
        if [ -n "$ACTUAL_SHA" ] && [ "$ACTUAL_SHA" = "$EXPECTED_SHA_NORMALIZED" ]; then
            if command -v python3 >/dev/null 2>&1 && python3 - "$SOURCE_ARCHIVE" <<'PY'
import sys
import tarfile


def unsafe_path(name):
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        return True
    trimmed = name[:-1] if name.endswith("/") else name
    parts = trimmed.split("/")
    if not trimmed or any(part in {"", ".", ".."} for part in parts):
        return True
    lowered = [part.casefold() for part in parts]
    if any(part == ".env" or (part.startswith(".env.") and part != ".env.example") for part in lowered):
        return True
    if any(part in {
        ".agents", ".aws", ".cache", ".codex", ".config", ".next", ".pytest_cache",
        ".ruff_cache", ".ssh", ".superpowers", ".tox", ".venv", "__pycache__",
        "node_modules", "playwright-report", "test-results",
    } for part in lowered):
        return True
    if any(
        part in {".netrc", ".npmrc", ".pypirc", ".coverage", "credentials", "credentials.json",
                 "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", "secrets"}
        or part.startswith(".htpasswd")
        or part.startswith("pilot-password")
        or part.endswith((".pem", ".key", ".p12", ".pfx", ".dump", ".sql", ".sqlite", ".sqlite3", ".db", ".log", ".tmp"))
        for part in lowered
    ):
        return True
    if any(part in {"backups", "private-media", "runtime-data"} for part in lowered):
        return True
    if len(lowered) >= 2 and lowered[0] == "data" and lowered[1] == "licensed":
        return True
    return False


try:
    seen = set()
    with tarfile.open(sys.argv[1], "r:gz") as archive:
        for member in archive:
            name = member.name
            normalized = name[:-1] if name.endswith("/") else name
            duplicate_key = normalized.casefold()
            if unsafe_path(name) or duplicate_key in seen or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe archive member")
            seen.add(duplicate_key)
except Exception:
    sys.exit(1)
PY
            then
                printf '%s\n' '[PASS] source archive members are safe regular files/directories'
            else
                printf '[FAIL] source archive contains unsafe or unreadable members\n'
                FAILURES=$((FAILURES + 1))
            fi
        fi
    fi
fi

if [ -n "$ENV_FILE" ] && [ "${ENV_FILE#/}" = "$ENV_FILE" ]; then
    ENV_FILE=$(CDPATH= cd -- "$(dirname -- "$ENV_FILE")" && pwd -P)/$(basename -- "$ENV_FILE")
fi
if [ -n "$ENV_FILE" ]; then
    [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ] || {
        printf '[FAIL] env file is missing or is a symlink\n'
        FAILURES=$((FAILURES + 1))
    }
elif [ -n "$RELEASE_REAL" ] && [ -f "$RELEASE_REAL/.env" ] && [ ! -L "$RELEASE_REAL/.env" ]; then
    ENV_FILE="$RELEASE_REAL/.env"
fi

if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ] && [ ! -L "$ENV_FILE" ]; then
    ENV_MODE=$(mode_of "$ENV_FILE")
    if [ "$ENV_MODE" = 600 ]; then
        printf '[PASS] runtime env file has mode 600\n'
    else
        printf '[FAIL] runtime env file must have mode 600 (found %s)\n' "$ENV_MODE"
        FAILURES=$((FAILURES + 1))
    fi
elif [ "$REQUIRE_ENV" -eq 1 ]; then
    printf '[FAIL] runtime env file is required for this preflight\n'
    FAILURES=$((FAILURES + 1))
else
    printf '[SKIP] runtime env permission check (no env file supplied)\n'
fi

if [ "$SKIP_COMPOSE" -eq 1 ]; then
    printf '[SKIP] Compose config check (--skip-compose)\n'
else
    [ -n "$COMPOSE_FILE" ] || COMPOSE_FILE=${RELEASE_REAL:-$RELEASE_DIR}/docker-compose.yml
    if [ "${COMPOSE_FILE#/}" = "$COMPOSE_FILE" ]; then
        COMPOSE_FILE=$(CDPATH= cd -- "$(dirname -- "$COMPOSE_FILE")" && pwd -P)/$(basename -- "$COMPOSE_FILE")
    fi
    EXPECTED_TAG_VALID=1
    if [ -z "$EXPECTED_IMAGE_TAG" ]; then
        printf '[FAIL] an expected image tag is required for Compose validation\n'
        FAILURES=$((FAILURES + 1))
        EXPECTED_TAG_VALID=0
    else
        case "$EXPECTED_IMAGE_TAG" in
            local|latest|[-.]*|*[!A-Za-z0-9_.-]*)
                printf '[FAIL] expected image tag is unsafe or reserved\n'
                FAILURES=$((FAILURES + 1))
                EXPECTED_TAG_VALID=0
                ;;
            *)
                [ "${#EXPECTED_IMAGE_TAG}" -le 128 ] || {
                    printf '[FAIL] expected image tag exceeds Docker tag length\n'
                    FAILURES=$((FAILURES + 1))
                    EXPECTED_TAG_VALID=0
                }
                case "$(printf '%s' "$EXPECTED_IMAGE_TAG" | tr '[:upper:]' '[:lower:]')" in
                    local|latest)
                        printf '[FAIL] expected image tag is unsafe or reserved\n'
                        FAILURES=$((FAILURES + 1))
                        EXPECTED_TAG_VALID=0
                        ;;
                esac
                ;;
        esac
    fi
    if [ ! -f "$COMPOSE_FILE" ] || [ -L "$COMPOSE_FILE" ]; then
        printf '[FAIL] Compose file is missing or is a symlink\n'
        FAILURES=$((FAILURES + 1))
    elif ! command -v docker >/dev/null 2>&1; then
        printf '[FAIL] docker is required for Compose config validation\n'
        FAILURES=$((FAILURES + 1))
    elif [ "$EXPECTED_TAG_VALID" -ne 1 ]; then
        :
    elif [ -z "$ENV_FILE" ] || [ ! -f "$ENV_FILE" ]; then
        printf '[FAIL] Compose config validation requires --env-file or release .env\n'
        FAILURES=$((FAILURES + 1))
    else
        COMPOSE_DIR=$(CDPATH= cd -- "$(dirname -- "$COMPOSE_FILE")" && pwd -P)
        if [ -n "$OVERRIDE_FILE" ] && [ "${OVERRIDE_FILE#/}" = "$OVERRIDE_FILE" ]; then
            OVERRIDE_FILE=$(CDPATH= cd -- "$(dirname -- "$OVERRIDE_FILE")" && pwd -P)/$(basename -- "$OVERRIDE_FILE")
        elif [ -z "$OVERRIDE_FILE" ] && [ -e "$COMPOSE_DIR/docker-compose.override.yml" ]; then
            OVERRIDE_FILE="$COMPOSE_DIR/docker-compose.override.yml"
        fi
        if [ -n "$OVERRIDE_FILE" ] && { [ ! -f "$OVERRIDE_FILE" ] || [ -L "$OVERRIDE_FILE" ]; }; then
            printf '[FAIL] Compose override is missing or is a symlink\n'
            FAILURES=$((FAILURES + 1))
        elif ! command -v python3 >/dev/null 2>&1; then
            printf '[FAIL] python3 is required to validate effective Compose images\n'
            FAILURES=$((FAILURES + 1))
        else
            IMAGE_OUTPUT=$(mktemp "${TMPDIR:-/tmp}/avtorinok-compose-images.XXXXXX") || {
                printf '[FAIL] unable to create temporary Compose validation output\n'
                FAILURES=$((FAILURES + 1))
                IMAGE_OUTPUT=
            }
            if [ -n "$IMAGE_OUTPUT" ]; then
                trap 'rm -f "$IMAGE_OUTPUT"' 0 HUP INT TERM
                COMPOSE_STATUS=0
                if [ -n "$OVERRIDE_FILE" ]; then
                    (cd "$COMPOSE_DIR" && docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" config --images) >"$IMAGE_OUTPUT" 2>/dev/null || COMPOSE_STATUS=$?
                else
                    (cd "$COMPOSE_DIR" && docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --images) >"$IMAGE_OUTPUT" 2>/dev/null || COMPOSE_STATUS=$?
                fi
                if [ "$COMPOSE_STATUS" -ne 0 ]; then
                    printf '[FAIL] Compose config validation failed\n'
                    FAILURES=$((FAILURES + 1))
                elif VALIDATION_REASON=$(python3 - "$IMAGE_OUTPUT" "$EXPECTED_IMAGE_TAG" <<'PY'
import re
import sys

tag_pattern = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")
digest_pattern = re.compile(r"sha256:[A-Fa-f0-9]{64}\Z")
repository_pattern = re.compile(r"[a-z0-9][a-z0-9./:_-]*\Z")
expected = sys.argv[2]
try:
    with open(sys.argv[1], encoding="utf-8") as source:
        images = [line.strip() for line in source if line.strip()]
    app_tags = {"avtorinok-api": set(), "avtorinok-web": set()}
    if not images:
        raise ValueError("unsafe image reference")
    for image in images:
        if any(character.isspace() for character in image) or image.count("@") > 1:
            raise ValueError("unsafe image reference")
        image_name, separator, digest = image.partition("@")
        if separator and not digest_pattern.fullmatch(digest):
            raise ValueError("unsafe image reference")
        slash = image_name.rfind("/")
        colon = image_name.rfind(":")
        if colon <= slash:
            raise ValueError("unsafe image reference")
        image_tag = image_name[colon + 1:]
        repository = image_name[:colon]
        if (
            not repository_pattern.fullmatch(repository)
            or "//" in repository
            or repository.endswith("/")
            or not tag_pattern.fullmatch(image_tag)
            or image_tag.casefold() in {"local", "latest"}
        ):
            raise ValueError("unsafe image reference")
        final_name = repository.rsplit("/", 1)[-1]
        if final_name == "avtorinok-api":
            if image_tag != expected:
                raise ValueError("effective image tags do not match")
            app_tags["avtorinok-api"].add(image_tag)
        elif final_name == "avtorinok-web":
            if image_tag != expected:
                raise ValueError("effective image tags do not match")
            app_tags["avtorinok-web"].add(image_tag)
    if any(tags != {expected} for tags in app_tags.values()):
        raise ValueError("effective image tags do not match")
except Exception as error:
    message = str(error)
    if message not in {"unsafe image reference", "effective image tags do not match"}:
        message = "unsafe image reference"
    print(message)
    sys.exit(1)
PY
                ); then
                    printf '[PASS] effective image tags match %s\n' "$EXPECTED_IMAGE_TAG"
                    printf '%s\n' '[PASS] Compose config validates without starting services'
                else
                    case "$VALIDATION_REASON" in
                        'effective image tags do not match')
                            printf '%s\n' '[FAIL] effective image tags do not match the requested release'
                            ;;
                        *)
                            printf '%s\n' '[FAIL] Compose contains an unsafe image reference'
                            ;;
                    esac
                    FAILURES=$((FAILURES + 1))
                fi
                rm -f "$IMAGE_OUTPUT"
                trap - 0 HUP INT TERM
            fi
        fi
    fi
fi

if [ "$FAILURES" -ne 0 ]; then
    printf 'Release preflight failed: %s check(s).\n' "$FAILURES" >&2
    exit 1
fi
printf '%s\n' 'Release preflight passed; no services, volumes, symlinks, or remote hosts were changed.'
