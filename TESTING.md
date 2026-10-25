# TESTING.md — журнал проверок

Running log: что проверено, чем и когда. Дополняется при каждом изменении.

## 2026-10-26 — ростовые функции: instant-оценка, Telegram-канал, платёжный шов

Изменения: дизайн-док `docs/superpowers/specs/2026-10-25-growth-features-design.md`;
backend (`app/valuation.py`, `app/api/market.py`, `app/market_schemas.py`,
`app/telegram_delivery.py`, `app/billing_services.py` ConfiguredPaymentProvider,
`app/api/billing.py` capabilities, воркер: telegram-канал доставки + link-poll,
миграция `0026_telegram_channel`); web (`/market-valuation`, бейдж рынка на
детальной, Telegram-блок в настройках, канал в сохранённых поисках, кнопка
оформления в биллинге).

- Backend: полный сьют на disposable-БД (контейнер PostgreSQL 17.11
  `127.0.0.1:55433`, `avtorinok_growth_20261026_test`): **746 passed**, 4
  deselected. Падение `test_public_detail_views_feed_owner_scoped_analytics`
  воспроизведено на чистом HEAD-worktree — предсуществующее в main (след
  откаченной analytics-фичи), к ростовым изменениям не относится; там же
  воспроизведены 3 контрактных падения (`route-error-status`,
  `listing-currency` analog-query, `listing-response` favorites).
- Новые тесты: `test_market_valuation.py` 5 passed (когорты high/low/none,
  несвежий курс USD → `unsupported_rate`, авторизованный
  `POST /listings/market-price-estimate`, CSRF-гейт для анонима);
  `test_telegram_notifications.py` 6 passed (link-start/unlink, 422
  `telegram_not_linked`, доставка outbox→sendMessage + in-app, `unsupported`
  без токена, link-poll по `/start <code>`); `test_payment_provider_config.py`
  6 passed (шаблон чекаута, ValueError без `{order_id}`, фабрика
  disabled/configured/bad-template, `/billing/capabilities`).
- Web: `corepack pnpm typecheck` PASS; полный сьют **719 passed / 26 failed** —
  все 26 воспроизведены 1:1 на чистом HEAD-worktree (предсуществующие).
  Новые тесты: `market-badge` (2), `billing-order-button` (4), `account-telegram`
  (3), `market-valuation` (3) — все зелёные.
- Проверено на моках SimpleNamespace (без новых полей Settings) — чтение
  telegram-настроек сделано через `token_from_settings`/getattr, тесты
  подмены настроек не ломаются.
- Найдено и восстановлено: sell-форма вызывала несуществующий
  `POST /api/v1/listings/market-price-estimate` (эндпоинт присутствовал только
  в устаревшем `types.generated.ts`); реализован на движке valuation.
- `types.generated.ts` НЕ перегенерирован: regen от текущего OpenAPI удаляет
  поля `telegram_contact_url`/`viber_contact_url`, на которые опирается
  sell-form (след откаченной фичи) и ломает typecheck. Перегенерация возможна
  только после возврата мессенджер-полей в бэкенд; новые API типизированы
  инлайн в `lib/api.ts`.
- Ruff: новые файлы — 0 замечаний; в изменённых файлах исправлены только
  сортировки импортов (I001), остальные замечания предсуществующие на HEAD.
- Деплой не выполнялся (требует отдельного явного запроса). Для прод-включения
  Telegram и оплаты достаточно переменных окружения: `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_BOT_USERNAME`, `PUBLIC_APP_URL`; `PAYMENT_PROVIDER_NAME`,
  `PAYMENT_CALLBACK_SECRET`, `PAYMENT_CHECKOUT_URL_TEMPLATE`.

## 2026-10-25 — деплой зеркала Onlíner (backend + прод-перенос)

Изменения: коммит `e7ce0d4` (ingest_onliner, worker job, CLI, httpx в main).
Реализация и 19/19 тестов — в docs/runtime/ONLINER_IMPORT_2026-10-24.md.

