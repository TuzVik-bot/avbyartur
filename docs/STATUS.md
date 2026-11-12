# Статус production — «Авторынок»

Сводка на 11 ноября 2026, около 00:38 по Минску (2026-11-10T21:38Z), по проверкам после выкатки релиза `audit-20261111-r1` и журналам в `docs/releases/2026/`. Это записанное состояние, а не живая проверка: перед любыми действиями на VPS сверить его заново (read-only), см. `AGENTS.md`.

## Текущий production: generation-20261112-r1 (web-only, 12 ноября 2026)

Поверх `audit-20261111-r1` выкачен только web: поле «Поколение» перенесено из «Дополнительных параметров» в «Параметры поиска» сразу после «Марки»/«Модели».

| Компонент | Значение |
|---|---|
| Активный каталог | `/home/suite/apps/avtorinok` → `/home/suite/apps/releases/generation-20261112-r1` |
| Исходники | ветка `prod-sync-20261110`, коммит `257fd4b`; sha256 архива — `12f5b8adf1aab281ed53a3a719cd113ee2e4fc813df1885a5d560b7ec029fca0` |
| Web | `avtorinok-web:generation-20261112-r1` (`sha256:d198bdaca538…`) |
| API, worker, db, test-mail | без изменений (api/worker `avtorinok-api:audit-20261111-r1`, контейнеры не пересоздавались) |
| Compose-цепочка | 17 файлов `audit-20261111-r1` + 18-й `docker-compose.generation.yml` (только образ web; создаётся на сервере, `docker-compose.audit.yml` скопирован из каталога audit) |

Бэкап: `/home/suite/backups/avtorinok/generation-20261112-r1/` (`database.dump` 23 634 900 байт, `pg_restore -l` — 534 записи; `before.json`, `built.json`, `build.log`, `deploy-failed.json` первой попытки, `deployed.json`). Прежний web-образ также помечен `avtorinok-web:rollback-generation-20261112-r1`. Журнал: [RELEASE_2026-11-12-generation.md](releases/2026/RELEASE_2026-11-12-generation.md).

Ниже — запись о базовом релизе `audit-20261111-r1`; она остаётся верной для api/worker/db.

## Базовый релиз: audit-20261111-r1

| Компонент | Значение |
|---|---|
| Активный каталог | `/home/suite/apps/avtorinok` → `/home/suite/apps/releases/audit-20261111-r1` |
| Исходники | ветка `prod-sync-20261110`, коммит `fd3158fd72c5b5a0f83c46c301464ded943f7ee2`; sha256 архива `git archive` — `d8def7286d14ca9b29345bd4023cdf107a42a2fe324622b913f5e8200e0df572` |
| API и worker | `avtorinok-api:audit-20261111-r1` (`sha256:4b9ca907fb1e…`) |
| Web | `avtorinok-web:audit-20261111-r1` (`sha256:c47ae3ddea74…`) |
| БД | PostgreSQL `postgres:17.11-alpine`, Alembic head `0034_listing_search_perf` (применена при выкатке, из `0033_listing_in_transit`) |
| Прочие сервисы | `db`, `test-mail` (Mailpit, внешняя доставка писем не подключена) — при выкатке не пересоздавались, `StartedAt` у db прежний (2026-10-26) |
| Тома | `avtorinok_postgres`, `avtorinok_private_media` — не удалять и не пересоздавать |
| `.env` | symlink на тот же защищённый файл, что и раньше (mode 600), содержимое не менялось |

Журнал релиза: [RELEASE_2026-11-11-audit.md](releases/2026/RELEASE_2026-11-11-audit.md). Скрипты выкатки: [scripts/release/audit-20261111-r1/](../scripts/release/audit-20261111-r1/README.md).

Проверки после выкатки (11 ноября 2026): 12 автоматических проверок скрипта деплоя пройдены; 0 событий уровня error в логах api и worker после старта; `/health/ready` — `ok`, heartbeat воркера 7–9 с; снаружи: главная 200 с заголовком «Автомобили Беларуси», заголовки CSP, `Permissions-Policy`, HSTS на месте, `/login?next=%2Fsell` показывает «Войти»/«Создать аккаунт» и поля регистрации. Подробно — в журнале релиза и `TESTING.md`.

## Предыдущий релиз

До 11 ноября 2026 активным был каталог `refero-20261108-r1`: web `avtorinok-web:refero-20261108-r1` (`sha256:6abbafbea5e1…`, [журнал](releases/2026/RELEASE_2026-11-08-refero.md)), api и worker `avtorinok-api:editorial-ux-20261102-r1` (`sha256:4772556fff67…`, [журнал](releases/2026/RELEASE_2026-11-02-editorial-ux.md)), head `0033_listing_in_transit`. На эти цепочки возвращает откат, см. `ROLLBACK.md`. Каталоги прежних релизов не удалялись.

## Что требует root или решения владельца

Релиз `audit-20261111-r1` этого не сделал:

