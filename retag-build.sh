#!/usr/bin/env bash
set -euo pipefail

candidate=/home/suite/apps/releases/competitive-first-wave-20261021-r1
release_tag=competitive-first-wave-20261021-r1
api_tag=avtorinok-api:$release_tag
web_tag=avtorinok-web:$release_tag
worker_tag=avtorinok-api:pilot-catalog-product-20261015T1241Z
backup=/home/suite/apps/releases/competitive-first-wave-20261021-r1.compose-before.yml
override=$candidate/docker-compose.override.yml

[ -d "$candidate" ] || { echo "STOP candidate missing"; exit 61; }
[ ! -e "$backup" ] || { echo "STOP compose backup already exists"; exit 62; }
for image in "$api_tag" "$web_tag"; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "STOP immutable candidate image tag already exists: $image"
    exit 63
  fi
done
cp -p "$override" "$backup"
python3 - "$override" "$api_tag" "$web_tag" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
api_tag, web_tag = sys.argv[2:]
text = path.read_text()
replacements = (
    ("    image: avtorinok-api:customs-benefit-20261016\n", f"    image: {api_tag}\n"),
    ("    image: avtorinok-web:site-assistant-20261021-r1\n", f"    image: {web_tag}\n"),
)
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one candidate Compose line: {old.strip()}")
    text = text.replace(old, new)
path.write_text(text)
PY
grep -Fx "    image: $api_tag" "$override"
grep -Fx "    image: $web_tag" "$override"
grep -Fx "    image: $worker_tag" "$override"
cd "$candidate"
echo "EFFECTIVE_IMAGES"
docker compose config --images
echo "BUILD_START api web"
docker compose build api web
echo "BUILD_IMAGES"
docker image inspect --format '{{.Os}}/{{.Architecture}} {{.Id}} {{.RepoTags}}' "$api_tag" "$web_tag"
