# Импорт объявлений с ab.onliner.by: реализация, 24 октября 2026

Проект располагает письменным разрешением оператора Onlíner на зеркалирование
ограниченной выборки объявлений автобарахолки: по 10 б/у автомобилей на
марку, все города Беларуси, с фотографиями, описаниями и контактами
продавцов. Разрешение хранится у оператора портала на бумаге; при изменении
условий или отзыве разрешения зеркалирование отключается переменной
`ONLINER_SYNC_ENABLED=false` и ручным снятием импортированных объявлений.

## Что реализовано

- `backend/app/ingest_onliner.py` — модуль зеркалирования: троттлированный
  HTTP-клиент (httpx, один запрос за интервал, повторы с backoff, 403
  останавливает сбор), парсер объявлений, идемпотентный импорт
  (slug `onliner-<id>`), фото через карантин и `photo.process`-пайплайн,
  немедленная публикация (`active` + `ListingStatusEvent` c `actor_kind="import"`
  + базовое событие цены `published` + `AuditEvent`), обновление существующих
  (цены через `ListingPriceEvent`, закрытие/переоткрытие по `closed_at`),
  обнаружение новых объявлений по маркам.
- `backend/app/config.py` — настройки `onliner_*` (база URL, интервал
  запросов, лимит на марку, максимум фото, флаг и интервал синхронизации,
  e-mail владельца-зеркала, охват марок). По умолчанию синхронизация
  выключена.
- `backend/app/worker.py` — job kind `onliner.sync` и планировщик
  `_schedule_onliner_sync` (бакеты по `ONLINER_SYNC_INTERVAL_HOURS`, leasing
  продлевается каждые 25 записей).
- `scripts/import_onliner_listings.py` — CLI: `collect` (снапшот JSONL),
  `import` (публикация снапшота, `--dry-run`, `--no-photos`, `--limit`,
  `--company-unp`), `sync` (обновление + новые), `refresh` (только
  обновление). Запускать из `backend/` или внутри API-контейнера
  (корневой docker-compose `.env` несовместим с extra=forbid).
- `backend/tests/test_onliner_ingest.py` — 19 интеграционных тестов:
  парсинг, клиент (MockTransport), публикация, идемпотентность, вычищение
  недоимпортированных draft, фото-пайплайн с реальной генерацией WebP,
  битые фото, dry-run/limit, обновление цен, закрытие/переоткрытие,
  ошибки сети, обнаружение новых, сбор снапшота.

## Формат источника (зафиксирован 24.10.2026)

База: `https://ab.onliner.by/sdapi/ab.api` — внутренний JSON-прокси фронта;
доступен только с белорусских IP (с локальной машины и зарубежных хостов
TCP-соединение не устанавливается; с VPS `suite-s1.denjik.by` отвечает).

- `GET /dictionaries` — справочники: 233 производителя (`manufacturer`),
  топ-марки, кузов, цвет, двигатель, трансмиссия, регионы.
- `GET /search/vehicles?extended=true&limit=N&state[]=owned&car[0][manufacturer]=<id>`
  — поиск б/у по марке; фильтры: `state[]=owned|new|emergency`,
  `location[country|region|city]=<id>`, `car[0][model]=<id>`;
  пагинация `page`; `total`.
- `GET /adverts/{id}` — полная карточка: описание, `specs`
  (год/пробег/двигатель/привод/цвет), `price` (+`converted` BYN/USD/EUR),
  `seller` (имя, маскированный телефон, часы звонков), `location`,
  `images` (оригиналы `content.onliner.by` + imgproxy-варианты),
  `deal_terms`, `closed_at`, `html_url`.
- `GET /vehicles/{id}/phones` — полный номер телефона без авторизации.
- `POST /links/parse {url}` — разбор SEO-ссылок в фильтры (использован для
  реверса формата фильтров).

Ключевые маппинги: трансмиссия `mechanical→manual`; топливо
`gasoline→petrol`, `hybrid`, ГБО (`engine.gas`) `→lpg`; цвет
`grey→gray`, `violet→purple`, `skyblue/maroon/golden→other`;
`state=new→new`, `owned→used`, `emergency→used+damaged`;
таможня `customs_clearance→cleared_rb/uncleared`; цена: EUR пересчитывается
в USD из `converted`. Каталог марок/моделей матчится по slug, затем по
имени; гео — по имени города (fallback `manual_city`). VIN не переносится
(источник отдаёт маскированным). В конец описания добавляется атрибуция
«Источник: Onlíner (ab.onliner.by)» со ссылкой на оригинал.

