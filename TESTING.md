# TESTING — журнал проверок

Бегущий лог: «как мы знаем, что это работает». Новые разделы добавляются сверху.

## 2026-10-22 — read-only проверка production по SSH

### SSH (read-only, разрешён пользователем)

- Активный симлинк `/home/suite/apps/avtorinok` → `releases/product-wave-articles-20261022-r1`.
- web = `avtorinok-web:product-wave-articles-20261022-r1` (из articles-r1); api/worker = `avtorinok-api:product-wave-20261021-r1` (из `releases/product-wave-20261021-r1`).
- 5 контейнеров healthy, RestartCount 0.
- Тома `avtorinok_postgres` и `avtorinok_private_media` на месте.
- `.env` права 600 (симлинк на `releases/home-ux-20261016-r1/.env`).

### БД

- `alembic_version` = `0032_listing_price_hist` (подтверждено).
- listings: draft 108, paused 102, pending_review 1, active 0.
- `listing_price_events` 0; `catalog_makes` 211.

### HTTP

- Главная 200, `X-Robots-Tag: noindex, nofollow, noarchive`, Basic Auth нет; `/api/v1/listings` 200.
- С самого сервера curl к публичному домену вернул 000 (не исследовано).

### Сверка исходников

sha256, `backend/app`, `backend/alembic`, `web/src`; py/ts/tsx/css.

- Релиз articles-r1: 470/470 файлов идентичны коммиту dc41a9e (реконструкция подтверждена побайтово).
- Релиз product-wave-20261021-r1: 467/469 идентичны; 2 отличия — файлы статей, которые обновил web-релиз 22.10 (ожидаемо).
- Отличия integrate HEAD от прода — только коммиты после реконструкции: защиты миграций 0027/0028/0031 и `env.py`, документация статусов в `main.py`, тесты, `types.generated.ts`.

### Наблюдение

- В проде запущен test-mail (mailpit).

## 2026-10-22 — интеграция integrate/20261022 (реконструкция прод-исходника)

### 1. Что проверялось и источник истины

Дерево коммита dc41a9e собрано из трёх частей:

- `merge-first-wave-20261021` (полное дерево);
- оверлей `product-wave-source.tar.gz` (sha256 `4fb7cf57a83e3fedcedc15a516c098735c2bf1269d29e3c352edd5afdcaa62d0`, совпал с `release-manifest.json`);
- оверлей статей `avtorinok-articles-overlay-20261022-r1.tar.gz`.

Побайтовая сверка коммита с собранным деревом: все файлы совпали, кроме намеренно исключённых релизных артефактов (`overlay/`, `deploy-backup/`, `*.tar.gz`).

### 2. Аналитика веток

- 15 веток `codex/*`: все, кроме двух, поглощены luna/прод-деревом.
- Не поглощены: `makes-directory` (listing_count на марку) и индексация (4400788, не перенесена: правило noindex).
- Редизайн из `origin/main` (до 0753afa) в проде отсутствует с 15.10 и в ветку не включён.

### 3. Backend

- Команда: `uv run --offline pytest` на одноразовом PostgreSQL 17.11 (docker, 127.0.0.1:55433, БД `*_test`).
- Результат: 698 passed, exit 0, 105 с.
- Повторный прогон с `TZ=UTC`: тот же результат.
- Исходно было 33 падения: все из-за устаревших тестов (контракты прода). Исправлены тесты, код не менялся.
- Один тест зависел от локальной TZ (`date.today`), переведён на UTC.

### 4. Web

- `corepack pnpm test`: 646 passed / 6 skipped / 0 failed (115 файлов). Skipped: 6 тестов sell-form на нереализованную фичу ручного каталога/вариантов кузова.
- `pnpm typecheck`: exit 0.
- `next build --webpack`: exit 0 (SITE_ORIGIN канонический, API на заглушку 127.0.0.1:9).
- `generate:api-types`: diff отсутствует, типы синхронны.

### 5. Миграции

- Одна голова: `0032_listing_price_hist`.
- `upgrade head` на пустой БД: OK (до фикса 96a7008 падал на 0027).
- `downgrade 0026` -> `upgrade head`: OK.
- Имитация реальной БД уровня 0026 (вручную удалены объекты 0027-0032), затем пошаговый `upgrade +1` x6: восстановлены все 5 таблиц, 6 колонок, 14 индексов, уникальные/FK/check-ограничения.
- `alembic check`: остаточный дрейф только по 9 индексам (`ix_listing_photo_phash_band_*` нечётные, `ix_dealer_external_listing_keys_missing_since`): не объявлены в моделях. Известно, не исправлялось.

### 6. Compose и каталог

- `docker compose config --quiet` с dummy `POSTGRES_PASSWORD`/`SESSION_SECRET`: rc=0.
- `data/catalog.json` валиден.

### 7. Безопасность

- grep по секретам/ключам/токенам: чисто.
- `.env` в дереве нет.
- Глобальный noindex сохранён.

### 8. НЕ проверено

- SSH и реальное состояние VPS (доступ заблокирован в сессии).
- Миграция 0032 на копии прод-данных.
- Браузерный smoke.
- Патчи `docs/runtime/catalog-pack-0*.patch` и `category-navigation*.patch` не входят ни в один исходник (вероятно, не на проде).
- `/admin/content` (managed articles) не выводится на публичные страницы.
- `compare-button.tsx` — мёртвый код.

### 9. Как повторить

Секреты в репозитории не хранятся; env-файл с паролем тестовой БД лежит вне репозитория.

```bash
# одноразовая БД
docker run -d --rm --name pg-test -p 127.0.0.1:55433:5432 \
  -e POSTGRES_PASSWORD="$TEST_DB_PASSWORD" postgres:17

# backend
cd backend
set -a; . "$TEST_ENV_FILE"; set +a   # внешний env-файл с DATABASE_URL тестовой БД
uv run --offline pytest
TZ=UTC uv run --offline pytest

# миграции
alembic heads
alembic upgrade head
alembic downgrade 0026 && alembic upgrade head
alembic check

# web
cd ../web
corepack pnpm test
corepack pnpm typecheck
corepack pnpm exec next build --webpack
corepack pnpm generate:api-types && git diff --exit-code

# compose
POSTGRES_PASSWORD=dummy SESSION_SECRET=dummy docker compose config --quiet
python -m json.tool data/catalog.json > /dev/null
```
