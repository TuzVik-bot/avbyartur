#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

TAG=${AVTORINOK_IMAGE_TAG:-}
case "$TAG" in
    ""|local|latest|[-.]*|*[!A-Za-z0-9_.-]*)
        printf '%s\n' 'Set AVTORINOK_IMAGE_TAG to a non-local release tag.' >&2
        exit 2
        ;;
esac
if [ "${#TAG}" -gt 128 ]; then
    printf '%s\n' 'AVTORINOK_IMAGE_TAG exceeds Docker tag length.' >&2
    exit 2
fi

PLATFORM=linux/amd64
AVAILABLE_KB=$(df -Pk "$ROOT_DIR" | awk 'NR == 2 { print $4 }')
MINIMUM_KB=$((15 * 1024 * 1024))
if [ -z "$AVAILABLE_KB" ] || [ "$AVAILABLE_KB" -lt "$MINIMUM_KB" ]; then
    printf '%s\n' 'AMD64 image build requires at least 15 GiB free on the project filesystem.' >&2
    exit 1
fi

DB_IMAGE=postgres:17.11-alpine
if ENGINE_PROBE_PLATFORM=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$DB_IMAGE" 2>/dev/null); then
    :
else
    docker pull --platform "$PLATFORM" "$DB_IMAGE"
    ENGINE_PROBE_PLATFORM=$PLATFORM
fi
ENGINE_AVAILABLE_KB=$(docker run --rm --read-only --platform "$ENGINE_PROBE_PLATFORM" \
    --entrypoint sh "$DB_IMAGE" -c 'df -Pk /' | awk 'NR == 2 { print $4 }')
if [ -z "$ENGINE_AVAILABLE_KB" ] || [ "$ENGINE_AVAILABLE_KB" -lt "$MINIMUM_KB" ]; then
    printf '%s\n' 'AMD64 image build requires at least 15 GiB free in Docker engine storage.' >&2
    exit 1
fi

printf 'Build storage preflight: host=%s KiB, Docker engine=%s KiB available.\n' \
    "$AVAILABLE_KB" "$ENGINE_AVAILABLE_KB"

if [ "$ENGINE_PROBE_PLATFORM" != "$PLATFORM" ]; then
    docker pull --platform "$PLATFORM" "$DB_IMAGE"
fi

docker buildx inspect --bootstrap >/dev/null

API_IMAGE="avtorinok-api:$TAG"
WEB_IMAGE="avtorinok-web:$TAG"

printf 'Building %s for %s\n' "$API_IMAGE" "$PLATFORM"
docker buildx build --platform "$PLATFORM" --load \
    -f backend/Dockerfile -t "$API_IMAGE" .

printf 'Building %s for %s\n' "$WEB_IMAGE" "$PLATFORM"
docker buildx build --platform "$PLATFORM" --load \
    -f web/Dockerfile -t "$WEB_IMAGE" .

verify_image() {
    image=$1
    architecture=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")
    size=$(docker image inspect --format '{{.Size}}' "$image")
    if [ "$architecture" != "$PLATFORM" ]; then
        printf 'Unexpected architecture for %s: %s\n' "$image" "$architecture" >&2
        exit 1
    fi
    printf '%s\t%s\t%s bytes\n' "$image" "$architecture" "$size"
}

printf '\nRelease image verification (local uncompressed image sizes):\n'
verify_image "$API_IMAGE"
verify_image "$WEB_IMAGE"
verify_image "$DB_IMAGE"
