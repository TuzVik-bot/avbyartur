# Инструкции проекта

## Структура и проверенные команды

- Корень проекта: `/Users/home/Downloads/avbyartur`. Git инициализирован 4 октября 2026; ветка `main`, `origin` — `https://github.com/TuzVik-bot/avbyartur.git`, репозиторий приватный. Перед изменениями проверяй `git status --short` и актуальный remote. Секреты, runtime-данные, лицензионные источники `data/licensed/` и локальные `.superpowers/` артефакты исключены из Git.
- Источник истины для кода production на 22 октября 2026 — ветка `integrate/20261022` (реконструирована из production-архивов релизов, коммит `dc41a9e`); `main` и `origin/main` (UX-редизайн до `0753afa`) на проде не развёрнуты. Архивы релизов: `/Users/home/backups/avbyartur-20261022/tmp-rescue` (вне git).
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

- Канонический домен: `https://xn--80aeylebmo7f.xn--90ais` (авторынок.бел); `suite-s1.denjik.by` выведен из эксплуатации. Релизы по документам на 22.10.2026: web `product-wave-articles-20261022-r1`, API и worker `product-wave-20261021-r1`, схема БД `0032_listing_price_hist` (прод выведен из скрипта релиза; подтверждено `0031` на 21.10.2026). Актуальное состояние: `README.md`, `DEPLOYMENT.md`.
- По явному запросу пользователя 4 октября 2026 общий HTTP Basic Auth на VPS отключён для проверки портала. Не включай его повторно без нового запроса; сохраняй `noindex` и авторизацию личного кабинета. API и PostgreSQL не должны публиковаться напрямую. По `docker-compose.yml` именованные тома называются `avtorinok_postgres` и `avtorinok_private_media`.
- Не удаляй, не пересоздавай и не очищай именованные тома; никогда не используй `docker compose down -v` для штатной остановки.
- Не импортируй и не добавляй синтетические данные на VPS. Не превращай локальные demo/test fixtures в реальные объявления. `DEPLOYMENT.md` сообщает об уже существующем приостановленном smoke-объявлении; не возобновляй и не дублируй его без отдельной задачи.
- Не показывай и не копируй значения `.env`, пароли или ключи. На хосте `.env` должен оставаться с правами `600`.
- `docs/IMPLEMENTATION_STATUS.md` фиксирует отказ SSH-agent аутентификации 2026-09-29. Команда из `SERVER.md` и прежние deployment-отчёты не доказывают текущий доступ: перед любыми удалёнными действиями требуется свежая успешная аутентификация и read-only проверка текущего состояния. Не выполняй deploy, миграции, импорт, restore или изменение Nginx без отдельного явного запроса; перед релизом сохрани rollback и проверь тома, `.env`, текущий режим доступа и `noindex`.

## Регрессия регистрации при web-only релизах

- 7 октября 2026 исправлен откат UI регистрации: backend capability `email_registration=true` не доказывает наличие формы во frontend. Перед web-релизом сохраняй актуальные `registerEmail`, pre-auth CSRF для `auth/register`, email-registration capability и страницы условий; не заменяй актуальный VPS-код архивом HEAD, если регистрационные изменения ещё не включены в него.
- После web-релиза на реальном `/login?next=%2Fsell` проверь появление «Создать аккаунт», открытие полей имени/email/пароля/повтора/согласий и кнопки «Зарегистрироваться». Доступность API без этой браузерной проверки не закрывает проверку регистрации. Рабочая интеграция 7 октября: VPS `/home/suite/apps/releases/registration-ui-fix-20261007`, отчёт `docs/runtime/REGISTRATION_UI_FIX_2026-10-07.md`; перед дальнейшими действиями проверь текущий релиз заново.
