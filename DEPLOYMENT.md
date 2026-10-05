# Авторынок: развёрнутый закрытый пилот

## 5 октября 2026: новый UX опубликован

Активный web-релиз `ux-20261005T074032Z-94a0427`, коммит `94a0427`, GitHub-ветка `codex/ux-redesign`. Обновлён только интерфейс; API/worker/БД, тома и режим доступа сохранены. Все четыре сервиса healthy. [Квитанция и откат](docs/runtime/RELEASE_2026-10-05-UX.md).

**GitHub, 4 октября 2026:** проект загружен в приватный репозиторий
[TuzVik-bot/avbyartur](https://github.com/TuzVik-bot/avbyartur), ветка `main`.
Исходники, миграции, тесты и документация включены; секреты, рабочие снимки,
backup/media и лицензионные исходники каталога исключены. Записи ниже о
непредоставленном Git remote относятся к состоянию на дату соответствующего релиза.

## Текущий релиз 2 октября 2026, проверен 14:38 UTC

Tag: `pilot-20261002T133421Z`. Активный symlink:
`/home/suite/apps/avtorinok` → `/home/suite/apps/releases/pilot-20261002T133421Z`.
Предыдущий `pilot-20261001T160530Z` и образы сохранены для отката приложений.
Это выкладка всего текущего кода в существующий закрытый пилот по явному
поручению «так задеплой всё», не подтверждение полной приёмки MVP или публичного запуска.

- Source: 472 проверенных файла, SHA-256
  `36b23d778401774c33de2c3babbb17e5a3e7dbd19a0491d70dc4a051b07dcbe5`.
- API/worker AMD64 image ID:
  `sha256:902112a6ef244a7ccf21ba6858da107952d21e67f6d82486360643542aa214eb`.
  Web AMD64 image ID:
  `sha256:9bd35ff4086e5be9fa25ab729d85136127cf602bf7604860bf7e50d076691848`.
- Python 3.12.15 / Expat 2.8.5; обновлённые зависимости, sync upload handler,
  i18n, конфигурируемая фото-политика, guest guards, история правок, dealer feed
  policies, каталог заявок, tariff CRUD и часы/роли компаний включены в этот код.
- Backend483PASS, web411PASS/typecheck, operations113PASS. Clean/repeat-head
  и0018→0021/repeat-head прошли на двух выделенных пустых локальных БД.
- Production migration0018→0019→0020→0021 выполнена нормальным Alembic.
  Все4serviceshealthy, RestartCount0. API/DB не опубликованы; web loopback8080.
- `.env` остался идентичным/mode600; PostgreSQL/media named volumes сохранены.
  Users2,listings102(100draft/2paused),photos2,companies0,tariffs0;
  каталог94makes/2630models/14009generations/13273bodyvariants/194817modifications
  совпал до/после. Synthetic данные на VPS не добавлялись.
- Pre-deploy snapshot:
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20261002T133421Z-20261002T142632Z/avtorinok-20261002T142632Z`.
  Post-deploy snapshot:
  `/home/suite/backups/avtorinok/post-deploy-pilot-20261002T133421Z-20261002T142901Z/avtorinok-20261002T142902Z`.
  Оба31checksum entries/readable dump; TOC451/464rows. Backup tool кратко
  останавливает приложения для согласованного DB/media snapshot и затем запускает
  их; первая параллельная HTTP-проверка попала на эту остановку и получила502.
  После завершения backup повторная проверка всех маршрутов прошла200.
- REAL domain BasicAuth401/noindex и authorised200 подтверждены. Новые
  `/admin/tariffs`, `/admin/catalog-requests`, validation-policy API отвечают200.
  Browser smoke прошёл; detail/guest-favorite ветки не исполнялись из-за0active
  production listings (старый smoke выводит их как PASS/skip). Дополнительные47
  проверки live profile/admin/billing/catalog/permissions/1440+390px прошли.
- Exact final images локально:29statefulAPI/worker checksPASS;8×32MPsynthetic
  JPEG4concurrent8/8ready, uploadp95339.89ms,health52/52HTTP200. Это ограниченный
  capacity probe без утверждённого uploadSLA/реального phoneHEIC.
- Full latest load600s/20RPS/10000localfixtures:12000HTTP200, но p95gate<=500ms
  НЕ пройден: первый954.69/1285.03ms, повтор670.15/978.96ms. Оба результата
  сохранены; старыйOct1baseline275.31/294.20ms не подменяет новые. Выпуск принят
  для существующего закрытого пилота; performance gate полной приёмки открыт.
- SMS/public registration/email/payment/Sentry/offsite/host-monitor не включены.
  Реальные активные объявления, внешние провайдеры, legal/offsite/device inputs
  и полная end-to-end acceptance остаются открытыми. GitHub auth работает,
  но remote проекта не найден и URL не предоставлен; Git push не выполнен.

Квитанции: `deployment-receipt.json`, `release-acceptance.json`,
`pre-deploy-backup.json`, `post-deploy-backup.json` в каталоге релиза VPS.
Откат приложений: вернуть symlink на сохранённыйOct1release и запустить его
образы. БД автоматически не понижать и не восстанавливать; миграции добавочные.

## Исторический релиз 1 октября 2026, проверен 16:18 UTC

Tag: `pilot-20261001T160530Z`. Активный symlink:
`/home/suite/apps/avtorinok` → `/home/suite/apps/releases/pilot-20261001T160530Z`.
Предыдущий релиз `pilot-20260930T052948Z` и его образы сохранены для отката.
Исходники переданы на VPS; Git push ожидает URL репозитория, поскольку в
локальном проекте отсутствуют `.git` и remote.

- Архив исходников: SHA-256
  `a7919540208d874adac4e5c64b16612d0f656ae394754e2ac59735d58db62d59`;
  423 файла, без `.env`, ключей, licensed data, кешей и локальных зависимостей.
  Все файлы проверены по source manifest после передачи.
- Образы собраны нативно на VPS, `linux/amd64`; production Turbopack build PASS.
  API/worker image ID:
  `sha256:6c5f7908d7e6740da473f6e6d72b33c549fe757a6f9f77232cf6a0f52c6f44db`.
  Web image ID:
  `sha256:d9393e51112899a9081285f3c551cca86932010f4d1e4a5d55aa5ba4f2a4ffee`.
- Production миграции `0011_sms_otp_auth` → `0018_profile_identity` PASS.
  Перед ними проверены чистое развёртывание и schema-only 0011 → 0018,
  включая повторный upgrade head, на выделенных disposable локальных БД.
- Backend suite: **396 PASS**. Web suite: **312 PASS**, 66 файлов.
  Typecheck, `make config-check`, 8 smoke/monitor tooling tests PASS.
  Исправлены две предрелизные тестовые ошибки: роли company/platform admin
  разделены; проверка мониторинга приведена к typed `imports.failed_24h`.
- Pre-deploy backup:
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20261001T160530Z/avtorinok-20261001T160908Z`.
  Post-deploy backup:
  `/home/suite/backups/avtorinok/post-deploy-pilot-20261001T160530Z/avtorinok-20261001T161751Z`.
  Оба snapshot имеют 31 подтверждённую checksum entry; pre-deploy dump читается
  через `pg_restore --list` (266 строк TOC).
- Все 4 сервиса healthy, RestartCount=0. `.env` mode 600 и его SHA-256 не
  изменились. Именованные тома PostgreSQL/media, 2 пользователя, 102 объявления,
  2 фото и 0 компаний сохранены. API/БД не опубликованы наружу, web остаётся
  на `127.0.0.1:8080`. Nginx/TLS и Basic Auth не менялись.
- Каталог проверен через новые admin API: 94 марки, 2 630 моделей,
  14 009 поколений, 13 273 варианта кузова, 194 817 модификаций. Использованы
  имеющиеся на VPS source artifacts; повторного импорта/публикации не было.
- HTTPS edge smoke PASS: anonymous 401/noindex, authorized 200.
  Browser smoke **29/29**; дополнительно **41 PASS** на новых profile/admin/billing
  API и страницах, включая 1440/390 px, отсутствие переполнения и JS errors,
  сохранность каталога и отказ admin monitoring обычному пользователю.
- Свежие агрегаты логов API/worker/web/db: error events=0, HTTP 5xx=0,
  traceback=0. Синтетические данные на VPS не добавлены.

SMS/registration, SMTP, реальные платежи и Sentry остаются неподключёнными.
Host monitor/systemd integration и offsite backup не установлены этой задачей.
Активных объявлений и компаний нет: stateful buyer/dealer/payment acceptance,
load/HEIC и offsite restore/RPO/RTO не подтверждены. Полная готовность MVP
или публичный запуск не заявляются.

Откат приложений: вернуть symlink на `pilot-20260930T052948Z` и запустить
его сохранённые образы. Миграции этого релиза добавляют схему; downgrade/restore
БД автоматически не выполнять. Фактический rollback не запускался.

Подробная машинная квитанция на VPS:
`/home/suite/apps/releases/pilot-20261001T160530Z/deployment-receipt.json`.

## Исторический релиз 30 сентября 2026, 05:29 UTC


Tag: `pilot-20260930T052948Z`. The active symlink points to
`/home/suite/apps/releases/pilot-20260930T052948Z`; rollback release
`pilot-20260930T004119Z` remains intact. The release was built natively on the
VPS as `linux/amd64`. The filtered source archive has SHA-256
`7faa4a3429ee091181651d3123b36db28f4574907509d6ceaf56232e1eb60e27`.

- API/worker image ID: `sha256:9f71ad7c83622efee27c68869b178e6bfcf4000056c696c6cfc82af79589b76e`.
- Web image ID: `sha256:0a81b3d0a55d7b00ca6331290f3faa62e0c3abacb4e25ace7e95d948abaa08a8`.
- Alembic advanced from `0009_notification_outbox` through
  `0010_conversations` to `0011_sms_otp_auth (head)`. SMS login and public
  registration remain disabled; no SMS provider is configured.
- Pre-deploy backup:
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20260930T052948Z/avtorinok-20260930T053644Z`.
  Post-deploy backup:
  `/home/suite/backups/avtorinok/post-deploy-pilot-20260930T052948Z/avtorinok-20260930T054842Z`.
  Both format-5 snapshots have 31 verified checksum entries and readable
  PostgreSQL dumps (`pg_restore -l` listed 215 and 266 entries respectively).
- The nine permissioned Drom batches (26 files) were copied with checksum
  verification and mode `600`. The deployed catalog contains 94 makes, 2,630
  models, 14,009 generations, 13,273 body variants and 194,817 modifications.
  Catalog dry-run reported `unchanged`. These records are vehicle catalog data,
  not sale listings.
- Production listing state remains 100 drafts, 2 paused and 0 active. The empty
  public search is intentional; synthetic announcements were not added or
  activated on the VPS.
- All four Compose services are healthy with restart count `0`. API and database
  are internal-only; web binds only `127.0.0.1:8080`. `.env` remains mode `600`,
  and `avtorinok_postgres` / `avtorinok_private_media` are present. Nginx/TLS
  was not changed.
- Authenticated HTTPS edge smoke passed (anonymous requests return `401` with
  `noindex`; authorized requests return `200`). Browser smoke passed `29/29`
  across search, seller/admin login, account and moderation pages, and 390 px
  mobile layouts. Listing detail and favorite mutation were skipped because the
  production catalog has no active listings. A full restore of this newest
  snapshot and off-host restore/RPO/RTO measurement remain outstanding.
- Compose emitted a warning about the stopped orphan
  `avtorinok-web-candidate-20260929`; it was left untouched and did not affect
  backup selection or service health.

Rollback: atomically point `/home/suite/apps/avtorinok` to
`/home/suite/apps/releases/pilot-20260930T004119Z` and run
`docker compose up -d --no-build --wait` from that release. Do not delete named
volumes or downgrade the database automatically.

## Предыдущий релиз 30 сентября 2026, 00:41 UTC

Tag: `pilot-20260930T004119Z`. Deployment switched `/home/suite/apps/avtorinok`
to `/home/suite/apps/releases/pilot-20260930T004119Z`; the prior
`pilot-20260930T000430Z` release is retained for rollback. The completed Compose
start reported all four services (`api`, `db`, `web`, `worker`) as running and
healthy. The database was already at `0009_notification_outbox`, so no migration
was run.

- API image ID: `sha256:a369bc7f377a0a44eeb4b66fc0e74c3173913d455baec8665f2508d491edd311`.
- Web image ID: `sha256:f14684f98fc3a1d11274942e882fdcdd2171fb5861b1307ea2034d3111704ea8`.
  Both images were built for `linux/amd64`.
- Pre-deploy backup:
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20260930T004119Z/avtorinok-20260930T004407Z`.
  The backup had 31 verified checksum entries and a PostgreSQL dump readable by
  `pg_restore -l`.
- Filtered source archive:
  `/home/suite/apps/releases/pilot-20260930T004119Z/source.tar.gz`, SHA-256
  `6c44479786669983a7afc5cf8f9e6b5dea1bd8ce1b70850f57a8362f0cee4459`.
  The nine licensed Drom batches (26 files) were copied with checksum checks and
  mode `600`; they are catalog source data, not sale listings.
- Fresh HTTPS edge smoke passed: anonymous `/`, `/healthz`, `/robots.txt`, and
  `/api/v1/listings` returned `401` with `noindex`; authenticated requests
  returned `200`. Browser smoke passed `29/29`, including public routes, seller
  and admin sessions, notification inbox, moderation queues, and mobile widths.
  There are no active public listings, so detail and favorite actions were
  correctly skipped for the empty production catalog.
- No post-deploy backup for this tag is recorded yet. A fresh BatchMode SSH
  preflight now returns `Permission denied (publickey,password)`, so `.env`
  permissions, restart counts, and current volume IDs were not independently
  reread after the switch. The deployment did not issue a volume deletion or a
  Nginx/TLS change. The post-deploy snapshot recorded below belongs to the
  previous release, not this one.

Rollback: atomically point `/home/suite/apps/avtorinok` back to
`/home/suite/apps/releases/pilot-20260930T000430Z` and run
`docker compose up -d --no-build --wait` from that release. Do not delete named
volumes or downgrade the database automatically; migration `0009` is additive.

## Предыдущий релиз 30 сентября 2026, 00:04 UTC

Tag: `pilot-20260930T000430Z`. Symlink `/home/suite/apps/avtorinok` указывает на
`/home/suite/apps/releases/pilot-20260930T000430Z`; предыдущий
`pilot-20260929T232443Z` сохранён для rollback. Исходники переданы на VPS без
секретов, лицензированные Drom-файлы сохранены с правами `600`, а образы
собраны и проверены на целевом AMD64-хосте.

- API: `avtorinok-api:pilot-20260930T000430Z`, image ID
  `sha256:dde43eb8e5c2bbba97be4dd18d06e7ade97954df1f50318b26c2602f243ad044`.
- Web: `avtorinok-web:pilot-20260930T000430Z`, image ID
  `sha256:fc554173eee2f4c050b94366e23b4b958bbb695c368faedefcd1befd13e5eee7`.
  Оба application image проверены как `linux/amd64`; pinned PostgreSQL image
  также `linux/amd64`.
- Alembic обновлён с `0008_saved_searches` до
  `0009_notification_outbox (head)`. Таблица outbox и in-app web notifications
  подтверждены на production release; email provider не настроен и остаётся
  `unsupported`.
- Pre-deploy backup:
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20260930T000430Z/avtorinok-20260930T000514Z`.
  Post-deploy backup:
  `/home/suite/backups/avtorinok/post-deploy-pilot-20260930T000430Z/avtorinok-20260930T000830Z`.
  В каждом snapshot 31 SHA-256 entry; checksums прошли, `pg_restore -l`
  прочитал database dump.
- Все четыре Compose-сервиса healthy, restart count равен `0`; `.env` mode
  `600`, тома `avtorinok_postgres` и `avtorinok_private_media` сохранены.
  Nginx/TLS и Basic Auth не изменялись.
- HTTPS без Basic Auth для `/`, `/healthz`, `/robots.txt` и `/api/v1/listings`
  возвращает `401` с `X-Robots-Tag: noindex, nofollow, noarchive`. Внутренние
  API `/health/live` и `/health/ready` возвращают `200`; web SSR
  отдаёт `200` для `/`, `/account/notifications` и других проверенных закрытых
  страниц.
- Production catalog counts: 94 makes, 2,630 models, 14,009 generations,
  13,273 body variants, 194,817 modifications. Listings remain `100 draft` and
  `2 paused`; active public listings are still `0`, so synthetic demo data is
  not published on the VPS.
- Source archive:
  `/home/suite/apps/releases/pilot-20260930T000430Z/source.tar.gz`, SHA-256
  `0da32c47be2476a4187dbc076b48fbd943d8c3e9704b54e60dc4c39eb1396cdb`.

Rollback: atomically point `/home/suite/apps/avtorinok` back to
`/home/suite/apps/releases/pilot-20260929T232443Z` and run
`docker compose up -d --no-build --wait` from that release. Do not delete named
volumes or downgrade the database automatically; migration `0009` is additive.
Rollback has not been executed; the release and previous tag were inspected
read-only.

## Предыдущий релиз 29 сентября 2026, 22:25 UTC

Tag: `pilot-20260929T222500Z`. Symlink `/home/suite/apps/avtorinok` указывает на
`/home/suite/apps/releases/pilot-20260929T222500Z`; предыдущий
`pilot-20260929T125300Z` сохранён для rollback. Кандидат собран на VPS как
`linux/amd64`, production Next.js build и TypeScript прошли.

- API: `avtorinok-api:pilot-20260929T222500Z`, image digest
  `sha256:68b9dcd5cb0e31d7992c7204445fd98d54c4364d703a4d7413271ffd56228830`.
- Web: `avtorinok-web:pilot-20260929T222500Z`, image digest
  `sha256:223eba3ee085a4e19af0efbc3013e6c5fa00768cdcbc1644dc2f11c272459435`.
  Runtime uses pinned Debian Bookworm Node image; the previous Alpine/musl exit-139
  loop is gone, and the live web container has restart count 0.
- Alembic is at `0007_company_report_revisions (head)`. Company, report and photo
  mutations use optimistic revision checks; unknown API routes return the standard
  JSON error envelope with `X-Request-ID`.
- `.env` remains mode 600. Volumes `avtorinok_postgres` and
  `avtorinok_private_media` were preserved. No Nginx change was made.
- Drom batches 1–9 were dry-run, imported and replay-checked after a format-5
  backup. Production counts are 194,817 catalog modifications, 14,009 generations,
  13,273 body variants and 2,630 models alongside the existing 94 makes. The
  permissioned Drom files are catalog inputs, not sale listings; no synthetic VPS
  listings were added.
- Pre-import backup: `/home/suite/backups/avtorinok/pre-release-20260929T220213Z/`.
  Post-import backup: `/home/suite/backups/avtorinok/post-import-20260929T221749Z/`.
  Post-deploy backup: `/home/suite/backups/avtorinok/post-deploy-20260929T222815Z/`.
  Each format-5 snapshot has 31 SHA-256 entries passing and a PostgreSQL dump that
  `pg_restore -l` reads (186 entries).
- Live checks: all four Compose services healthy; API readiness 200; web local SSR
  200; internal `/api/v1/listings` 200; web restart count 0. Anonymous HTTPS `/`,
  `/healthz` and `/api/v1/listings` return 401 with `noindex, nofollow, noarchive`.
- Current-script full Compose restore rehearsal completed in an isolated project
  `avtorinok_rehearsal2_20260929_225157_96639`: backup took 22 s, restore 43 s,
  all four services returned healthy, and the restored listing/photo matched the
  original photo SHA-256 `81b722fd16b6b0d8ced07dc0eae47d540d5d823a3fde3bd51b244d67d1471b3a`.
  The temporary project, volumes and files were removed; this is not an off-host test.

Rollback: atomically point `/home/suite/apps/avtorinok` back to
`/home/suite/apps/releases/pilot-20260929T125300Z`, then run
`docker compose up -d --no-build --wait` from that release. Do not restore or delete
database/media volumes as part of an application rollback.

## Предыдущий релиз 28 сентября 2026, 05:25 UTC

Tag: `pilot-20260928T052525Z`. Выпуск был оставлен закрытым за Basic Auth и
`noindex`; Nginx/TLS конфигурация не менялась. Release хранится в
`/home/suite/apps/releases/pilot-20260928T052525Z`; для совместимости с daily
backup путь `/home/suite/apps/avtorinok` указывает на этот каталог. Предыдущий
source tree сохранён в `/home/suite/apps/avtorinok-before-20260928T052525Z`.

- API/worker: `avtorinok-api:pilot-20260928T052525Z`, image ID
  `sha256:5c8394ac102210805029a862bdadd10d5280ff931b7fb27c50300077c2a1880d`.
- Web: `avtorinok-web:pilot-20260928T052525Z`, image ID
  `sha256:15100f7d0c49b682e229834221aed1378952d33976e2d18b0671cbf96b747e11`.
- PostgreSQL: `postgres:17.11-alpine`, image ID
  `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`.
- Все три image проверены как `linux/amd64`; production build Next.js и TypeScript
  прошли во время последовательной сборки на VPS. Build storage preflight: около
  32.8 GiB свободно на filesystem и в Docker engine.
- Исходный архив: `/home/suite/apps/releases/pilot-20260928T052525Z/source.tar.gz`,
  SHA-256 `fa5c62640c819a3e9954f309dc346587b2cee0fb0f7307883376768d59985208`.
  `.env`, `.workflow`, node_modules, venv и Next build output исключены; 8
  разрешённых Drom source/report files включены. `.dockerignore` исключает
  `.workflow` и `data/licensed` из Docker build context.
- Alembic уже был на `0006_unbounded_generation_labels`; upgrade завершился без
  изменений схемы. PostgreSQL и media volumes сохранены без замены.
- Все три Drom batch импортированы после dry-run: 165,133 modifications,
  11,164 Drom generations и 10,684 Drom body variants. Итого в БД: 41 make,
  1,730 model, 11,180 generation, 10,708 body variant; создано 3 Drom import
  records. Crosswalk: 53 точных совпадения, 4 неоднозначные пары оставлены
  раздельно, 1,473 Drom модели без точного совпадения добавлены отдельно.
- Backup до импорта и переключения: `/home/suite/backups/avtorinok/avtorinok-20260928T053527Z`.
  Backup после deploy/import: `/home/suite/backups/avtorinok/avtorinok-20260928T064248Z`,
  формат 4; все 13 SHA-256 checksums прошли. Снимок содержит DB, media, каталог
  и лицензированные пакеты 1–3.
- Restore rehearsal post-deploy backup выполнен в отдельном PostgreSQL
  container/volume и отдельном media каталоге на том же VPS. `pg_restore`
  занял 3 секунды; восстановлены 165,133 Drom modifications и три import records;
  все шесть WebP-файлов декодировались и не содержали EXIF. Временные container,
  volume и каталог удалены. Это не off-host rehearsal и не измерение RTO.
- HTTPS smoke: без Basic Auth `/`, `/healthz`, `/api/v1/listings`, `/robots.txt`
  и photo path отвечают 401; с Basic Auth главная, API и health отвечают 200.
  `X-Robots-Tag: noindex, nofollow, noarchive` сохранён.
- Browser smoke: `/`, поиск, дилеры, помощь, вход, seller account/listings/favorites/company,
  форма продажи и moderation отвечают 200 по доступным ролям; 390px без overflow и
  JS ошибок. Seller/admin Secure HttpOnly cookies работают. Drom SSR показывает
  AITO M5, поколение, комплектацию и кузовной вариант в фильтрах/чипах.
- Live seller smoke прошёл черновик → JPEG upload → worker `ready` → moderation
  approve → public detail/search/WebP; phone не попал в public payload; избранное
  добавлено/прочитано/удалено. Smoke listing `63199a54-d0e2-4168-867d-4b93fe731c8a`
  и фото оставлены в `paused`; это синтетическое предложение, не товар на продажу.
- Главная показывает пустую выдачу, пока реальные продавцы не разместят объявления;
  тестовый smoke listing скрыт из неё в статусе `paused`.

Откат приложения без замены БД и media: атомарно переключить symlink
`/home/suite/apps/avtorinok` на сохранённый `avtorinok-before-20260928T052525Z`,
затем выполнить `docker compose up -d --no-build --wait` из этого каталога. Старый
tag `pilot-20260927T182200Z` и images сохранены. Схема уже была на migration 0006;
новые Drom rows additive, откат кода их не удаляет. Восстановление backup отдельно
перезапишет DB и потому требует отдельного решения. Symlink и images rollback
проверены только read-only/инвентаризацией; фактический app rollback не выполнялся.

**Остаётся:** off-host target/копия и off-host restore не настроены, целевые
RPO 24h/RTO 2h не измерены; свежие реальные HEIC с устройства не проверялись;
live company creation-to-public flow не повторялся на VPS, хотя он прошёл
локальную PostgreSQL integration suite; публичный запуск не выполнялся.
Владелец подтвердил, что все девять официальных пакетов Drom переданы для проекта
и письменное разрешение на их использование есть; этот выпуск сохраняет
исходные файлы и provenance в проверяемом backup.

## Предыдущий выпуск 27 сентября 2026, 18:22 UTC

Tag: `pilot-20260927T182200Z`; остальные разделы ниже сохраняют историю выпусков.
Обновлены поиск, сортировка, карточки, мои объявления, подача и preview модерации.
AMD64 API/web собраны на VPS; production build и TypeScript прошли.

- API: `sha256:07e1da31b98769060f5787514ec1c5aaad1069068d61c0fca8e14caade8187d0`.
- Web: `sha256:a7f438df75deae549240f51fd95aa6afe20e59974f107125529ca867e1e8a55a`.
- Архив: `/home/suite/apps/avtorinok-pilot-20260927T182200Z.tar.gz`, SHA-256
  `7ffe6226a09cc70525c7593eac935e1e6e95a260f225cda4f79f9ee6314b8557`.
- Backup: `/home/suite/backups/avtorinok/avtorinok-20260927T182328Z`;
  контрольные суммы базы, фото, каталога и manifest проверены.
- Старый код: `/home/suite/apps/avtorinok-before-20260927T182200Z`; образы сохранены.
- Alembic обновлён до `0006_unbounded_generation_labels`: добавлена provenance
  модификаций и расширены строковые поля поколений до TEXT, без удаления данных.
- Штатный каталог не изменён. Закрытые выгрузки `data/licensed` не передавались
  и не импортировались; локальные 165 тысяч модификаций Drom на VPS не заявляются.
- `.env`, тома, аккаунты, Nginx и внешний вход `admin` / `1111` сохранены.
  Все четыре сервиса healthy, backup.timer активен; свободно около 33 GiB.
- HTTPS browser smoke: реальный вход продавца и шесть страниц на 1440/390 px
  прошли с HTTP 200, без JS-ошибок и горизонтального переполнения; анонимно — 401.
- Полные backend-тесты, импорт Drom, нагрузочный тест и восстановление backup
  в рамках этого обновления не выполнялись.

Откат: остановить web/API/worker, сохранить текущий каталог под отдельным именем,
вернуть `avtorinok-before-20260927T182200Z` на `/home/suite/apps/avtorinok`
и запустить `docker compose up -d --no-build --wait`. Не удалять тома.
Не выполнять downgrade/restore автоматически: новые длинные строки нельзя
обрезать, восстановление старого backup теряет последующие записи. Откат не проверялся.

## Обновление 27 сентября 2026, 12:15 UTC

Текущий выпуск: `pilot-20260927T121527Z`. Разделы ниже — история предыдущих выпусков.
Обновлены `backend/app/api/auth.py`, `backend/app/api/media.py` и
`backend/app/catalog_import.py`. Интерфейс и каталог совпадают с предыдущим выпуском.

- Сборка AMD64 успешна; неизменённый web переиспользовал проверенный build cache.
- API ID: `sha256:efeb95e086a862a8e24bfe51fb6597f3b586793c53371501c1cf80c3889b31a9`.
- Web ID: `sha256:6db56b733395f865f2a490e703d7bd7cacc7694a62e2193c78154d8a3c24a03d`.
- Исходный архив: `/home/suite/apps/avtorinok-pilot-20260927T121527Z.tar.gz`.
  SHA-256: `992afd43bf32ebc274c79674db8ba220538cdbd1e0b39ffba529df942f0bb9dc`.
- Backup перед обновлением: `/home/suite/backups/avtorinok/avtorinok-20260927T121708Z`;
  контрольные суммы всех пяти файлов проверены.
- Предыдущий код и override: `/home/suite/apps/avtorinok-before-20260927T121527Z`.
- `.env`, аккаунты, media и том PostgreSQL сохранены; Alembic head остаётся
  `0004_geography_provenance`, импорт каталога сообщил `unchanged`.
- Все четыре контейнера healthy. Внешний временный вход `admin` / `1111`
  сохранён по запросу пользователя; пароли аккаунтов приложения не менялись.
- HTTPS-проверки прошли: реальный вход продавца; главная, поиск, компании,
  кабинет, мои объявления и подача на 1440/390 px — 200, без JS-ошибок
  и переполнения. API возвращает 25 марок и 8 типов кузова; анонимный вход — 401.
- Полный backend suite, нагрузочный тест и новое восстановление backup
  в рамках этого обновления не выполнялись.

Откат приложения: остановить web/API/worker, сохранить текущий каталог под
отдельным именем, вернуть `avtorinok-before-20260927T121527Z` на прежний путь
и запустить `docker compose up -d --no-build --wait`. Образы сохранены.
Не удалять тома и не восстанавливать базу автоматически. Откат не выполнялся.

## Обновление 27 сентября 2026, 11:06 UTC

Текущий выпуск: `pilot-20260927T110651Z`. Ниже после этого раздела сохранён
исторический отчёт первого развёртывания.

- Новый код собран на VPS для AMD64, production build и TypeScript прошли.
- API ID: `sha256:70036d7b754180162f760490b705a5432f51575c02cce0998e9e551aeb841d6b`.
- Web ID: `sha256:651e2d7e6e429252549902172f0663cc95a7f3bc4573faa99cd82aab8824e3fb`.
- Архив: `/home/suite/apps/avtorinok-pilot-20260927T110651Z.tar.gz`.
  SHA-256: `33e805eb34e07a5b06b642af81bf2ddbfb7c96edd084bcaf67e908231f691ef1`.
- Миграции применены до `0004_geography_provenance`. Они добавляют nullable-поля
  источников данных, не удаляя старые поля и записи.
- Каталог: 25 марок, 253 модели, 16 поколений, 8 типов кузова, 24 варианта,
  7 регионов и 12 городов. Полнота каталога не заявляется.
- До переключения сохранены база и фото:
  `/home/suite/backups/avtorinok/avtorinok-20260927T110827Z`.
  Все контрольные суммы прошли проверку.
- Старый код и override сохранены в `/home/suite/apps/avtorinok-before-20260927T110651Z`,
  отдельный архив кода — `/home/suite/backups/avtorinok-code-before-20260927T110651Z.tar.gz`.
- `.env`, учётные записи, Docker-тома, Nginx, HTTPS и Basic Auth сохранены.
- Все четыре контейнера healthy, backup.timer активен, свободно около 34 GiB.
- Через HTTPS проверен реальный вход продавца и шесть страниц (главная,
  автомобили, компании, кабинет, мои объявления, подача) на 1440 и 390 px:
  200, без JS-ошибок и горизонтального переполнения. Без Basic Auth — 401.
- Главная теперь имеет заголовок «Ваш автомобиль уже ждёт вас».
- В этом обновлении фото/модерация повторно не прогонялись; полный набор
  backend-тестов и нагрузочный тест VPS не запускались.

Для отката к предыдущему приложению остановить web/API/worker, сохранить новый
каталог под отдельным именем и вернуть каталог `avtorinok-before-20260927T110651Z`
на `/home/suite/apps/avtorinok`, затем выполнить `docker compose up -d --no-build --wait`.
Предыдущие образы сохранены. Не удалять тома и не откатывать БД автоматически:
восстановление backup потеряет данные, созданные после его снятия. Откат не выполнялся.

## Первое развёртывание

Проверено 27 сентября 2026 г. по HTTPS на `https://suite-s1.denjik.by`.
Это развёртывание текущей версии для тестирования, не открытый публичный запуск.

## Версия и размещение

- SSH: `ssh -p 23026 suite@178.124.211.251`.
- Приложение: `/home/suite/apps/avtorinok`.
- Тег API, worker и web: `pilot-20260927T065501Z`.
- API image ID: `sha256:54ad63b73a8698ea8c8f48df93d7c8fe1fdeb881b87130c109b4d71e15d662c5`.
- Web image ID: `sha256:4fd1885aab3946e87dd8d24b4acfdb8f11249bc78cd47c9e9c2aeaf07779c910`.
- Все три используемых образа, включая `postgres:17.11-alpine`, проверены как `linux/amd64`.
- Снимок исходников: `/home/suite/apps/avtorinok-pilot-20260927T065501Z.tar.gz`.
- SHA-256 снимка: `1bb6351dd4c0df89073dc14e14aef8b56e01f23908eb04054d0c1075dd36243a`.
- `.env`, локальные БД, media, node_modules, venv и build output в снимок не вошли.
- Сборка выполнена последовательно на VPS: API, затем web, штатным
  `scripts/build-amd64-images.sh`. Локальный Docker-кэш не очищался.
- Миграции БД: `0002_manual_city`; импорт: 25 марок, 253 модели,
  13 поколений, 7 регионов и 12 городов. Это объём загруженного снимка,
  не утверждение о полноте или независимо проверенном качестве каталога.
- `data/catalog.json` на VPS имеет права 644 для чтения API (UID 10001).
  Данные каталога не являются секретами; секретный `.env` остаётся 600.

`deploy/pilot-release.compose.yml` установлен на VPS как
`docker-compose.override.yml`. Он закрепляет точные теги для обычных команд
`docker compose`, включая резервирование. Локальная разработка этот override
не использует. После любых будущих обновлений требуется новый тег и проверка;
правки исходников сами по себе не обновляют запущенные контейнеры.

## Доступ

На первом экране браузер запросит HTTP Basic Auth: пользователь `pilot`.
Затем для кабинета доступны администратор `admin@suite-s1.denjik.by`
и продавец `pilot@suite-s1.denjik.by`. Письма на эти адреса не отправлялись;
это идентификаторы локальных пилотных аккаунтов.

Пароли не находятся в коде или этой документации. Защищённый файл на Mac:
`/Users/home/.config/avtorinok/pilot-access-20260927T065501Z.json` (600).
На VPS: `/home/suite/.config/avtorinok/pilot-access-20260927.json` (600).
`basic_auth` относится к первому запросу браузера, `accounts` — ко входу
в кабинет. Хранить файл приватно; не помещать в web-root или Git.

## Сеть и службы

- Внешний OpenResty и сертификат сохранены. HTTP перенаправляется на HTTPS.
- Nginx обслуживает порт 80 и проксирует web на `127.0.0.1:8080`.
- API 8000 и PostgreSQL 5432 не опубликованы на хосте.
- Basic Auth защищает HTML, API, изображения, статику, robots.txt и healthz.
- `X-Robots-Tag: noindex, nofollow, noarchive` сохранён.
- Конфигурация: `/etc/nginx/sites-available/suite-s1.denjik.by`;
  её исходник: `deploy/suite-s1.denjik.by.pilot.nginx.conf`.
- `/healthz` проверяет Nginx и Basic Auth, а не БД. Готовность приложения
  проверяется Docker healthchecks и обращением к API.
- Сессии используют Secure cookies; доверие API к proxy-IP не расширялось.
- После старта: 4 healthy-контейнера, около 35 GiB свободно на диске,
  около 2.4 GiB available RAM. Это снимок без существенной нагрузки.

## Выполненные проверки

Производственная сборка Next.js и TypeScript прошла на VPS. Миграции
успешно применены к новой БД; dry-run и импорт каталога завершились.
Проведены 43 автоматизированные проверки через реальный HTTPS-домен:

- Без Basic Auth: 401 для HTML, API, healthz, фото, статики и robots.txt.
- С Basic Auth: главная и healthz — 200; каталог — 25 марок;
  `.env` и публичная регистрация — 404.
- Вход продавца через браузер, переход в кабинет и Secure cookies.
- Создание черновика, загрузка PNG, обработка worker в WebP.
- Приватное фото до публикации недоступно без входа в кабинет.
- Отправка на модерацию, одобрение администратором, открытие SSR-карточки
  и опубликованного изображения; после паузы карточка снова скрыта.
- Главная, поиск, кабинет и форма подачи на 1440x1000 и 390x844:
  HTTP 200, без горизонтального переполнения и ошибок JavaScript.
- Logout отзывает сессию: последующий `/api/v1/me` возвращает 401.

Синтетическое объявление `1884d65b-90d2-4081-8059-46f543628200` оставлено
в состоянии `paused` в кабинете пилотного продавца. Заголовок:
`Deployment smoke test - not for sale`. Это не реальное предложение;
в общей выдаче оно не отображается. Его три варианта фото входят в backup.

## Резервирование

Включён `avtorinok-backup.timer`: ежедневно в 03:15 UTC с задержкой до 15 минут.
Каталог: `/home/suite/backups/avtorinok`. Сохраняются семь локальных копий.
При резервировании web/API/worker кратковременно останавливаются и запускаются
обратно; PostgreSQL продолжает работать.

Первый backup: `avtorinok-20260927T070604Z`, около 448 KiB.
`Result=success`, `ExecMainStatus=0`. SHA-256 базы, media, каталога и manifest
совпали, gzip media прошёл проверку. После backup все четыре контейнера
вернулись в healthy, сайт повторно проверен. Полное восстановление именно
этого VPS-backup не выполнялось; прежние локальные restore-проверки — отдельные.

Архив FORTEBIT в `/home/suite/backups/online-shop-retirement-20260926-190522`
не изменялся. Off-host backup пока не настроен.

## Управление и откат

Обычная проверка с VPS:

```sh
cd /home/suite/apps/avtorinok
docker compose ps
docker compose logs --since 10m --tail 50
docker compose up -d --no-build --wait --wait-timeout 120
sudo nginx -t
systemctl list-timers avtorinok-backup.timer
```

Не запускать `docker compose down -v`: это удалит данные нового сайта.
Для отката только к прежней заглушке сначала остановить таймер, вернуть
проверенный конфиг Nginx, проверить и перезагрузить его, затем остановить
контейнеры без удаления томов:

```sh
sudo systemctl disable --now avtorinok-backup.timer
sudo install -o root -g root -m 644 /home/suite/backups/avtorinok-deploy-20260927T065501Z/nginx-before.conf /etc/nginx/sites-available/suite-s1.denjik.by
sudo nginx -t && sudo systemctl reload nginx
cd /home/suite/apps/avtorinok
docker compose stop
```

Это не восстанавливает старый магазин. Его отдельный архив описан
в `deploy/RETIREMENT.md`. Процедура отката документирована, но не выполнялась.

## Ограничения пилота

- Нагрузочный тест на VPS не выполнялся; 3.3 GiB RAM ниже исходного ориентира 8 GiB.
- Показ телефона ограничен 30 запросами в час на аккаунт и покрыт интеграционными тестами. Дополнительный IP-лимит не включён, пока не проверены цепочка прокси и защита от подмены forwarded-заголовков.
- Каталог и география не считаются полными.
- Новый сценарий компании полностью на VPS не проходили; проверен сценарий частника.
- Внешнее резервирование, обновление ОС и ожидающая перезагрузка не выполнялись.
- Публичный запуск, снятие Basic Auth, открытая регистрация и SEO-индексация
  требуют отдельного решения.


## 4 октября 2026 — общий релиз и снятие HTTP Basic Auth

Развёрнут `pilot-20261004T123401Z`, ревизия `64d2903`, миграция `0022_listing_categories`. Калькулятор доступен на реальном сайте, общий пароль отключён по запросу пользователя. 600 backend/422 frontend tests passed; HTTPS и browser desktop/mobile проверены без общего пароля; обычные user/admin входы проверены. Данные и тома сохранены, pre/post backups verified. Детали и ограничения: [отчёт релиза](docs/runtime/RELEASE_2026-10-04.md).