- Backend-сьют на disposable-БД (loopback-контейнер PostgreSQL 17.11,
  `avtorinok_rel_20261025_test`): прохождение целиком; 3 падения контрактов
  (route-error / listing-currency / listing-response) воспроизведены на
  чистом HEAD в отдельном worktree ДО onliner-правок — тестовый долг от
  ранее закоммиченных фич (маршруты compare/price-history/feed-imports), не
  связанный с зеркалом. Onliner-тесты и остальной сьют — зелёные.
- Прод-перенос: collect с хоста VPS — 233 марки / 703 объявления / 0 ошибок;
  import в API-контейнере — failed 0, без фото 0, 15 050 фото через
  WebP-пайплайн, все 703 `active` с атрибуцией «Источник: Onlíner»;
  идемпотентность по slug `onliner-<id>` подтверждена счётчиками
  existing/imported. `/api/v1/listings` и SSR-карточка `/cars/<uuid>` — 200.
- Синхронизация осталась ВЫКЛЮЧЕНОЙ по решению пользователя, зафиксированному
  параллельной сессией («пока хватит, останови»): кратковременное включение
  этой сессией отменено в тот же день (`ENABLED=false`, queued-джоб нет,
  worker force-recreate). Дубликаты ONLINER_SYNC-ключей в общем `.env`
  вычищены до одного блока; владение 193 новых объявлений унифицировано с
  первой выкладкой (один владелец, 897 объявлений, 889 active).
- Полный отчёт: docs/runtime/ONLINER_DEPLOY_2026-10-25.md.

## 2026-10-25 — 21 лицензированная статья cars.ru в разделе «Статьи» (web/)

Изменения: `editorial-articles-carsru.ts` (21 адаптированная статья; лицензия
cars.ru, исходники и фото — в `data/licensed/cars-ru`, вне Git), объединение в
`editorial-articles.ts`, действия-подсказки на все слаги в
`editorial-guide-actions.ts` (+дата обновления контента), рендер lead-фото и
inline-фото с подписями-кредитами и атрибуцией источника в карточке статьи,
миниатюры в списке, `publishedOn`/`leadImage` в Article JSON-LD и OG,
22 фото в `web/public/editorial/<slug>/`.

### Автоматические проверки

- `cd web && corepack pnpm test` — 105 файлов / 646 тестов PASS. Новые проверки:
  каждое фото (`leadImage` и image-блоки) существует в `web/public/editorial`;
  для лицензионных статей рендерятся lead-фото, строка «По материалам» и ссылка
  на оригинал; OG-метаданные используют lead-фото; байлайн различается для
  собственных («Редакционный материал») и лицензионных («Материал по лицензии»)
  материалов.
- `cd web && corepack pnpm typecheck` — PASS.
- `cd web && corepack pnpm build` — production build PASS, все 24 статьи
  (3 собственные + 21 адаптированная) предрендерены без ошибок.
- Сверка данных: 21 слаг в `manifest.json` архива ↔ 21 слаг в
  `editorial-articles-carsru.ts` (расхождение отсутствует); в адаптированных
  текстах нет маркеров РФ-рынка (рубли, ГИБДД, Авито, утильсбор, Минпромторг,
  РОАД) и брендовых упоминаний из исходников; внешних ссылок в текстах нет
  (единственная внешняя ссылка — атрибуция на оригинал статьи cars.ru).
- Backend этой серией не изменялся; прогон backend-тестов не требуется
  (релизная сборка бэкенда байт-в-байт совпадает с задеплоенной
  `homepage-ads-20261024-r1`, см. TESTING.md 2026-10-24 и git-историю).

## 2026-10-24 — публичный SEO-запуск (серия изменений web/)

Изменения: флаг-управляемый публичный режим (`AVTORINOK_PUBLIC_INDEXING_ENABLED`),
OG/Twitter-метаданные + og-default, JSON-LD (WebSite+SearchAction, Organization,
BreadcrumbList, Article, AutoDealer), статические страницы в sitemap, мета-описания
17 статических страниц, лендинги /trucks /trailers /buses /parts, 308-редирект
канонических карточек, оптимизация изображений объявлений (снятие `unoptimized`),
HSTS и верификационные мета-теги в публичном режиме, nginx public-шаблон.

### Автоматические проверки

