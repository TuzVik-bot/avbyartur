# Инструкции проекта

## Структура и проверенные команды

- Корень проекта: `/Users/home/Downloads/avbyartur`. Git инициализирован 4 октября 2026; ветка `main`, `origin` — `https://github.com/TuzVik-bot/avbyartur.git`, репозиторий приватный. Перед изменениями проверяй `git status --short` и актуальный remote. Секреты, runtime-данные, лицензионные источники `data/licensed/` и локальные `.superpowers/` артефакты исключены из Git.
- FastAPI и интеграционные тесты: `backend/`; Next.js: `web/`; эксплуатационные сведения: `docs/runtime/runbook.md`, `DEPLOYMENT.md`, `SERVER.md`, `docs/IMPLEMENTATION_STATUS.md`.
- Backend tests: `cd backend && uv run pytest`. Перед запуском явно задай `TEST_DATABASE_URL` для выделенной одноразовой PostgreSQL БД с именем, оканчивающимся на `_test`, и `TEST_DATABASE_DISPOSABLE_CONFIRMATION`, равный точному имени этой БД. Фикстура до подключения проверяет PostgreSQL URL, известную preview-БД и совпадение с runtime-БД; затем создаёт и удаляет все таблицы.
- Не направляй тесты на preview-БД: документированная `avtorinok_preview_20260927_00aa22_test` также оканчивается на `_test` и содержит preview-данные.
- Web scripts из `web/package.json`: `cd web && corepack pnpm test`, `cd web && corepack pnpm typecheck`, `cd web && corepack pnpm generate:api-types`.
- Генератор типов строит OpenAPI из FastAPI и записывает результат в `web/src/lib/types.generated.ts`.
- Проверка Compose и JSON каталога: `make config-check` (цель из корневого `Makefile`).

## Локальные preview

- Текущий исходный preview использует `127.0.0.1:3003`, API — `127.0.0.1:8003`; на момент проверки оба порта слушали локально.
- Записи в `docs/IMPLEMENTATION_STATUS.md` также называют старый preview `3002 -> 8002`, production-build preview `3004 -> 8004` и acceptance `18080`. Перед использованием или остановкой любого preview проверь владельца порта безопасным read-only способом; не перезапускай чужой процесс. Preview может содержать синтетические тестовые объявления; они предназначены только для изолированной локальной БД.

## Данные и production

- По явному запросу пользователя 4 октября 2026 общий HTTP Basic Auth отключён для проверки портала. Не включай его повторно без нового запроса; сохраняй `noindex`, авторизацию личного кабинета и внутреннюю маршрутизацию API/БД. API и PostgreSQL не должны публиковаться напрямую. По `docker-compose.yml` именованные тома называются `avtorinok_postgres` и `avtorinok_private_media`.
- Не удаляй, не пересоздавай и не очищай именованные тома; никогда не используй `docker compose down -v` для штатной остановки.
- Не импортируй и не добавляй синтетические данные на VPS. Не превращай локальные demo/test fixtures в реальные объявления. `DEPLOYMENT.md` сообщает об уже существующем приостановленном smoke-объявлении; не возобновляй и не дублируй его без отдельной задачи.
- Не показывай и не копируй значения `.env`, пароли или ключи. На хосте `.env` должен оставаться с правами `600`.
- `docs/IMPLEMENTATION_STATUS.md` фиксирует отказ SSH-agent аутентификации 2026-09-29. Команда из `SERVER.md` и прежние deployment-отчёты не доказывают текущий доступ: перед любыми удалёнными действиями требуется свежая успешная аутентификация и read-only проверка текущего состояния. Не выполняй deploy, миграции, импорт, restore или изменение Nginx без отдельного явного запроса; перед релизом сохрани rollback и проверь тома, `.env`, текущий режим публичного доступа, авторизацию аккаунтов и `noindex`.
