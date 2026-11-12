# Откат приложения

## Откат web-релиза generation-20261112-r1 (12 ноября 2026)

Текущий web — `avtorinok-web:generation-20261112-r1` из `/home/suite/apps/releases/generation-20261112-r1`. Чтобы вернуть web на `audit-20261111-r1` (api/worker/db не трогаются):

```sh
cd /home/suite/apps/releases/audit-20261111-r1 && docker compose -p avtorinok --project-directory "$PWD" \
  -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml \
  -f docker-compose.feedback.yml -f docker-compose.yandex.yml -f docker-compose.google.yml \
  -f docker-compose.seo-sorting.yml -f docker-compose.full.yml -f docker-compose.registry.yml \
  -f docker-compose.editorial.yml -f docker-compose.footer.yml -f docker-compose.card-borders.yml \
  -f docker-compose.button-spacing.yml -f docker-compose.content-pages.yml \
  -f docker-compose.headlights.yml -f docker-compose.refero.yml -f docker-compose.audit.yml \
  up -d --no-deps --no-build --wait --wait-timeout 180 web
ln -s /home/suite/apps/releases/audit-20261111-r1 /home/suite/apps/.avtorinok.tmp && mv -Tf /home/suite/apps/.avtorinok.tmp /home/suite/apps/avtorinok
```

Этот путь проверен на практике: первая попытка выкатки 12 ноября автоматически откатилась им (из-за ошибочной проверки скрипта), web вернулся healthy. Затем проверить регистрацию в браузере на `/login?next=%2Fsell`.

Откат ниже (audit → refero) относится к базовому релизу.

Текущий релиз: `/home/suite/apps/releases/audit-20261111-r1` (api/worker `avtorinok-api:audit-20261111-r1`, web `avtorinok-web:audit-20261111-r1`, Alembic head `0034_listing_search_perf`). Выкачен 11 ноября 2026.
Предыдущий релиз: `/home/suite/apps/releases/refero-20261108-r1` (web `avtorinok-web:refero-20261108-r1`, api/worker `avtorinok-api:editorial-ux-20261102-r1`, head `0033_listing_in_transit`).
Бэкап: `/home/suite/backups/avtorinok/audit-20261111-r1/` (`database.dump` 23 493 915 байт, прочитан `pg_restore -l`, 527 записей TOC, файл sha256; `before.json`, `prepared.json`, `env-diff.json`, `built.json`, `deployed.json`, `rollback.json`).
Прежние образы дополнительно помечены тегами `avtorinok-api:rollback-audit-20261111-r1` и `avtorinok-web:rollback-audit-20261111-r1`. Каталоги прежних релизов не удалялись.

## Как откатить

Скрипт — `90-rollback-server.py` из `output/audit-release-20261111-r1/` (каталог в `.gitignore`); та же копия в git: [scripts/release/audit-20261111-r1/90-rollback-server.py](scripts/release/audit-20261111-r1/90-rollback-server.py). Запуск с локальной машины из корня репозитория:

```sh
ssh fortebit-prod python3 - < scripts/release/audit-20261111-r1/90-rollback-server.py
```

Что делает скрипт:

1. Читает `rollback.json` из каталога бэкапа. Там записаны точные прежние compose-цепочки: у api, worker и web они разные.
2. Если тег прежнего образа указывает на другой образ, возвращает его из тега `rollback-audit-20261111-r1`.
3. Поднимает api из цепочки `editorial-ux-20261102-r2`, worker из цепочки `editorial-ux-20261102-r1`, затем web из цепочки `refero-20261108-r1`: `up -d --no-deps --no-build --wait`.
4. Ждёт `healthy` на прежних id образов.
5. Атомарно возвращает ссылку `/home/suite/apps/avtorinok` на `/home/suite/apps/releases/refero-20261108-r1`.
6. Проверяет, что контейнер db не пересоздан и не перезапущен. Пишет `rolled-back.json` в каталог бэкапа.

Повторный запуск безопасен. Если скрипт недоступен, те же команды записаны в `rollback.json`.

## База данных

БД при откате **не** понижается. Схема остаётся на `0034_listing_search_perf`: миграция аддитивная (колонка `listings.published_at`, индексы, таблица `worker_heartbeats`) и совместима со старыми образами. Откат данных — только отдельным решением через `database.dump` и `docs/runtime/backup-restore.md`.

## После отката

- Проверить health сервисов и фактические id образов контейнеров.
- Проверить регистрацию в браузере на `/login?next=%2Fsell` (см. `AGENTS.md`).
- Тома не удалять, `docker compose down -v` не выполнять.

Более старые откаты описаны в журналах `docs/releases/2026/`. Прежняя версия этого файла (откат `refero-20261108-r1` → `headlights-header-20261102-r1`) устарела.
