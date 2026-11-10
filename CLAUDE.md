# CLAUDE.md — «Авторынок» (avbyartur), production-линия

Краткая карта проекта для ИИ-ассистентов. Правила эксплуатации и история инцидентов — в `AGENTS.md` (обязателен к прочтению перед любыми удалёнными действиями). Текущий релиз и откат — `docs/STATUS.md`. Известные долги и план улучшений — `AUDIT_REPORT.md`.

## Источник истины

Ветка `prod-sync-20261110` — источник истины, совпадающий с production: релиз `audit-20261111-r1` (11 ноября 2026) собран из коммита `fd3158f` этой ветки (база ветки — коммит `651f75d`, копия релиза `refero-20261108-r1`). Ветка на GitHub не отправлена. Ветка `main` — другая, расходящаяся линия кода с функциями, которых нет в production (рыночная оценка, Telegram-канал, платёжный провайдер); не переносить из неё файлы целиком, только смысл исправлений, и только по решению владельца.

## Что это

Маркетплейс автомобилей и техники в Беларуси. Публичный домен: `авторынок.бел` (punycode `xn--80aeylebmo7f.xn--90ais`).
`suite-s1.denjik.by` — хост соседнего проекта AURUM. Не использовать его конфиги, web-root и URL для «Авторынка». Прежние пилотные конфиги suite-s1 лежат в `docs/archive/deploy/` только как история.

## Карта кода

- `backend/` — FastAPI + SQLAlchemy 2 + PostgreSQL 17 + Alembic (Python 3.12, `uv`).
  - `app/main.py` — приложение, middleware, обработчики ошибок, `/health/live` и `/health/ready`.
  - `app/api/*.py` — роутеры (`/api/v1/...`): listings, auth, account, profile_identity, conversations, saved_searches, notifications, billing, feeds, dealer, companies, media, moderation, monitoring, managed_content, catalog, catalog_requests, customs_calculator, admin, admin_catalog, admin_settings, admin_tariffs, test_mail.
  - `app/config.py` — единственный источник настроек (`Settings`, pydantic-settings).
  - `app/models.py`, `app/identity_models.py`, `app/profile_identity_models.py`, `app/catalog_request_models.py` — модели; `alembic/versions/` — миграции. Head в production — `0034_listing_search_perf` (`published_at`, trgm-индексы, таблица `worker_heartbeats`), применена 11 ноября 2026 релизом `audit-20261111-r1`.
  - `app/services.py` — поиск и сериализация объявлений; `app/worker.py` — фоновые задачи (варианты фото, письма identity и уведомлений, сопоставление сохранённых поисков, курс USD НБРБ, очистка по сроку хранения, Onliner sync); очередь `WorkerJob` с `SKIP LOCKED` и продлением lease; несколько воркеров безопасны. Каждый воркер пишет heartbeat в `worker_heartbeats` (`worker_id` = `hostname:pid`, строки старше 24 ч удаляются, сбой heartbeat только логируется как `worker_heartbeat_failed`); возраст показывает `/health/ready`.
  - `app/billing_services.py` — провайдер-нейтральные заказы и платёжный шов; по умолчанию закрыт (`PaymentProviderUnavailable`).
  - `app/security.py` — `client_ip` (доверяет `X-Forwarded-For` только от `TRUSTED_PROXY_CIDRS`), rate limits. Если IP клиента не определён (адрес совпадает с доверенным прокси), работает режим «IP неизвестен»: `ip_scoped_limit` умножает лимит на `UNKNOWN_CLIENT_IP_LIMIT_FACTOR` (×20) и пишет `client_ip_unresolved`. Так работает production, пока на хосте не применён nginx `real_ip` (на 11 ноября 2026 не применён).
  - `app/api/analytics.py` — `POST /api/v1/analytics/errors`: анонимные очищенные отчёты об ошибках фронтенда, только лог, лимит 30 в час на IP.
- `web/` — Next.js 16 App Router + React 19 + Tailwind 4 (pnpm через corepack).
  - `src/app/api/v1/[...path]/route.ts` — same-origin прокси браузер → API (allowlist заголовков).
  - `src/app/api/assistant/route.ts` + `src/lib/assistant-server.ts` — ИИ-помощник (OpenRouter, только модели `:free`; модель только планирует JSON, объявления берутся из API).
  - `src/lib/server-api.ts`, `src/lib/public-server-api.ts` — SSR-запросы к API; `src/lib/api.ts` — клиентский API; `src/lib/types.generated.ts` — генерируется из OpenAPI, вручную не править.
  - `src/proxy.ts` — Next middleware.
- `data/catalog.json` — каталог марок/моделей; `scripts/` — бэкап/restore, монитор, импорт каталога, сборка AMD64, релизные проверки; `deploy/avtorinok-domain.nginx.conf` и `deploy/systemd/` — копии vhost и unit'ов (применяются вручную только по явному запросу).
- Цепочка в production: внешний OpenResty (TLS) → nginx vhost `avtorinok-domain` → `127.0.0.1:8080` (web) → `api:8000` в docker-сети `app`. API и PostgreSQL наружу не публикуются.

## Production: релизы и Compose