- `cd web && corepack pnpm test` — 105 файлов / 643 теста PASS (включая новые
  `src/lib/public-seo.test.ts`: строгий флаг, rootRobots в обоих режимах,
  OG-фолбэк на брендовое изображение, фильтрация сторонних og:image,
  нумерация хлебных крошек, санитизация JSON-LD, OG/Twitter активных объявлений).
- `cd web && corepack pnpm typecheck` — PASS. Попутно расширен тип
  `EditorialArticle` (опциональные `publishedOn`/`source`/`leadImage`, вариант
  блока `image`) — аддитивно, чтобы компилировался параллельный WIP-файл
  `editorial-articles-carsru.ts` (никем не импортируется, в релиз не входит).
- `make config-check` — PASS (compose config + catalog.json).
- Backend не изменялся этой серией; прогон backend-тестов не требуется.

### Исправленные устаревшие тесты

- `src/app/sitemap.test.ts`: ожидаемые массивы URL дополнены
  `STATIC_SITEMAP_PATHS` (17 статических страниц) — контракт обновлён, а не
  ослаблен (строгий `toEqual` сохранён).
- `src/app/page.test.tsx`: утверждение `<img>` count=1 не учитывало
  категорийную графику, появившуюся 24.10 (проверено: тест падал и на
  baseline-коммите `555fdbe` в чистом worktree). Заменено на честный контракт:
  6 изображений (hero + 5 иллюстраций категорий), каждый `src` из
  `/category-art/` или `/vehicles/`.

### Локальная прод-верификация (production build + start + curl)

Закрытый режим (флаг не задан):
- `X-Robots-Tag: noindex, nofollow, noarchive` на `/` — PASS.
- meta robots `noindex, nofollow, noarchive`, пилотный description — PASS.
- robots.txt без строки Sitemap; sitemap.xml пустой — PASS.
- HSTS отсутствует — PASS (осознанно).
- JSON-LD WebSite+SearchAction+Organization в HTML главной — PASS.
- OG/Twitter: og:site_name, og:image → `/og-default.jpg`, twitter:card — PASS.

Публичный режим (флаг = true на сборке и в рантайме):
- Заголовок X-Robots-Tag ОТСУТСТВУЕТ на `/`; `Strict-Transport-Security` присутствует — PASS.
- meta robots `index, follow`; публичный description без «закрытого пилота» — PASS.
- robots.txt содержит `Sitemap:` — PASS.
- sitemap.xml: 24 URL (ядро + 17 статических + статьи) — PASS.
- Лендинги /trucks /trailers /buses /parts — HTTP 200 — PASS.
- canonical + og:title на /customs-calculator — PASS.

Направление отказа: при расхождении режима сборки и рантайма сайт остаётся
закрытым (noindex строится по умолчанию) — fail-safe.

### Известные ограничения

- Тестовая база данных/полный browser-smoke — на Stage A приемке на VPS
  (по релизной процедуре) и после переключения флага.
- В рабочем дереве параллельная сессия ведёт backend-WIP по onliner-импорту
  (`ingest_onliner.py` и др.) — в эту серию и релиз не входит.

## 2026-10-25 — деплой публичной индексации на прод

Деплой-линия параллельной сессии ушла вперёд (editorial-articles-20261025),
поэтому SEO-дельта перебазирована на неё в worktree и закоммичена как
`aba8bd3` (main). Проверки merge-дерева:

- `corepack pnpm typecheck` — PASS.
- `corepack pnpm test`: 657 PASS / 27 FAIL — все 27 существуют и в чистом
  контексте деплоя (WIP параллельной сессии: customs-calculator 7,
  sell-form 6, compare 4, page 3 и др.); внесённых падений 0; 24/24
  SEO-контракт-теста (layout/robots/sitemap/public-seo) зелёные в обоих
  режимах флага.
- Локальный production build + start + curl: закрытый режим (noindex
  заголовок+мета, пустой robots-sitemap) и публичный (нет заголовка, HSTS,
  index/follow, sitemap 45 URL, Article JSON-LD) — PASS.
- Прод: образ `avtorinok-web:public-indexing-20261025-r1` (build-arg флага)
  переключён под flock; edge-проверки — см.
  `docs/runtime/PUBLIC_INDEXING_2026-10-25.md`. Дамп БД до переключения:
  `pre-public-indexing-20261025T131005Z` (542 TOC).
