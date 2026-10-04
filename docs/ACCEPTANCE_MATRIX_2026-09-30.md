# Авторынок: матрица приёмки и эксплуатационных блокеров

Дата среза: 30 сентября 2026 года. Матрица сверяет согласованный P0 из
[`docs/superpowers/plans/2026-09-26-avtorinok-pilot.md`](superpowers/plans/2026-09-26-avtorinok-pilot.md)
с исходниками, локальными проверками и текущим закрытым VPS-релизом. Она не
превращает успешный локальный тест в доказательство серверной приёмки.

Текущий релиз: `pilot-20260930T004119Z` на `suite-s1.denjik.by`. Развёртывание
сообщило о четырёх healthy-сервисах; внешний edge smoke и браузерный smoke
`29/29` прошли. Пилот остаётся за HTTP Basic Auth и `noindex`; активных
публичных объявлений нет. Post-deploy backup и повторная проверка SSH-зависимых
значений `.env`, томов и restart count пока не завершены из-за отказа SSH
аутентификации. Подробные временные доказательства и исторические срезы сохранены в
[`DEPLOYMENT.md`](../DEPLOYMENT.md) и
[`docs/IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md).

Статусы: **Подтверждено** означает, что указанное доказательство существует;
**Частично** означает, что выполнен только названный срез; **Заблокировано**
означает отсутствие внешнего условия; **Отложено** означает согласованную
границу P0; **Не проверено** означает, что нельзя делать вывод по имеющимся
данным.

## Согласованный P0

| Требование плана | Текущее состояние | Доказательство и граница |
|---|---|---|
| §2.1 FastAPI + Next.js + PostgreSQL + worker в Compose | **Подтверждено для core; последние локальные правки ожидают релиза** | Current checkout backend `234` tests and web `208` tests across `43` files pass; typecheck, optimized production build and Compose config also pass. In the last confirmed VPS release API, worker, web and PostgreSQL were healthy, with only web published on loopback. |
| §2.2 Каталог: происхождение, стабильный импорт и минимум seed | **Частично** | Последний подтверждённый VPS-срез содержал 94 марки, 2 630 моделей, 14 009 поколений, 13 273 кузовных вариантов и 194 817 модификаций; все девять Drom-пакетов импортированы. Свежая локальная сверка CSV насчитала 194 817 строк и уникальных source URL; контрольные границы поколений подтверждены не полностью, `generation_depth_verified=false`. |
| §2.3 Частный вход, роли, компании, закрытая регистрация | **Частично** | Basic Auth и индивидуальные сессии/роли проверены; регистрация возвращает 404, cookies Secure/HttpOnly. Полный API-сценарий компании (создание → одобрение → публикация дилерского объявления → блокировка и скрытие) прошёл на одноразовой PostgreSQL БД; дублирующий УНП даёт `409`. Stateful путь ещё не повторён на VPS; локальные валидационные правки ожидают релиза. |
| §2.4 Черновик и форма подачи | **Подтверждено для частника** | Live seller smoke в историческом VPS-срезе прошёл каталог → draft → JPEG → worker `ready` → moderation; сохранение формы и ошибки покрыты локальными тестами. Реальный HEIC с телефона ещё не проверен. |
| §2.5 Статусы, премодерация, квоты и ревизии | **Подтверждено локально; частично на VPS** | Локальные тесты покрывают pending/active, pause/sold/block/archive, квоты, stale revision `409`, аудит и конкуренцию. На VPS 100 draft и 2 paused, active public `0`, поэтому buyer-facing lifecycle на текущих данных не повторён. |
| §2.6 Приватные фото и worker | **Подтверждено локально; частично live** | JPEG upload, WebP, EXIF removal, private access и worker retry покрыты тестами; VPS seller smoke доставил WebP без телефона в public payload. Реальный HEIC и отказоустойчивость на production release не подтверждены отдельным свежим прогоном. |
| §2.7 Поиск, фильтры, карточка, избранное и контакт | **Подтверждено для доступного среза** | Локальный browser/API acceptance и VPS seller smoke покрывают search/detail/favorite/contact omission; текущая VPS выдача пуста (`active=0`), поэтому активная публичная карточка не доступна для нового серверного клика. |
| Saved-search notifications vertical slice | **Подтверждено на текущем VPS; email unsupported** | Migration `0009_notification_outbox` is head. Saved-search matching enqueues an outbox and idempotently delivers an in-app web notification; authenticated list/read endpoints and worker regressions are covered by `backend/tests/test_saved_search_notifications.py`, and `/account/notifications` returned 200 in the deployed release. Email selections are retained as `unsupported` with `email_provider_unconfigured`; no email provider is configured. |
| §2.8 API-контракт и generated TypeScript types | **Подтверждено** | OpenAPI generator создаёт типы для 51 paths, включая live/ready health paths; web typecheck и deterministic generation проходят. В отдельных route errors остаётся неполная детализация статусов, это не блокирует закрытый P0 smoke. |
| §3.1 Страницы и SSR | **Подтверждено для закрытого пилота** | Внутренний SSR текущего релиза возвращает 200 для `/`, `/cars`, `/dealers`, `/help`, `/account/saved-searches`; browser runner проверяет public routes, mobile widths и пустую выдачу. |
| §3.2 Визуальное направление и мобильность | **Частично** | Playwright проверяет отсутствие horizontal overflow на заявленных widths в локальном/доступном smoke. Проверка на реальных телефонах ещё не выполнена. |
| §3.3 SEO | **Подтверждено для закрытого режима; public launch blocked** | `noindex, nofollow, noarchive` и Basic Auth подтверждены на edge; canonical/metadata и пустой sitemap соответствуют закрытому пилоту. Публичные sitemap/structured-data/индексация должны пройти отдельную legal/public-launch приёмку. |
| §3.4 Security and operations | **Частично** | Права, CSRF, rate limits, private media, request IDs и закрытые API/DB ports покрыты кодом/тестами. Свежий anonymous edge smoke подтвердил четыре ожидаемых `401` с `noindex`; authenticated checks пропущены без credentials. `.env` mode `600` и именованные тома проверялись для предыдущего релиза; после переключения на `004119Z` свежий SSH readback заблокирован. Off-host copy/restore, production RPO/RTO и полный security review остаются открытыми. |
| §3.4 Daily backup, seven copies, restore rehearsal | **Локально подтверждено; post-deploy backup нового релиза ожидает SSH** | Backup/restore/offsite/retention/daily suites: 59 тестов; isolated Compose rehearsal 22/43 s с совпавшим SHA-256 фото. Для релиза `004119Z` pre-deploy snapshot проверен (31 checksum и `pg_restore -l`); post-deploy snapshot не создан, production restore не выполнялся. |
| §5.1 Acceptance load: 10k listings, 20 VU/20 RPS, p95 ≤500 ms | **Частично** | Current-source isolated sidecar: 12 000/12 000 HTTP 200, search p95 34.99 ms, detail p95 14.31 ms, host guard passed. Это не измерение текущего VPS release image; production-load run остаётся открытым. |
| §5.2 Deployment preflight, version, rollback record | **Частично подтверждено; latest local changes await deploy** | `pilot-20260930T004119Z` is the last confirmed active release; deployment output reported four healthy services, browser smoke passed `29/29`, a fresh anonymous edge smoke passes, and rollback release is retained. New local company-validation and mobile-navigation fixes are verified but not deployed. SSH-agent is empty, preventing host reread and post-deploy backup; local Buildx advertises only ARM64/386, so it cannot build the required AMD64 release image. Rollback was not executed. |

## Что не является дефектом P0

Следующие элементы исходного ТЗ v1 сознательно перенесены за границы первой
поставки: SMS/public registration, external login, chat, dealer feeds, employee
teams, payments, promotion, external fraud/VIN services, and external email/SMS
notification providers. Saved-search preferences and in-app web delivery are
implemented in the current source vertical slice; email remains explicitly
unsupported until a provider is configured.

## Блокеры до публичного запуска

| Блокер | Почему он остаётся блокером | Как закрыть |
|---|---|---|
| Off-host encrypted backup | Шифрованная упаковка, decrypt и opt-in transfer реализованы и локально тестируются; реальный target/SSH credentials не заданы, transfer и off-host restore не подтверждены | Настроить age recipient, owner-managed target и SSH host key; выполнить encrypted preflight и явный transfer, затем отдельный изолированный off-host restore rehearsal. Тесты v1–v5 и stubbed remote path не заменяют эти проверки. |
| RPO/RTO | Isolated 22/43 s — это локальная метрика, не production RPO/RTO | Зафиксировать timestamp последнего backup, измерить off-host restore и записать фактические значения против RPO 24 h/RTO 2 h. |
| Company flow on VPS | Local integration и page load не доказывают stateful production journey; проектные инструкции запрещают добавлять synthetic data на VPS | Повторить путь в отдельном изолированном стенде с синтетическим набором либо использовать предоставленные владельцем реальные company/account/listing данные с явным разрешением. Не создавать синтетические записи на VPS. |
| Real-device HEIC | Локальная обработка и JPEG smoke не заменяют iOS/Android samples | Передать безопасные тестовые HEIC-файлы и прогнать upload/worker/EXIF checks на закрытом пилоте. |
| Release-image load | Current-source sidecar не равен deployed image/host | Поднять отдельный изолированный стенд из текущего release image, загрузить синтетический набор из 10 000 объявлений и повторить профиль §5.1; нагрузку и synthetic data не направлять на текущий VPS. |
| Legal and public indexing | Pilot noindex is intentional; operator/legal data and public launch approval are external | Собрать юридические реквизиты/политики, проверить canonical/sitemap/structured data, получить явное разрешение на снятие Basic Auth/noindex. |

## Безопасные проверки без внешнего провайдера

Все проверки ниже read-only, если отдельно не указано иное:

```sh
sh -n scripts/smoke-pilot-edge.sh scripts/release-preflight.sh \
  scripts/backup-offsite.sh scripts/backup-offsite-preflight.sh
python3 -m unittest scripts.test_smoke_pilot_edge scripts.test_release_preflight \
  scripts.test_backup_encryption scripts.test_backup_offsite_encrypted \
  scripts.test_backup_offsite
./scripts/release-preflight.sh --release-dir . --skip-compose
```

Для edge smoke задайте `SMOKE_BASIC_AUTH_USER` и
`SMOKE_BASIC_AUTH_PASSWORD` только через защищённое окружение; скрипт не печатает
их и не изменяет сервер:

```sh
./scripts/smoke-pilot-edge.sh --base-url https://suite-s1.denjik.by
```

Без credentials он проверяет anonymous `401` и `X-Robots-Tag: noindex`; с
credentials добавляет authenticated `200`. Browser smoke
`scripts/smoke-pilot-ui.py` остаётся отдельным read-only проверяющим маршруты и
не выполняет seller/admin branches без явно переданных credentials.

После создания локального `.tar.age` bundle encrypted offsite preflight
проверяет file/header и удалённые prerequisites через read-only SSH; он не
создаёт каталог, staging или backup:

```sh
AVTORINOK_OFFSITE_TARGET='backup-user@backup-host:/srv/avtorinok-backups' \
  ./scripts/backup-offsite.sh --encrypted-bundle --preflight \
  "$HOME/avtorinok-backups/avtorinok-YYYYMMDDTHHMMSSZ.tar.age"
```

До появления реального target локальные tests/stubs или отказ
`AVTORINOK_OFFSITE_TARGET is required` не подтверждают off-host backup.
