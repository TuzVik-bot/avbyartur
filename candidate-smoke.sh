#!/usr/bin/env bash
set -euo pipefail

api_image=avtorinok-api:competitive-first-wave-20261021-r1
web_image=avtorinok-web:competitive-first-wave-20261021-r1

echo "API_IMPORT_AND_ROUTES"
docker run --rm --network none --entrypoint /app/.venv/bin/python "$api_image" -c '
from app.main import app
paths = set(app.openapi()["paths"])
required = {"/api/v1/listings/compare", "/api/v1/dealer/feed-imports"}
missing = sorted(required - paths)
print("ROUTES=" + ",".join(sorted(required & paths)))
if missing:
    raise SystemExit("missing API routes: " + ",".join(missing))
'

container_name=avtorinok-first-wave-web-smoke-20261021
if docker ps -a --format '{{.Names}}' | grep -Fxq "$container_name"; then
  echo "STOP smoke container name already exists"
  exit 71
fi
body=/tmp/avtorinok-first-wave-compare.html
headers=/tmp/avtorinok-first-wave-compare.headers
container_id=$(docker run -d --rm --name "$container_name" -p 127.0.0.1::3000 -e PORT=3000 -e HOSTNAME=0.0.0.0 "$web_image")
cleanup() {
  docker stop "$container_id" >/dev/null 2>&1 || true
  rm -f "$body" "$headers"
}
trap cleanup EXIT
port_line=$(docker port "$container_id" 3000/tcp | head -n 1)
port=${port_line##*:}
[ -n "$port" ] || { echo "STOP candidate web port unavailable"; exit 72; }
status=000
for _ in $(seq 1 30); do
  status=$(curl --silent --show-error --output "$body" --dump-header "$headers" --write-out '%{http_code}' "http://127.0.0.1:$port/compare" 2>/dev/null || true)
  [ "$status" = 200 ] && break
  sleep 1
done
[ "$status" = 200 ] || { echo "STOP candidate /compare HTTP $status"; exit 73; }
robots=$(grep -i '^x-robots-tag:' "$headers" | tr -d '\r' | head -n 1)
printf 'COMPARE_HTTP=%s\nROBOTS=%s\n' "$status" "$robots"
printf 'COMPARE_TITLE='; grep -o 'Сравнение автомобилей' "$body" | head -n 1
printf 'COMPARE_EMPTY_STATE='; grep -o 'Пока нет объявлений для сравнения' "$body" | head -n 1
case "$robots" in *noindex*) ;; *) echo "STOP noindex header missing"; exit 74;; esac
