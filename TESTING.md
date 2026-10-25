# TESTING.md — журнал проверок

Running log: что проверено, чем и когда. Дополняется при каждом изменении.

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
- Синхронизация: `ONLINER_SYNC_ENABLED=true` (дубликаты ключей в общем
  `.env` вычищены до одного блока), worker перезапущен; джоба «paused by
  operator» планировщику не мешает (по коду фильтр только queued/running);
  первая периодическая синхронизация — в следующем 6-часовом бакете.
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