## Проверено

- 19/19 новых тестов; полный бэкенд-прогон: 4 падения
  (`listing_currency`, `listing_response_contract`, `route_error_status_contract`,
  `listing_completion`) воспроизводятся и без изменений этой задачи —
  следствие несобранных правок рабочего дерева, ожидающих отдельной сборки.
- End-to-end smoke на реальных данных (5 объявлений Ford, снапшот собран
  с VPS): все опубликованы `active`, реальные фото прошли карантин и
  WebP-варианты (320/768/1600), события цены `published`, полные телефоны,
  малые города легли в `manual_city`, повторный прогон идемпотентен,
  `sync_existing` на неизменённых данных — 5 unchanged.

## Запуск на VPS (требует отдельного явного запроса)

1. Выбрать/создать active-пользователя-владельца зеркала (например,
   выделенный аккаунт «Onliner»); при необходимости — approved-компанию
   с UNP и передавать `--company-unp` (квоты на submit импорт не проходит:
   пишет напрямую в БД, как abw-импортёр).
2. Первый перенос: в API-контейнере
   `python scripts/import_onliner_listings.py collect --output data/onliner_snapshot_<date>.jsonl`
   (≈2500 запросов на 233 марки ≈ 40–60 мин при 1 rps), затем
   `... import --snapshot ... --owner-email <...>` (фото ≈ 10–15 тыс.
   загрузок; оценить место на томе `avtorinok_private_media`, закладывать
   ~5–15 ГБ).
3. Постоянная синхронизация: в `.env` (600) задать
   `ONLINER_SYNC_ENABLED=true`, `ONLINER_SYNC_OWNER_EMAIL=<...>`,
   при желании `ONLINER_SYNC_INTERVAL_HOURS=6` (по умолчанию),
   `ONLINER_SYNC_MANUFACTURERS=all`; перезапустить worker. Джоба обновляет
   цены, ставит на паузу закрытые и возвращает переоткрытые, затем
   импортирует новые объявления по каждой марке.
4. Перед релизом — стандартные предрелизные проверки проекта, backup и
   rollback по DEPLOYMENT.md; после релиза — контрольный просмотр
   карточек на портале.

## Фактический деплой: 25 октября 2026

Релиз `onliner-mirror-20261025-r1` развёрнут по явному запросу
пользователя. База — работавший прод-код (backend релиза
`homepage-ads-20261024-r1`); поверх — только файлы этой задачи
(плюс перенос `httpx` из dev- в основные зависимости, `COPY scripts` в
`backend/Dockerfile`, переменные `ONLINER_*` в `environment` api/worker
в `docker-compose.yml`). Web не пересобирался и остался на образе
`avtorinok-web:category-art-20261024-r2`; api/worker —
`avtorinok-api:onliner-mirror-20261025-r1` (linux/amd64, сборка на VPS).

- Исправление по факту smoke: матчинг города не находил «Минск», потому
  что источник пишет «Минская обл.», а каталог — «Минская область»;
  `resolve_location` переписан на поиск по имени города с нормализацией
  региона для дубликатов.
- Pre-deploy backup: `avtorinok-20261025T120930Z` (ветка version-1:
  `AVTORINOK_BACKUP_ALLOW_EMPTY_LICENSED=1`, в релизе нет data/licensed).
- Владелец зеркала: `onliner-mirror@suite-s1.denjik.by` (active, роль
  user), доступ — `/home/suite/.config/avtorinok/onliner-mirror-access.json`
  (600).
- Мини-smoke: 6/6 объявлений BMW с фото опубликованы, WebP отдаётся,
  публичная выдача и SSR карточки 200; тестовые записи вычищены.
- Полный перенос: сбор 233 марок — 704 объявления, 0 ошибок
  (233 марки × до 10 свежих б/у по всей РБ). Импорт запущен отдельным
  контейнером `avtorinok-onliner-import` из того же образа (обходит
  пересоздание api-контейнера; `docker exec -d` в api ненадёжен).
- Наблюдение: 25 октября ~12:34 UTC контейнер api был пересоздан сторонним
  действием во время фоновой задачи — вероятен второй оператор сервера;
  при совместных работах сверяйтесь.