- **nginx `real_ip` не применён.** Nginx видит всех клиентов как LAN-адрес OpenResty. Лимиты по IP поэтому работают в режиме «IP неизвестен» (×20) как общие на весь сайт. Лимиты по email и по токену работают полностью. Нужен root и проверка, что OpenResty передаёт IP клиента.
- **systemd-юниты не установлены.** Юниты монитора (новый base-url, Telegram-алерты) и ежедневного шифрованного offsite-бэкапа лежат в `deploy/systemd/`. Для установки нужны root, `/etc/avtorinok/monitor-alerts.env`, `/etc/avtorinok/offsite-backup.env`, `age` и SSH-ключ для хоста бэкапов. До этого монитор на хосте работает по старому unit.
- **Платёжный провайдер выключен** — решение бизнеса.
- **CSP без nonce** для `script-src`.
- **Digest образа postgres не закреплён**: смена ссылки пересоздаст контейнер БД, только в окне обслуживания.
- **Крупный рефакторинг не сделан**: `sell-form`, `worker`, `api/listings`.
- **118 предупреждений ESLint** — бэклог.
- **API `verified_evidence`** (`listing_trust_evidence`) не восстановлен.
- **Страница проверки по VIN** — по-прежнему заглушка.
- **Ветки.** `prod-sync-20261110` не отправлена на GitHub. `main` и его незакоммиченное рабочее дерево в `/Users/home/Downloads/avbyartur` по-прежнему содержат расходящуюся линию с функциями, которых никогда не было в production: эндпоинт рыночной оценки, канал уведомлений Telegram, настроенный платёжный провайдер. Нужно решение, переносить ли их на `prod-sync-20261110`.

## Хосты и домен

- Публичный домен: <https://авторынок.бел> (`xn--80aeylebmo7f.xn--90ais`).
- Цепочка: внешний OpenResty (TLS) → nginx vhost `/etc/nginx/sites-available/avtorinok-domain` (копия — `deploy/avtorinok-domain.nginx.conf`) → `127.0.0.1:8080` (web) → `api:8000` в docker-сети `app`. API и PostgreSQL наружу не опубликованы.
- VPS: `178.124.211.251`, SSH через локальный alias `fortebit-prod` (пользователь `suite`). Подробности — `SERVER.md`.
- `suite-s1.denjik.by` принадлежит соседнему проекту AURUM; для «Авторынка» не использовать.

## Compose-цепочка

Проект `avtorinok`, `--project-directory` = каталог релиза, файлы по порядку (последний выигрывает). Те же 16 файлов, что у `refero-20261108-r1` (теперь из каталога нового релиза), и 17-м — `docker-compose.audit.yml` (в репозитории его нет: его создаёт в каталоге релиза `10-prepare-server.py`):

```sh
docker compose -p avtorinok --project-directory /home/suite/apps/releases/audit-20261111-r1 \
  -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml \
  -f docker-compose.feedback.yml -f docker-compose.yandex.yml -f docker-compose.google.yml \
  -f docker-compose.seo-sorting.yml -f docker-compose.full.yml -f docker-compose.registry.yml \
  -f docker-compose.editorial.yml -f docker-compose.footer.yml -f docker-compose.card-borders.yml \
  -f docker-compose.button-spacing.yml -f docker-compose.content-pages.yml \
  -f docker-compose.headlights.yml -f docker-compose.refero.yml -f docker-compose.audit.yml <команда>
```

Без полного списка `-f` Compose соберёт другую конфигурацию. Точный список записан в квитанциях `deployed.json` и `rollback.json` (каталог бэкапа, см. ниже) и в метке `com.docker.compose.project.config_files` контейнеров.

## Откат

Порядок и предупреждения — в `ROLLBACK.md`. Кратко:

1. Бэкап перед выкаткой: `/home/suite/backups/avtorinok/audit-20261111-r1/` — `database.dump` (23 493 915 байт, прочитан `pg_restore -l`, 527 записей TOC), файл sha256, `before.json`, `prepared.json`, `env-diff.json`, `built.json`, `deployed.json`, `rollback.json`.
2. Прежние образы сохранены как `avtorinok-api:rollback-audit-20261111-r1` и `avtorinok-web:rollback-audit-20261111-r1`.
3. Откат приложения — `90-rollback-server.py` (api из цепочки `editorial-ux-20261102-r2`, worker из цепочки `editorial-ux-20261102-r1`, web из цепочки `refero-20261108-r1`, ссылка возвращается на `refero-20261108-r1`).
4. БД не откатывается: `0034` аддитивна и совместима со старыми образами.

## Логи и мониторинг

- Логи контейнеров: `docker compose -p avtorinok <полная цепочка -f> logs --tail=200 <service>` из активного каталога; сервисы `web`, `api`, `worker`, `db`, `test-mail`.
- Здоровье: Docker healthchecks; API `/health/live` и `/health/ready` (внутри сети `app`); nginx `/healthz` на домене.
- Админский снимок метрик: `GET /api/v1/admin/monitoring` и страница `/admin/monitoring` — [docs/runtime/monitoring.md](runtime/monitoring.md).
- Хостовый монитор и ежедневный бэкап: unit'ы `avtorinok-monitor.{service,timer}` и `avtorinok-backup.{service,timer}` (копии в `deploy/systemd/`); статус монитора — `/var/lib/avtorinok-monitor/status.json`, бэкапы — `/home/suite/backups/avtorinok/`. На 11 ноября 2026 монитор на хосте работает по старому unit; новые unit'ы монитора и offsite-бэкапа (`avtorinok-offsite-backup.{service,timer}`) из `deploy/systemd/` не установлены (нужен root). Наличие ежедневного `avtorinok-backup` на VPS проверять отдельно.
- Процедуры: [runbook](runtime/runbook.md), [backup/restore](runtime/backup-restore.md), [off-host backup](runtime/off-host-backup.md).
