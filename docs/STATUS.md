# Статус production — «Авторынок»

Сводка на 10 ноября 2026 по квитанции последнего релиза (`deployed.json`, 8 ноября 2026, 16:59 UTC) и журналам в `docs/releases/2026/`. Это записанное состояние, а не живая проверка: перед любыми действиями на VPS сверить его заново (read-only), см. `AGENTS.md`.

## Текущий релиз

| Компонент | Значение |
|---|---|
| Активный каталог | `/home/suite/apps/avtorinok` → `/home/suite/apps/releases/refero-20261108-r1` |
| Web | `avtorinok-web:refero-20261108-r1` (`sha256:6abbafbea5e1…`) — [журнал](releases/2026/RELEASE_2026-11-08-refero.md) |
| API и worker | `avtorinok-api:editorial-ux-20261102-r1` (`sha256:4772556fff67…`) — [журнал](releases/2026/RELEASE_2026-11-02-editorial-ux.md) |
| БД | PostgreSQL `postgres:17.11-alpine`, Alembic head `0033_listing_in_transit` |
| Прочие сервисы | `db`, `test-mail` (Mailpit, внешняя доставка писем не подключена) |
| Тома | `avtorinok_postgres`, `avtorinok_private_media` — не удалять и не пересоздавать |
| Исходники | ветка `prod-sync-20261110`, базовый коммит `651f75d` = точная копия релиза |

Ветка `prod-sync-20261110` уже содержит миграцию `0034_listing_search_perf` и исправления по `AUDIT_REPORT.md`; они **не** выкачены. API-контейнер монтирует `data/` из каталога `editorial-ux-20261102-r2` (web-only релизы с `--no-deps` его не перезапускали).

## Хосты и домен

- Публичный домен: <https://авторынок.бел> (`xn--80aeylebmo7f.xn--90ais`).
- Цепочка: внешний OpenResty (TLS) → nginx vhost `/etc/nginx/sites-available/avtorinok-domain` (копия — `deploy/avtorinok-domain.nginx.conf`) → `127.0.0.1:8080` (web) → `api:8000` в docker-сети `app`. API и PostgreSQL наружу не опубликованы.
- VPS: `178.124.211.251`, SSH через локальный alias `fortebit-prod` (пользователь `suite`). Подробности — `SERVER.md`.
- `suite-s1.denjik.by` принадлежит соседнему проекту AURUM; для «Авторынка» не использовать.

## Compose-цепочка

Проект `avtorinok`, `--project-directory` = каталог релиза, файлы по порядку (последний выигрывает):

```sh
docker compose -p avtorinok --project-directory /home/suite/apps/releases/refero-20261108-r1 \
  -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml \
  -f docker-compose.feedback.yml -f docker-compose.yandex.yml -f docker-compose.google.yml \
  -f docker-compose.seo-sorting.yml -f docker-compose.full.yml -f docker-compose.registry.yml \
  -f docker-compose.editorial.yml -f docker-compose.footer.yml -f docker-compose.card-borders.yml \
  -f docker-compose.button-spacing.yml -f docker-compose.content-pages.yml \
  -f docker-compose.headlights.yml -f docker-compose.refero.yml <команда>
```

Список снят с метки `com.docker.compose.project.config_files` работающего web-контейнера. Без полного списка `-f` Compose соберёт другую конфигурацию.

## Откат

Порядок и предупреждения — в `ROLLBACK.md`. Кратко для текущего релиза (только web, без отката БД):

1. Резервная копия релиза: `/home/suite/backups/avtorinok/refero-20261108-r1/` — `database.dump` (23 488 140 байт, прочитан `pg_restore -l`), `rollback.json` с точной командой, `before.json`/`deployed.json`.
2. Прежний образ также сохранён как `avtorinok-web:rollback-refero-20261108-r1`.
3. Из каталога `headlights-header-20261102-r1` поднять web той же цепочкой **без** `docker-compose.refero.yml` с `up -d --no-deps --no-build --wait --wait-timeout 120 web`.
4. После проверки здоровья и регистрации атомарно вернуть ссылку `/home/suite/apps/avtorinok` на `/home/suite/apps/releases/headlights-header-20261102-r1`.

Откат API/worker на образы до `editorial-ux-20261102-r1` — по `/home/suite/backups/avtorinok/editorial-ux-20261102-r1/rollback.sh` (см. журнал editorial-ux). Миграции и импортированные данные откат приложения не отменяет.

## Логи и мониторинг

- Логи контейнеров: `docker compose -p avtorinok <полная цепочка -f> logs --tail=200 <service>` из активного каталога; сервисы `web`, `api`, `worker`, `db`, `test-mail`.
- Здоровье: Docker healthchecks; API `/health/live` и `/health/ready` (внутри сети `app`); nginx `/healthz` на домене.
- Админский снимок метрик: `GET /api/v1/admin/monitoring` и страница `/admin/monitoring` — [docs/runtime/monitoring.md](runtime/monitoring.md).
- Хостовый монитор и ежедневный бэкап: unit'ы `avtorinok-monitor.{service,timer}` и `avtorinok-backup.{service,timer}` (копии в `deploy/systemd/`); статус монитора — `/var/lib/avtorinok-monitor/status.json`, бэкапы — `/home/suite/backups/avtorinok/`. Установлены ли они на VPS сейчас — проверять отдельно.
- Процедуры: [runbook](runtime/runbook.md), [backup/restore](runtime/backup-restore.md), [off-host backup](runtime/off-host-backup.md).
