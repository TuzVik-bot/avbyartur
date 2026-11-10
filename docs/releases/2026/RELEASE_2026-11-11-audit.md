# Релиз audit-20261111-r1 — 11 ноября 2026

Выкатка исправлений по `AUDIT_REPORT.md` на production. Завершена 11 ноября 2026, около 00:38 по Минску (2026-11-10T21:38Z).

## Релиз

- Активный каталог: `/home/suite/apps/avtorinok` → `/home/suite/apps/releases/audit-20261111-r1`.
- Исходники: ветка `prod-sync-20261110`, коммит `fd3158fd72c5b5a0f83c46c301464ded943f7ee2`. Архив `git archive`, sha256 `d8def7286d14ca9b29345bd4023cdf107a42a2fe324622b913f5e8200e0df572`.
- Образы: `avtorinok-api:audit-20261111-r1` (`sha256:4b9ca907fb1e…`, api и worker), `avtorinok-web:audit-20261111-r1` (`sha256:c47ae3ddea74…`).
- Не пересоздавались: `db` (`postgres:17.11-alpine`, `StartedAt` прежний — 2026-10-26) и `test-mail`.
- Миграция: `0033_listing_in_transit` → `0034_listing_search_perf` (head).
- Compose: те же 16 файлов, что у `refero-20261108-r1` (теперь из каталога нового релиза), и 17-м — `docker-compose.audit.yml`. Полная команда — `docs/STATUS.md`.
- `.env`: symlink на тот же защищённый файл (mode 600), содержимое не менялось.
- Скрипты выкатки: `output/audit-release-20261111-r1/` (в `.gitignore`), копия в git — [scripts/release/audit-20261111-r1/](../../../scripts/release/audit-20261111-r1/README.md).

## Что изменилось

База — релиз `refero-20261108-r1` (коммит `651f75d`). Изменения перенесены с `main` по смыслу, не файлами. Статус каждого пункта аудита — таблица «Статус исправлений» в `AUDIT_REPORT.md`.

**Безопасность.** next 16.4.5. Лимит логина проверяется до проверки пароля, отдельные счётчики по email и по IP. Лимиты восстановления по email/субъекту и общий потолок. GA только после согласия и не в приватных разделах. Токены убираются из URL. CSP (`frame-ancestors`, `object-src`, `base-uri`, `form-action`) и `Permissions-Policy`. Прокси отклоняет `.`, `..` и пустые сегменты. Режим «IP неизвестен» для лимитов по IP (×20).

**Надёжность.** Состояние `paid_unfulfilled` и алерт в мониторинге. Синхронная работа фидов и платёжного callback вынесена из event loop. Воркер без глобальной блокировки (`SKIP LOCKED`, продление lease), heartbeat в таблице `worker_heartbeats` (сбой heartbeat не останавливает цикл). Письма отправляются после снятия блокировок. Пул БД 15 + 10. Таймауты SSR-запросов. Даты по `Europe/Minsk`. `global-error.tsx`.

**Производительность.** Колонка `listings.published_at` с backfill и индексом, GIN trgm-индексы публичного поиска (миграция 0034). Публичные SSR-запросы без cookie, `Cache-Control` на справочниках.

**API.** Восстановлены эндпоинты, которые web уже вызывал и получал 404: отзывы о дилерах (с модерацией и жалобами), логотип компании (загрузка и выдача), фотобейджи модерации, `billing/listings/{id}/eligibility`. Новый `POST /api/v1/analytics/errors` (только лог). Исправлен 500 на странице дилера. Новой миграции для восстановленных эндпоинтов нет: модели совпадают с 0025/0030.

**Интерфейс.** Ошибки API показываются по-русски (`user-message.ts`). Бейдж «Цена снижена на …» и сортировка «Сначала подешевевшие» (`last_price_drop`). Подсказка рынка в «Моих объявлениях». Черновик и шаблоны сообщений продавцу. Похожие объявления для снятых.

**Импорт и фиды.** CSV в `cp1251`, XML через defusedxml, allowlist хостов изображений Onliner (синхронизация Onliner по-прежнему выключена).

**Эксплуатация.** api и worker получают все поля `Settings` через `x-backend-env` в compose. CI (`.github/workflows/ci.yml`), ESLint, ruff, Dependabot. `alembic upgrade head` работает на пустой БД.

### Переменные окружения

Сравнение с прежними контейнерами, только имена (`env-diff.json`):

