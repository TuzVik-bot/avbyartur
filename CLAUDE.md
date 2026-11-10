# CLAUDE.md — «Авторынок» (avbyartur), production-линия

Краткая карта проекта для ИИ-ассистентов. Правила эксплуатации и история инцидентов — в `AGENTS.md` (обязателен к прочтению перед любыми удалёнными действиями). Текущий релиз и откат — `docs/STATUS.md`. Известные долги и план улучшений — `AUDIT_REPORT.md`.

## Источник истины

Ветка `prod-sync-20261110` — источник истины, совпадающий с production (базовый коммит `651f75d` = точная копия релиза `refero-20261108-r1`). Ветка `main` — другая, расходящаяся линия кода; не переносить из неё файлы целиком, только смысл исправлений.

## Что это

Маркетплейс автомобилей и техники в Беларуси. Публичный домен: `авторынок.бел` (punycode `xn--80aeylebmo7f.xn--90ais`).
`suite-s1.denjik.by` — хост соседнего проекта AURUM. Не использовать его конфиги, web-root и URL для «Авторынка». Прежние пилотные конфиги suite-s1 лежат в `docs/archive/deploy/` только как история.

## Карта кода

- `backend/` — FastAPI + SQLAlchemy 2 + PostgreSQL 17 + Alembic (Python 3.12, `uv`).
  - `app/main.py` — приложение, middleware, обработчики ошибок, `/health/live` и `/health/ready`.
  - `app/api/*.py` — роутеры (`/api/v1/...`): listings, auth, account, profile_identity, conversations, saved_searches, notifications, billing, feeds, dealer, companies, media, moderation, monitoring, managed_content, catalog, catalog_requests, customs_calculator, admin, admin_catalog, admin_settings, admin_tariffs, test_mail.
  - `app/config.py` — единственный источник настроек (`Settings`, pydantic-settings).
  - `app/models.py`, `app/identity_models.py`, `app/profile_identity_models.py`, `app/catalog_request_models.py` — модели; `alembic/versions/` — миграции. Head в production — `0033_listing_in_transit`; в этой ветке добавлена `0034_listing_search_perf` (на VPS ещё не применена).
  - `app/services.py` — поиск и сериализация объявлений; `app/worker.py` — фоновые задачи (варианты фото, письма identity и уведомлений, сопоставление сохранённых поисков, курс USD НБРБ, очистка по сроку хранения, Onliner sync); очередь `WorkerJob` с `SKIP LOCKED`.
  - `app/billing_services.py` — провайдер-нейтральные заказы и платёжный шов; по умолчанию закрыт (`PaymentProviderUnavailable`).
  - `app/security.py` — `client_ip` (доверяет `X-Forwarded-For` только от `TRUSTED_PROXY_CIDRS`), rate limits.
- `web/` — Next.js 16 App Router + React 19 + Tailwind 4 (pnpm через corepack).
  - `src/app/api/v1/[...path]/route.ts` — same-origin прокси браузер → API (allowlist заголовков).
  - `src/app/api/assistant/route.ts` + `src/lib/assistant-server.ts` — ИИ-помощник (OpenRouter, только модели `:free`; модель только планирует JSON, объявления берутся из API).
  - `src/lib/server-api.ts`, `src/lib/public-server-api.ts` — SSR-запросы к API; `src/lib/api.ts` — клиентский API; `src/lib/types.generated.ts` — генерируется из OpenAPI, вручную не править.
  - `src/proxy.ts` — Next middleware.
- `data/catalog.json` — каталог марок/моделей; `scripts/` — бэкап/restore, монитор, импорт каталога, сборка AMD64, релизные проверки; `deploy/avtorinok-domain.nginx.conf` и `deploy/systemd/` — копии vhost и unit'ов (применяются вручную только по явному запросу).
- Цепочка в production: внешний OpenResty (TLS) → nginx vhost `avtorinok-domain` → `127.0.0.1:8080` (web) → `api:8000` в docker-сети `app`. API и PostgreSQL наружу не публикуются.

## Production: релизы и Compose

