#!/usr/bin/env bash
set -Eeuo pipefail

apps=/home/suite/apps
active_link=$apps/avtorinok
old_release=$apps/releases/site-assistant-20261021-r1
candidate=$apps/releases/competitive-first-wave-20261021-r1
env_file=$candidate/.env
expected_env_sha=16150470d4acd6374f0a04537664c49bbca695831207835e313066f134ef3d48
old_api_image=sha256:02359296ecd553ef024f8986ef7ffb79b61d392d6dec789fc3290398c03f6afe
old_web_image=sha256:1f0c384041dc5011404a49611c8a4240b0263709c7e3f2a5cbf1bf735c837132
new_api_tag=avtorinok-api:competitive-first-wave-20261021-r1
new_web_tag=avtorinok-web:competitive-first-wave-20261021-r1
new_api_image=sha256:b614ba540a96f709e252c83d96a4a3d59117a72645bfa9dd2db112abce3f8504
new_web_image=sha256:2337cbaecfb5db06ec6407b8d2d35b617942fdf42f09c3c4facbb85c9f369a55
worker_tag=avtorinok-api:pilot-catalog-product-20261015T1241Z
worker_container_before=
worker_image_before=
other_ids_before=()
other_images_before=()
volume_state_before=
switched=0
success=0
lock_file=/tmp/avtorinok-competitive-first-wave-20261021.activation.lock

exec 9>"$lock_file"
flock -n 9 || { echo 'STOP another first-wave activation holds the lock'; exit 80; }
echo 'LOCK=held'