- Каждый релиз — отдельный каталог `/home/suite/apps/releases/<tag>`; активный выбирается символической ссылкой `/home/suite/apps/avtorinok` → каталог релиза (переключение атомарно: `ln -s` во временное имя + `mv -Tf`).
- Compose-проект `avtorinok` запускается с `--project-directory` каталога релиза и цепочкой файлов, которые лежат в корне репозитория. Порядок (по квитанции `deployed.json` релиза `audit-20261111-r1`, источник — метки `com.docker.compose.project.config_files` контейнеров):
  `docker-compose.yml` → `override` → `public-launch` → `feedback` → `yandex` → `google` → `seo-sorting` → `full` → `registry` → `editorial` → `footer` → `card-borders` → `button-spacing` → `content-pages` → `headlights` → `refero` → `audit` (все — `docker-compose.<имя>.yml`, 17 файлов). `docker-compose.audit.yml` в репозитории нет: его пишет в каталог релиза на сервере `scripts/release/audit-20261111-r1/10-prepare-server.py`.
  Каждый overlay лишь закрепляет теги образов (и пару env/build-args); последний по порядку выигрывает. Итог: api/worker — `avtorinok-api:audit-20261111-r1`, web — `avtorinok-web:audit-20261111-r1` (оба из `audit`).
- Новый релиз = новый каталог + новый overlay в конце цепочки; команды выполнять с полным списком `-f`, иначе Compose соберёт другую конфигурацию. Точные команды и откат — `docs/STATUS.md` и журналы `docs/releases/2026/`.
- Сборка образов: `make release-amd64` (`scripts/build-amd64-images.sh`, тег из `AVTORINOK_IMAGE_TAG`, только `linux/amd64`, затем передача на VPS) или сборка на самом VPS из каталога релиза (`docker build ... -f web/Dockerfile`, как в `refero-20261108-r1`, или `docker compose … build api web`, как `20-build-server.py` в `audit-20261111-r1`). Web-образ собирать с `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` (build-arg), иначе сайт уйдёт в `noindex`. Перед релизом — `scripts/release-preflight.sh`.

## Команды

- Backend-тесты: `cd backend && uv run pytest`. Обязательно задать `TEST_DATABASE_URL` на отдельную одноразовую PostgreSQL-БД с именем `*_test` и `TEST_DATABASE_DISPOSABLE_CONFIRMATION` = точное имя этой БД. Фикстура удаляет все таблицы. Никогда не направлять на preview-БД `avtorinok_preview_20260927_00aa22_test`.
- Web: `cd web && corepack pnpm test | typecheck | lint | build | generate:api-types`. `corepack pnpm lint` должен завершаться с кодом 0; предупреждения — бэклог.
- Цели Makefile: `make test-backend` (нужны те же `TEST_DATABASE_*`), `make test-web`, `make test-scripts` (`python3 -m unittest discover -s scripts`), `make lint` (ruff + ESLint), `make typecheck`.
- CI: `.github/workflows/ci.yml` — web typecheck/lint/test/build/`pnpm audit --prod`, backend ruff + pytest на PostgreSQL 17, тесты `scripts/`, `docker compose config`.
- Конфиг compose и JSON каталога: `make config-check`. Локальный стек: `make up` (`AVTORINOK_IMAGE_TAG=local`, только базовый `docker-compose.yml`).

## Инварианты (нарушать нельзя)

- Никогда `docker compose down -v`; не удалять и не пересоздавать тома `avtorinok_postgres`, `avtorinok_private_media`.
- Не читать и не выводить значения `.env`; права файла на хосте — `600`.
- Без отдельного явного запроса пользователя: никаких deploy, push, миграций на VPS, импорта, restore, правок Nginx. Перед push/deploy — показать diff и дождаться явного «ок».
- Не заливать синтетические/тестовые данные на VPS; не трогать приостановленное smoke-объявление.
- После web-релиза проверить регистрацию в браузере на `/login?next=%2Fsell` (см. `AGENTS.md`).
- `noindex`/индексация управляется `AVTORINOK_PUBLIC_INDEXING_ENABLED` при сборке образа web.

## Правила изменений

- Новая настройка: поле в `backend/app/config.py` → переменная в блоке `x-backend-env` в `docker-compose.yml` (его получают и api, и worker) → `.env.example`. Синхронность проверяет `backend/tests/test_compose_settings.py`.
- Образ БД — ровно `postgres:17.11-alpine`. Смена ссылки, включая digest, пересоздаст контейнер БД при `up`; это делается только в окне обслуживания.
- Изменение API: обновить роутер и схемы, затем `corepack pnpm generate:api-types` в `web/`.
- Деньги и таможня — только `Decimal`. Даты для пользователя — в часовом поясе `Europe/Minsk`.
- Тексты для пользователя — на русском; ошибки API не показывать пользователю как есть.
- Ограничения по IP работают только при корректной передаче IP по цепочке nginx → web-прокси → API.
- `output/`, скриншоты и `.patch` не коммитить.

## Где искать состояние

- Текущий релиз, откат, логи, мониторинг: `docs/STATUS.md`, `ROLLBACK.md`.
- Эксплуатация: `docs/runtime/runbook.md`, `docs/runtime/monitoring.md`, `docs/runtime/backup-restore.md`, `SERVER.md`, `DEPLOYMENT.md` (журнал, частично исторический).
- Релизные журналы: `docs/releases/2026/` (текущий — `RELEASE_2026-11-11-audit.md`). Устаревшие конфиги и отчёты: `docs/archive/`.
- Скрипты выкатки `audit-20261111-r1`: рабочая копия в `output/audit-release-20261111-r1/` (в `.gitignore`, вместе с `src.tar.gz`); её не удалять. Копия в git — `scripts/release/audit-20261111-r1/` (`00-local.sh`, `10/20/30/40/90-*.py`, `README.md`); откат — `90-rollback-server.py`, см. `ROLLBACK.md`.
- Журнал проверок: `TESTING.md`. Аудит и долги: `AUDIT_REPORT.md`.