- Каждый релиз — отдельный каталог `/home/suite/apps/releases/<tag>`; активный выбирается символической ссылкой `/home/suite/apps/avtorinok` → каталог релиза (переключение атомарно: `ln -s` во временное имя + `mv -Tf`).
- Compose-проект `avtorinok` запускается с `--project-directory` каталога релиза и цепочкой файлов, которые лежат в корне репозитория. Порядок (по `previous_config_files` и `compose_command` квитанции релиза `refero-20261108-r1`, источник — метки `com.docker.compose.project.config_files` контейнеров):
  `docker-compose.yml` → `override` → `public-launch` → `feedback` → `yandex` → `google` → `seo-sorting` → `full` → `registry` → `editorial` → `footer` → `card-borders` → `button-spacing` → `content-pages` → `headlights` → `refero` (все — `docker-compose.<имя>.yml`).
  Каждый overlay лишь закрепляет теги образов (и пару env/build-args); последний по порядку выигрывает. Итог: web — `avtorinok-web:refero-20261108-r1` (из `refero`), api/worker — `avtorinok-api:editorial-ux-20261102-r1` (из `editorial`).
- Новый релиз = новый каталог + новый overlay в конце цепочки; команды выполнять с полным списком `-f`, иначе Compose соберёт другую конфигурацию. Точные команды и откат — `docs/STATUS.md` и журналы `docs/releases/2026/`.
- Сборка образов: `make release-amd64` (`scripts/build-amd64-images.sh`, тег из `AVTORINOK_IMAGE_TAG`, только `linux/amd64`, затем передача на VPS) или сборка на самом VPS из каталога релиза (`docker build ... -f web/Dockerfile`, как в `refero-20261108-r1`). Web-образ собирать с `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` (build-arg), иначе сайт уйдёт в `noindex`. Перед релизом — `scripts/release-preflight.sh`.

## Команды

- Backend-тесты: `cd backend && uv run pytest`. Обязательно задать `TEST_DATABASE_URL` на отдельную одноразовую PostgreSQL-БД с именем `*_test` и `TEST_DATABASE_DISPOSABLE_CONFIRMATION` = точное имя этой БД. Фикстура удаляет все таблицы. Никогда не направлять на preview-БД `avtorinok_preview_20260927_00aa22_test`.
- Web: `cd web && corepack pnpm test | typecheck | build | generate:api-types`.
- Конфиг compose и JSON каталога: `make config-check`. Локальный стек: `make up` (`AVTORINOK_IMAGE_TAG=local`, только базовый `docker-compose.yml`).

## Инварианты (нарушать нельзя)

- Никогда `docker compose down -v`; не удалять и не пересоздавать тома `avtorinok_postgres`, `avtorinok_private_media`.
- Не читать и не выводить значения `.env`; права файла на хосте — `600`.
- Без отдельного явного запроса пользователя: никаких deploy, push, миграций на VPS, импорта, restore, правок Nginx. Перед push/deploy — показать diff и дождаться явного «ок».
- Не заливать синтетические/тестовые данные на VPS; не трогать приостановленное smoke-объявление.
- После web-релиза проверить регистрацию в браузере на `/login?next=%2Fsell` (см. `AGENTS.md`).
- `noindex`/индексация управляется `AVTORINOK_PUBLIC_INDEXING_ENABLED` при сборке образа web.

## Правила изменений

- Новая настройка: поле в `backend/app/config.py` → переменная в `docker-compose.yml` (api и, если нужно, worker) → `.env.example`, если он заведён в ветке.
- Изменение API: обновить роутер и схемы, затем `corepack pnpm generate:api-types` в `web/`.
- Деньги и таможня — только `Decimal`. Даты для пользователя — в часовом поясе `Europe/Minsk`.
- Тексты для пользователя — на русском; ошибки API не показывать пользователю как есть.
- Ограничения по IP работают только при корректной передаче IP по цепочке nginx → web-прокси → API.
- `output/`, скриншоты и `.patch` не коммитить.

## Где искать состояние

- Текущий релиз, откат, логи, мониторинг: `docs/STATUS.md`, `ROLLBACK.md`.
- Эксплуатация: `docs/runtime/runbook.md`, `docs/runtime/monitoring.md`, `docs/runtime/backup-restore.md`, `SERVER.md`, `DEPLOYMENT.md` (журнал, частично исторический).
- Релизные журналы: `docs/releases/2026/`. Устаревшие конфиги и отчёты: `docs/archive/`.
- Журнал проверок: `TESTING.md`. Аудит и долги: `AUDIT_REPORT.md`.
