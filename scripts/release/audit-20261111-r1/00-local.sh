#!/usr/bin/env bash
# Local helper: package the committed release source and print the upload command.
# It never contacts the server; the lead runs the printed scp command by hand.
set -euo pipefail

REPO=/Users/home/Downloads/avbyartur-prod
OUT=/Users/home/Downloads/avbyartur-prod/output/audit-release-20261111-r1
TAG=audit-20261111-r1
EXPECTED_BRANCH=prod-sync-20261110
REMOTE_PATH="/home/suite/apps/releases/${TAG}.src.tar.gz"

fail() { echo "ABORT: $*" >&2; exit 1; }

branch="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
[ "$branch" = "$EXPECTED_BRANCH" ] || fail "HEAD is on '$branch', expected '$EXPECTED_BRANCH'"

# Uncommitted or untracked (non-ignored) files mean HEAD is not what was reviewed.
dirty="$(git -C "$REPO" status --porcelain --untracked-files=normal)"
if [ -n "$dirty" ]; then
  echo "$dirty" | head -20 >&2
  fail "worktree has uncommitted changes; commit or stash them first"
fi

commit="$(git -C "$REPO" rev-parse HEAD)"
mkdir -p "$OUT"
tmp="$OUT/src.tar.gz.tmp"
rm -f "$tmp"
git -C "$REPO" archive --format=tar.gz --prefix= -o "$tmp" HEAD

# The runtime .env must never travel inside the source archive.
env_members="$(tar -tzf "$tmp" | grep -E '(^|/)\.env(\.[^/]*)?$' | grep -Ev '(^|/)\.env\.example$' || true)"
if [ -n "$env_members" ]; then
  rm -f "$tmp"
  fail "archive contains a .env file"
fi
for required in docker-compose.yml backend/Dockerfile web/Dockerfile backend/alembic.ini data/catalog.json; do
  tar -tzf "$tmp" | grep -qx "$required" || { rm -f "$tmp"; fail "archive is missing $required"; }
done

mv -f "$tmp" "$OUT/src.tar.gz"
sha="$(shasum -a 256 "$OUT/src.tar.gz" | awk '{print $1}')"
printf '%s  src.tar.gz\n' "$sha" > "$OUT/src.sha256"
printf '%s\n' "$commit" > "$OUT/src.commit"

echo "archive: $OUT/src.tar.gz"
echo "bytes:   $(wc -c < "$OUT/src.tar.gz" | tr -d ' ')"
echo "commit:  $commit"
echo "branch:  $branch"
echo "sha256:  $sha"
echo
echo "Upload (run by hand, not executed here):"
echo "  scp $OUT/src.tar.gz fortebit-prod:$REMOTE_PATH"
echo
echo "Then set SRC_SHA256 = \"$sha\" in 10-prepare-server.py."
