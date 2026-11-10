# Публичная индексация авторынок.бел — 25.10.2026

Статус: **ВЫПОЛНЕНО И ПРОВЕРЕНО**. Сайт https://авторынок.бел открыт для
поисковиков: глобальный `X-Robots-Tag: noindex` снят на всех уровнях.

## Что сделано

1. Код (main, коммиты f577f51, bdeccf0, b13a57d, aba8bd3 + editorial 391ed2b):
   флаг `AVTORINOK_PUBLIC_INDEXING_ENABLED` управляет всеми слоями noindex —
   build-time заголовком в `next.config.ts` (через `ARG` в `web/Dockerfile`),
   корневыми meta robots (`layout.tsx` → `rootRobots()`), robots.txt/sitemap.
   При выключенном флаге поведение = закрытый пилот (fail-safe).
2. Деплой: активный web-образ `avtorinok-web:editorial-articles-20261025`
   (собран параллельной сессией из main, уже содержит SEO-код) заменён на
   `avtorinok-web:public-indexing-20261025-r1` — тот же исходник
   (`editorial-articles-20261025`), пересобран с
   `--build-arg AVTORINOK_PUBLIC_INDEXING_ENABLED=true`.
3. Release dir: `/home/suite/apps/releases/public-indexing-20261025-r1`
   (копия активного релиза + `docker-compose.public-launch.yml`: image +
   env `AVTORINOK_PUBLIC_INDEXING_ENABLED="true"`).
4. Переключение: `flock /home/suite/apps/avtorinok-web-deploy.lock` +
   `docker compose -p avtorinok ... up -d --no-deps --no-build --wait web`.
   Container: `avtorinok-web-1 9dc5fa982ca1` (healthy).

## Пред-переключательный дамп

`/home/suite/backups/avtorinok/pre-public-indexing-20261025T131005Z/database.dump`
(21 224 258 bytes, SHA-256 `a3a562a3…04c663` предшествующего дампа 13:01,
`pg_restore --list`: 542 TOC entries). Ошибка при включении индексации не
затрагивает БД; dump сохранён как обычный pre-deploy snapshot.

## Пост-проверки (12:1x–13:2x UTC)

App (127.0.0.1:8080, Host канонический) и edge (HTTPS авторынок.бел):

- Заголовок `X-Robots-Tag` ОТСУТСТВУЕТ на `/` — PASS (nginx edge уже был
  чист: `add_header X-Robots-Tag` удалён из vhost ещё 14.10,
  бэкап `pre-indexing-20261014-4400788`).
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` — PASS.
- meta robots `index, follow`; description без «закрытого пилота» — PASS.
- robots.txt: `Sitemap: https://xn--80aeylebmo7f.xn--90ais/sitemap.xml` — PASS.
- sitemap.xml: 69 URL (растёт вместе с onliner-импортом) — PASS.
- OG/Twitter: og:title, og:image → `/og-default.jpg`, twitter:card — PASS.
- JSON-LD: WebSite+SearchAction, Organization (главная); Car+Brand+
  BreadcrumbList (карточка); Article (статьи) — PASS.
- Оптимизация изображений: `/_next/image` → HTTP 200 `image/webp` — PASS.
- Лендинги /trucks /parts → 200; неизвестный путь → 404 — PASS.
- Изоляция: api/worker/db/test-mail/onliner-import контейнеры не менялись
  (ID совпадают с baseline) — PASS.
- `.env` не читался и не менялся; nginx/DNS/TLS не менялись.

## Откат

1. Вернуть web: тем же compose-переключением с
   `AVTORINOK_WEB_IMAGE_TAG=avtorinok-web:editorial-articles-20261025`
   и БЕЗ `docker-compose.public-launch.yml` (или env флага → false).
2. Ничего более не требуется: nginx чистый, БД не менялась.

## Известные ограничения

- 26 предсуществующих web-тестов падают в дереве деплой-линии
  (customs-calculator 7, sell-form 6, compare 4, page 3 и др.) — WIP
  параллельной сессии, существуют и в чистом контексте деплоя; к SEO не
  относятся. Внесённых этой работой падений: 0 (24/24 SEO-контрактов зелёные).
- Верификация в Google Search Console / Яндекс.Вебмастере — следующий шаг
  (мета-теги поддержаны через env `GOOGLE_SITE_VERIFICATION` /
  `YANDEX_SITE_VERIFICATION` при следующем пересоборе образа).
- Параллельная сессия ведёт onliner-импорт; каталог наполняется живыми
  объявлениями (sitemap растёт).
