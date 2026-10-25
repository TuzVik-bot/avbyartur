# TESTING.md — журнал проверок

Running log: что проверено, чем и когда. Дополняется при каждом изменении.

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