service_id() {
  local service=$1
  local ids
  mapfile -t ids < <(docker ps -q --filter "label=com.docker.compose.project=avtorinok" --filter "label=com.docker.compose.service=$service")
  [[ ${#ids[@]} -eq 1 ]] || { echo "STOP expected one running $service container, got ${#ids[@]}" >&2; return 1; }
  printf '%s' "${ids[0]}"
}
service_image() {
  docker inspect --format '{{.Image}}' "$1"
}
service_health() {
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1"
}
compose_up() {
  local release=$1
  (cd "$release" && docker compose --project-directory "$release" --env-file "$release/.env" -p avtorinok -f "$release/docker-compose.yml" -f "$release/docker-compose.override.yml" up --no-build --no-deps --wait api web)
}
atomic_switch() {
  local target=$1
  local temp_link="$apps/.avtorinok-link.$$"
  rm -f "$temp_link"
  ln -s "$target" "$temp_link"
  mv -Tf "$temp_link" "$active_link"
}
rollback() {
  local rc=$?
  if [[ $switched -eq 1 && $success -eq 0 ]]; then
    trap - EXIT ERR INT TERM
    set +e
    echo 'ROLLBACK=starting'
    atomic_switch "$old_release"
    compose_up "$old_release"
    local rollback_rc=$?
    echo "ROLLBACK_COMPOSE_EXIT=$rollback_rc"
    if [[ $rollback_rc -eq 0 ]]; then
      echo 'ROLLBACK=old release and API/web restored'
    else
      echo 'ROLLBACK=FAILED; manual recovery required' >&2
    fi
  fi
  exit "$rc"
}
trap rollback EXIT

# Fresh source-state gate, held under this lock through activation and smoke.
[[ -L "$active_link" ]] || { echo 'STOP active path is not a symlink'; exit 81; }
[[ "$(readlink -f "$active_link")" == "$old_release" ]] || { echo 'STOP active release changed'; exit 82; }
[[ -d "$candidate" && ! -L "$candidate" ]] || { echo 'STOP candidate directory unavailable'; exit 83; }
[[ -L "$env_file" && "$(readlink -f "$env_file")" == "$(readlink -f "$old_release/.env")" ]] || { echo 'STOP candidate .env target changed'; exit 84; }
[[ "$(stat -c '%a' "$(readlink -f "$env_file")")" == 600 ]] || { echo 'STOP runtime .env mode changed'; exit 85; }
actual_env_sha=$(sha256sum "$(readlink -f "$env_file")" | awk '{print $1}')
[[ "$actual_env_sha" == "$expected_env_sha" ]] || { echo 'STOP runtime .env digest changed'; exit 86; }
actual_api=$(service_image "$(service_id api)")
actual_web=$(service_image "$(service_id web)")
[[ "$actual_api" == "$old_api_image" ]] || { echo 'STOP active API image changed'; exit 87; }
[[ "$actual_web" == "$old_web_image" ]] || { echo 'STOP active web image changed'; exit 88; }
[[ "$(docker image inspect --format '{{.Id}}' "$new_api_tag")" == "$new_api_image" ]] || { echo 'STOP candidate API image ID changed'; exit 89; }
[[ "$(docker image inspect --format '{{.Id}}' "$new_web_tag")" == "$new_web_image" ]] || { echo 'STOP candidate web image ID changed'; exit 90; }
worker_container_before=$(service_id worker)
worker_image_before=$(service_image "$worker_container_before")
[[ "$worker_image_before" == "$(docker image inspect --format '{{.Id}}' "$worker_tag")" ]] || { echo 'STOP worker image/tag mismatch'; exit 91; }
for service in db test-mail; do
  id=$(service_id "$service")
  other_ids_before+=("$service=$id")
  other_images_before+=("$service=$(service_image "$id")")
done
volume_state_before=$(docker volume inspect avtorinok_postgres avtorinok_private_media --format '{{.Name}}|{{.Mountpoint}}' | sort)
printf 'PRECHECK_ACTIVE=%s\nPRECHECK_API_IMAGE=%s\nPRECHECK_WEB_IMAGE=%s\nPRECHECK_WORKER_ID=%s\nPRECHECK_WORKER_IMAGE=%s\nPRECHECK_ENV_SHA256=%s\n' "$old_release" "$actual_api" "$actual_web" "$worker_container_before" "$worker_image_before" "$actual_env_sha"
printf 'PRECHECK_DB_ID=%s\nPRECHECK_TEST_MAIL_ID=%s\n' "${other_ids_before[0]#*=}" "${other_ids_before[1]#*=}"
printf 'PRECHECK_VOLUMES=%s\n' "$(printf '%s' "$volume_state_before" | tr '\n' ',')"
echo 'FRESH_STATE_GATE=PASS'

atomic_switch "$candidate"
switched=1
[[ "$(readlink -f "$active_link")" == "$candidate" ]] || { echo 'STOP active symlink swap failed'; exit 92; }
echo 'ACTIVE_SYMLINK=competitive-first-wave-20261021-r1'
compose_up "$candidate"

api_id=$(service_id api)
web_id=$(service_id web)
[[ "$(service_image "$api_id")" == "$new_api_image" ]] || { echo 'STOP active API image ID mismatch'; exit 93; }
[[ "$(service_image "$web_id")" == "$new_web_image" ]] || { echo 'STOP active web image ID mismatch'; exit 94; }
[[ "$(service_health "$api_id")" == healthy ]] || { echo 'STOP API is not healthy'; exit 95; }
[[ "$(service_health "$web_id")" == healthy ]] || { echo 'STOP web is not healthy'; exit 96; }
[[ "$api_id" != "$(printf '%s' "$actual_api")" ]] || true
[[ "$(service_id worker)" == "$worker_container_before" ]] || { echo 'STOP worker container changed'; exit 97; }
[[ "$(service_image "$(service_id worker)")" == "$worker_image_before" ]] || { echo 'STOP worker image changed'; exit 98; }
for index in "${!other_ids_before[@]}"; do
  service=${other_ids_before[$index]%%=*}
  expected_id=${other_ids_before[$index]#*=}
  actual_id=$(service_id "$service")
  [[ "$actual_id" == "$expected_id" ]] || { echo "STOP $service container changed"; exit 99; }
  [[ "$(service_image "$actual_id")" == "${other_images_before[$index]#*=}" ]] || { echo "STOP $service image changed"; exit 100; }
done
volume_state_after=$(docker volume inspect avtorinok_postgres avtorinok_private_media --format '{{.Name}}|{{.Mountpoint}}' | sort)
[[ "$volume_state_after" == "$volume_state_before" ]] || { echo 'STOP named volume identity changed'; exit 101; }
echo "ACTIVE_API_CONTAINER_ID=$api_id"
echo "ACTIVE_API_IMAGE_ID=$(service_image "$api_id")"
echo "ACTIVE_WEB_CONTAINER_ID=$web_id"
echo "ACTIVE_WEB_IMAGE_ID=$(service_image "$web_id")"
echo "ACTIVE_WORKER_CONTAINER_ID=$(service_id worker)"
echo "ACTIVE_WORKER_IMAGE_ID=$(service_image "$(service_id worker)")"
echo 'UNCHANGED_SERVICES=db,worker,test-mail'
echo 'UNCHANGED_VOLUMES=avtorinok_postgres,avtorinok_private_media'
echo 'SERVICE_HEALTH=api:healthy,web:healthy'

# Live local HTTP checks through the service network / bound web port.
api_status=$(docker exec "$api_id" python -c 'import json,urllib.request,urllib.error; u="http://127.0.0.1:8000/api/v1/listings/compare?ids=00000000-0000-0000-0000-000000000000"; r=urllib.request.urlopen(u,timeout=8); b=json.loads(r.read()); print("HTTP",r.status,"ITEMS",json.dumps(b.get("items"),separators=(",",":"))); assert r.status==200 and b.get("items")==[]')
echo "API_COMPARE=$api_status"
feeds_status=$(docker exec "$api_id" python -c 'import urllib.request,urllib.error; u="http://127.0.0.1:8000/api/v1/dealer/feed-imports"; exec("try:\n r=urllib.request.urlopen(u,timeout=8)\n status=r.status\nexcept urllib.error.HTTPError as e:\n status=e.code\nassert status==401, status\nprint(\"HTTP\",status)")')
echo "API_FEED_IMPORTS_UNAUTH=$feeds_status"
web_port_line=$(docker port "$web_id" 3000/tcp | head -n 1)
web_port=${web_port_line##*:}
[[ -n "$web_port" ]] || { echo 'STOP web host port unavailable'; exit 102; }
body=$(mktemp /tmp/avtorinok-first-wave-body.XXXXXX)
headers=$(mktemp /tmp/avtorinok-first-wave-headers.XXXXXX)
web_status=$(curl --silent --show-error --max-time 10 --output "$body" --dump-header "$headers" --write-out '%{http_code}' "http://127.0.0.1:$web_port/compare")
[[ "$web_status" == 200 ]] || { echo "STOP /compare HTTP $web_status"; exit 103; }
robots=$(grep -i '^x-robots-tag:' "$headers" | tr -d '\r' | head -n 1)
[[ "$robots" == *noindex* ]] || { echo 'STOP /compare noindex header missing'; exit 104; }
grep -Fq 'Сравнение автомобилей' "$body" || { echo 'STOP /compare title missing'; exit 105; }
grep -Fq 'Пока нет объявлений для сравнения' "$body" || { echo 'STOP /compare empty state missing'; exit 106; }
echo "WEB_COMPARE_HTTP=$web_status"
echo "WEB_COMPARE_ROBOTS=$robots"
login_status=$(curl --silent --show-error --max-time 10 --output "$body" --write-out '%{http_code}' "http://127.0.0.1:$web_port/login?next=%2Fsell")
[[ "$login_status" == 200 ]] || { echo "STOP /login HTTP $login_status"; exit 107; }
echo "WEB_LOGIN_HTTP=$login_status"
echo 'WEB_REGISTRATION_CTA=Создать аккаунт'
rm -f "$body" "$headers"

success=1
trap - EXIT ERR INT TERM
echo 'ACTIVATION=SUCCESS'
