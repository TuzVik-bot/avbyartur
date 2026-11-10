# TESTING.md — журнал проверок

Running log: что проверено, чем и когда. Дополняется при каждом изменении.

## 2026-11-10/11 — prod-sync: перенос аудита на production-линию

Ветка `prod-sync-20261110` создана от релиза `refero-20261108-r1` (коммит `651f75d`,
точная копия production). На неё перенесён смысл исправлений из `AUDIT_REPORT.md`,
сделанных на `main` (запись 2026-11-10 в `TESTING.md` ветки `main`). Статус по каждому пункту —
таблица «Статус исправлений» в `AUDIT_REPORT.md`. Готовится релиз `audit-20261111-r1`.
На VPS ничего не выкачено.

Последние правки этой серии:

- `measurement-provider.tsx`: `usePathname()` вызывается безусловно (раньше хук стоял
  внутри `&&`). Переопределения правил ESLint для файла удалены,
  `react-hooks/rules-of-hooks` снова `error`. `prefer-rest-params` отключён одной
  строкой `eslint-disable-next-line`: gtag.js принимает только объект `arguments`.
- Воркер: `_record_heartbeat` не роняет цикл. Ошибка пишется в лог как WARNING
  `worker_heartbeat_failed` с трейсбеком, например если таблицы ещё нет во время
  rolling deploy. В той же транзакции удаляются строки старше 24 ч: `worker_id` =
  `hostname:pid`, поэтому каждый рестарт оставляет новую строку.
- `docker-compose.yml`: образ БД снова ровно `postgres:17.11-alpine`, без digest.
  Смена ссылки на образ пересоздаст контейнер БД при следующем `up`, поэтому
  закрепление digest отложено до окна обслуживания.
- Новый `POST /api/v1/analytics/errors` (`backend/app/api/analytics.py`). Раньше
  `reportFrontendError` получал 404. Схема строгая (`extra="forbid"`, allowlist
  `error_type` и `breadcrumbs`, не больше 10 breadcrumbs, `release_id` до 64 символов
  по шаблону). Без авторизации и CSRF, как `dealer/clicks`. Лимит 30 в час на IP
  через `consume_rate_limit` + `ip_scoped_limit`. В лог пишется одна строка WARNING
  `frontend_error`, путь и query не пишутся. Ответ 202 `{"accepted": true}`.
  Web-прокси пересылает `content-type`, тело и IP клиента, поэтому вызов из браузера
  проходит. `types.generated.ts` перегенерирован.
- `globals.css`: нейтральный цвет для `.market-badge.in_market`.

Базовые линии:

- До переноса (`651f75d`, по журналу переноса, этим прогоном не повторялось):
  backend **36 failed**, web **51 failed**.
- После (полный прогон в конце работы 2026-11-11):
  - backend — **921 passed, 0 failed** (одноразовая PostgreSQL 17, `TZ=UTC`);
  - web — **876 passed / 135 файлов, 0 failed**. Параллельный исполнитель чинил
    web-тесты в это же время; число снято с рабочего дерева на момент прогона.
- `corepack pnpm typecheck` — PASS.
- `corepack pnpm lint` — exit 0, 0 ошибок, **118 предупреждений** (бэклог; правила
  временно понижены до `warn` в `web/eslint.config.mjs`).
- `python3 -m unittest discover -s scripts -p 'test_*.py'` — **128 тестов OK**
  (6 skipped).

Что проверено:

- Миграция `0034_listing_search_perf` на схеме из моделей, помеченной `stamp head`:
  `downgrade 0033_listing_in_transit` → `upgrade head`, оба шага без ошибок.
  Цепочку с пустой БД (`upgrade head` с нуля) не проверить: старая миграция падает
  на `DuplicateColumn telegram_contact_url`. Это давний дефект цепочки, не 0034.
- Два цикла воркера параллельно не обрабатывают одну задачу дважды:
  `test_two_worker_loops_never_process_a_job_twice`. Новые тесты heartbeat: очистка
  строк старше 24 ч, сбой без остановки `_work_once`.
- Новые тесты `test_frontend_error_reports.py`: 202 и структурированный лог; 422 на
  лишние поля, превышение длины, неизвестный `error_type` или breadcrumb и
  отсутствующее поле; 429 после 30 запросов с одного IP, другой IP проходит.
  Добавлен контракт в `test_route_error_status_contract.py`.
- `docker compose config --quiet` — PASS.
- `pnpm audit --prod` — 0 уязвимостей.
- Не проверено: живой production, применение nginx `real_ip` за OpenResty, установка
  systemd-юнитов на VPS, браузерная отправка отчёта об ошибке через Next-прокси.
- Замечание: `uv run ruff check app tests` сообщает 10 находок (неиспользуемые импорты
  и т. п.) в тестовых файлах вне этой серии правок, а CI запускает ruff.

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
  `docs/releases/2026/PUBLIC_INDEXING_2026-10-25.md`. Дамп БД до переключения:
  `pre-public-indexing-20261025T131005Z` (542 TOC).