- api: добавлено 10 переменных, все дают значения по умолчанию из `config.py`: `SESSION_COOKIE_NAME`, `SESSION_DAYS`, `PRIVATE_LISTING_QUOTA`, `COMPANY_LISTING_QUOTA`, `SAVED_SEARCH_LIMIT`, `SAVED_SEARCH_MUTATIONS_PER_HOUR`, `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_PIXELS`, `TRUSTED_PROXY_CIDRS`, `MONITORING_STATUS_PATH` (пустое).
- worker: получил полный набор `Settings`.
- web: добавлены `GA_MEASUREMENT_ID`, `ASSISTANT_FALLBACK_MODELS`, `ASSISTANT_DAILY_MODEL_BUDGET`.
- Ничего не удалено и не изменено. Флаги функций API совпадают. `/api/v1/auth/capabilities` до и после выкатки одинаков.

## Проверки

**До релиза** (прогон тимлида на коммите `fd3158f`): backend — 943 теста, 0 упавших; ruff чист; `unittest` скриптов OK; web typecheck чист; ESLint 0 ошибок, 118 предупреждений; vitest 875/875; `pnpm audit --prod` — 0 уязвимостей; production-сборка OK.

**Подготовка.** Очищены build cache старше 72 ч и dangling-образы: свободно 6,76 → 11,33 GiB.

**Автоматические проверки деплоя** (12, все пройдены): контейнеры healthy; db не изменился; образы совпадают с собранными; главная через nginx — заголовок «Автомобили Беларуси», нет AURUM, нет noindex; CSP с `frame-ancestors`; capabilities не изменились; страница объявлений; `catalog/makes` с `Cache-Control: max-age=300`; `/health/ready` — `ok` с heartbeat воркера (7–9 с); страница дилеров; несуществующее объявление — 404; `/login` — 200.

**Пост-проверка:** 0 событий уровня error в логах api и worker после старта; свободно на диске 9,38 GiB.

**Снаружи:**

- Главная — 200, правильный заголовок. Заголовки `Content-Security-Policy`, `Permissions-Policy`, HSTS на месте.
- `GET /api/v1/dealers/x/reviews/mine` — 401 (было 404: эндпоинт восстановлен).
- `sort=price_drop` — 200; `page=99999999` — 422; в объявлениях есть `last_price_drop`.
- Браузер (Chrome): `/login?next=%2Fsell` показывает «Войти» и «Создать аккаунт»; вкладка регистрации показывает поля имени, email, пароля и повтора пароля. Ничего не отправлялось, аккаунт не создавался.
- `/cars` — 889 объявлений; страница объявления отображается; в «Сначала подешевевшие» виден бейдж «Цена снижена на 600 USD».
- Ошибок в консоли на этих страницах нет.

## Бэкап и откат

- Бэкап перед выкаткой: `/home/suite/backups/avtorinok/audit-20261111-r1/` — `database.dump` (23 493 915 байт, прочитан `pg_restore -l`, 527 записей TOC), файл sha256, `before.json`, `prepared.json`, `env-diff.json`, `built.json`, `deployed.json`, `rollback.json`.
- Теги прежних образов: `avtorinok-api:rollback-audit-20261111-r1`, `avtorinok-web:rollback-audit-20261111-r1`. Каталоги прежних релизов не тронуты.
- Откат: `90-rollback-server.py` (или команды из `rollback.json`). api — из цепочки `editorial-ux-20261102-r2`, worker — из цепочки `editorial-ux-20261102-r1`, web — из цепочки `refero-20261108-r1`. БД не понижается: 0034 аддитивна и совместима со старыми образами. Подробно — `ROLLBACK.md`.

## Чего релиз не сделал

- nginx `real_ip` не применён. Nginx видит всех клиентов как LAN-адрес OpenResty. Лимиты по IP работают в режиме «IP неизвестен» (×20) как общие на весь сайт; лимиты по email и по токену работают полностью.
- systemd-юниты монитора (новый base-url, Telegram-алерты) и ежедневного шифрованного offsite-бэкапа лежат в `deploy/systemd/`, но не установлены. Нужны root, `/etc/avtorinok/monitor-alerts.env`, `/etc/avtorinok/offsite-backup.env`, `age` и SSH-ключ для хоста бэкапов. До этого монитор на хосте работает по старому unit.
- Платёжный провайдер выключен (решение бизнеса).
- CSP без nonce для `script-src`.
- Digest образа postgres не закреплён (отложено до окна обслуживания).
- Рефакторинг больших файлов (`sell-form`, `worker`, `api/listings`) не сделан.
- 118 предупреждений ESLint — бэклог.
- API `verified_evidence` (`listing_trust_evidence`) не восстановлен.
- Страница проверки по VIN — заглушка.
- Ветка `prod-sync-20261110` не отправлена на GitHub. `main` (и его незакоммиченное рабочее дерево в `/Users/home/Downloads/avbyartur`) содержит расходящуюся линию с функциями, которых не было в production: эндпоинт рыночной оценки, канал уведомлений Telegram, настроенный платёжный провайдер. Нужно решение, переносить ли их на `prod-sync-20261110`.
