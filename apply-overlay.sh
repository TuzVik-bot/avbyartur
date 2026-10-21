#!/usr/bin/env bash
set -euo pipefail

apps=/home/suite/apps
active_link=$apps/avtorinok
expected_active=$apps/releases/site-assistant-20261021-r1
candidate=$apps/releases/competitive-first-wave-20261021-r1
staging=/tmp/avtorinok-first-wave-20261021
archive=$staging/competitive-first-wave-overlay.tar.gz
manifest=$staging/overlay.sha256
archive_artifact=$apps/releases/competitive-first-wave-20261021-r1.overlay.tar.gz
manifest_artifact=$apps/releases/competitive-first-wave-20261021-r1.overlay.sha256
expected_archive_sha=f5c78e4882ffe6e670a6bf2ca2cd410182885f2f6644db502a1fc6ec111a7baf

active=$(readlink -f "$active_link")
[ "$active" = "$expected_active" ] || { echo "STOP active release changed"; exit 41; }
[ -d "$candidate" ] || { echo "STOP candidate missing"; exit 42; }
[ -L "$candidate/.env" ] || { echo "STOP candidate .env link changed"; exit 43; }
[ "$(readlink -f "$candidate/.env")" = "$(readlink -f "$active/.env")" ] || { echo "STOP candidate .env target changed"; exit 44; }
[ ! -e "$archive_artifact" ] && [ ! -e "$manifest_artifact" ] || { echo "STOP overlay artifact already exists"; exit 45; }

actual_archive_line=$(sha256sum "$archive")
actual_archive_sha=${actual_archive_line%% *}
[ "$actual_archive_sha" = "$expected_archive_sha" ] || { echo "STOP overlay archive SHA mismatch"; exit 46; }
rm -rf "$staging/overlay"
tar -xzf "$archive" -C "$staging"
(cd "$staging" && sha256sum -c overlay.sha256)
entries=$(tar -tzf "$archive")
for entry in $entries; do
  case "$entry" in overlay|overlay/*) ;; *) echo "STOP unexpected archive path: $entry"; exit 47;; esac
  case "$entry" in /*|../*|*/../*) echo "STOP unsafe archive path: $entry"; exit 48;; esac
done
file_count=$(find "$staging/overlay" -type f | wc -l | tr -d ' ')
[ "$file_count" = 20 ] || { echo "STOP expected 20 overlay files, got $file_count"; exit 49; }
if tar -tzf "$archive" | grep -q 'backend/alembic/'; then
  echo "STOP overlay unexpectedly contains a migration"
  exit 50
fi

install -m 0644 "$archive" "$archive_artifact"
install -m 0644 "$manifest" "$manifest_artifact"
tar -xzf "$archive" --strip-components=1 -C "$candidate"
while IFS=' ' read -r expected_hash source_path; do
  target_path=${source_path#overlay/}
  actual_line=$(sha256sum "$candidate/$target_path")
  actual_hash=${actual_line%% *}
  [ "$actual_hash" = "$expected_hash" ] || { echo "STOP applied hash mismatch: $target_path"; exit 51; }
done < "$manifest"
[ "$(readlink -f "$candidate/.env")" = "$(readlink -f "$active/.env")" ] || { echo "STOP .env target changed during overlay"; exit 52; }

echo "OVERLAY_APPLIED=20"
echo "OVERLAY_ARCHIVE_SHA256=$actual_archive_sha"
echo "MIGRATIONS=none"
echo "CANDIDATE=$candidate"
echo "ARTIFACT_ARCHIVE=$archive_artifact"
echo "ARTIFACT_MANIFEST=$manifest_artifact"
echo "COMPOSE_IMAGE_LINES"
grep -nE 'image:|build:|AVTORINOK_IMAGE_TAG' "$candidate/docker-compose.yml" "$candidate/docker-compose.override.yml" 2>/dev/null || true
echo "COMPOSE_EFFECTIVE_IMAGES"
(cd "$candidate" && docker compose config --images)
