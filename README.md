# Авторынок BY

Автомобильный маркетплейс: FastAPI, PostgreSQL, Next.js и фоновая обработка
фотографий, импорта и уведомлений.

Приватный репозиторий: [TuzVik-bot/avbyartur](https://github.com/TuzVik-bot/avbyartur).

## Структура

- `backend/` — API, модели, миграции Alembic и тесты.
- `web/` — интерфейс Next.js, кабинет, модерация и административные страницы.
- `scripts/` — сборка, резервное копирование, восстановление и мониторинг.
- `deploy/` — шаблоны Nginx, Compose и systemd.
- `data/` — базовые справочники и география для разработки.
- `docs/` — API-контракт, требования и эксплуатационная документация.

## Запуск

Установите Docker с Compose, Python 3.12 с `uv` и Node.js с Corepack.
Создайте защищённую локальную конфигурацию:

```sh
make secrets
make config-check
make up
```

`make up` собирает приложения и применяет миграции к БД, указанной в локальной
конфигурации. Перед запуском проверьте назначение БД и томов. Именованные тома
сохраняйте; `docker compose down -v` для штатной остановки не используйте.

Подробнее: [backend](backend/README.md), [frontend](web/README.md),
[runbook](docs/runtime/runbook.md), [API](docs/API_CONTRACT.md).

## Проверки

```sh
cd web
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm typecheck
```

Backend-тесты создают и удаляют таблицы. Используйте **только отдельную
одноразовую PostgreSQL БД**, имя которой заканчивается на `_test`. Задайте
`TEST_DATABASE_URL` и `TEST_DATABASE_DISPOSABLE_CONFIRMATION`, равный точному
имени этой БД, затем выполните `cd backend && uv run pytest`.
Production и preview-БД для тестов не подходят, даже если имя заканчивается на `_test`.

## Данные и секреты

`.env`, ключи, резервные копии, приватные фотографии, рабочие импортные снимки,
локальные артефакты проверок и лицензионные исходники Drom не входят в Git.
Базовый каталог в репозитории не заменяет полный разрешённый production-каталог.
Не публикуйте импортные черновики без проверенных данных продавца и фотографий.

## Текущее состояние (22 октября 2026)

Источник: отчёты деплоя и архивы релизов от 22.10.2026. SSH к production в этой сессии заново не проверялся.

- Канонический домен: <https://xn--80aeylebmo7f.xn--90ais> (авторынок.бел). `suite-s1.denjik.by` выведен из эксплуатации ([приёмка](docs/runtime/CANONICAL_DOMAIN_ACCEPTANCE_2026-10-21.md)).
- Web: `product-wave-articles-20261022-r1` ([отчёт](docs/runtime/COMBINED_RELEASE_2026-10-22.md)). API и worker: `product-wave-20261021-r1`, собран из архива `product-wave-source.tar.gz` (sha256 `4fb7cf57a83e3fedcedc15a516c098735c2bf1269d29e3c352edd5afdcaa62d0`, база `53ff49e`).
- Схема БД: `0032_listing_price_hist` (alembic head этой ветки; значение на проде подтверждено read-only проверкой 22.10.2026; ранее подтверждённое документами значение на 21.10.2026 — `0031`).
- HTTP Basic Auth выключен (с 4 октября 2026 по запросу пользователя); глобальный `X-Robots-Tag: noindex` включён (`web/next.config.ts`). Оба правила сохраняются.
- Активных объявлений на последней проверке (22.10.2026, до релиза) — 0.
- Источник истины для кода — git-ветка `integrate/20261022` (реконструирована из production-архивов релизов, коммит `dc41a9e`). Архивы релизов сохранены локально в `/Users/home/backups/avbyartur-20261022/tmp-rescue` (вне git).
- Открыто: полная приёмка MVP (p95 нагрузки выше 500 мс); реальные SMS/email/payment-провайдеры не подключены; патчи `catalog-pack-01..05` и category-navigation в `docs/runtime/*.patch` не входят ни в один известный источник (на проде могут отсутствовать); статьи из БД (`/admin/content`) не показываются на публичных страницах (публичные берут статический `web/src/lib/editorial-articles.ts`); UX-редизайн из `origin/main` (коммиты до `0753afa`) на проде не развёрнут с 15.10.2026.

Подробности: [DEPLOYMENT.md](DEPLOYMENT.md), [SERVER.md](SERVER.md).
