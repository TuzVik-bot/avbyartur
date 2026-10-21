# TESTING — журнал проверок

Бегущий лог: «как мы знаем, что это работает». Новые разделы добавляются сверху.

## 2026-10-22 — ветка next/20261022 (фичи поверх прод-паритета)

### Состав

`integrate/20261022` плюс слияния:

- `chore/drift-deadcode`: индексы phash/missing_since объявлены в моделях, поэтому `alembic check` без дрейфа; удалён мёртвый CompareButton.
- `test/migration-0032-data`: тест миграции 0032 на синтетической БД уровня 0031: upgrade, сохранность данных, check-ограничения, downgrade без данных, guard RuntimeError при наличии событий/opt-in/outbox.
- `feat/makes-listing-counts`: listing_count на /catalog/makes одним запросом, счётчики на /makes.
- `feat/catalog-packs`: category_code для makes/models; для cars скрыты строки пакетов NHTSA/Autorinok 01–05 (ИЗМЕНЕНИЕ ПОВЕДЕНИЯ относительно прода); подсказки марок/моделей в форме для не-легковых категорий при редактировании.
- `feat/managed-articles-public`: публичный API статей и вывод опубликованных статей из /admin/content на /useful-information/articles и в sitemap; fail-soft; /articles/[slug] теперь динамический.
- Исправление f1b86fe: SQL-пагинация списка статей, публичные серверные запросы без cookie, валидация slug, кэш загрузчика.

### Проверки

- backend: 720 passed, exit 0 (одноразовый PostgreSQL 17.11, отдельная БД для теста миграции);
- web: 667 passed / 6 skipped;
- typecheck: 0;
- `next build --webpack`: 0;
- `generate:api-types`: без diff;
- `alembic heads` = 0032;
- `alembic check`: без дрейфа.

### Ревью безопасности

CRITICAL/HIGH нет. Два MEDIUM (неограниченная загрузка статей, проброс cookie) исправлены в f1b86fe. Cache-Control статей оставлен no-store по конвенции проекта.

### Не проверено

Браузерный smoke, визуальная проверка, деплой. Новая ветка не на проде.

### Отдельно

`trial/redesign-on-prod-20261022`: пробное слияние редизайна origin/main поверх прода (typecheck/test 637+6 skip/build OK, визуально не проверено, удалены страницы категорий/financing из origin/main). Не входит в next.

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
