# Релиз audit-20261111-r1 — порядок выкатки

Источник: ветка `prod-sync-20261110`, `git archive HEAD`. Сервер: alias `fortebit-prod`, пользователь `suite` (группа docker, без sudo).
Каждый серверный скрипт — Python 3 stdlib, запускается через stdin, печатает служебный ход в stderr и **одну итоговую JSON-строку** в stdout.
Квитанции (mode 600) пишутся в `/home/suite/backups/avtorinok/audit-20261111-r1/` (mode 700).

Ни один скрипт не читает и не печатает значения `.env`, не делает `down`, `-v`, prune томов или не-dangling образов, не трогает nginx, systemd и чужие контейнеры.

## Последовательность

Перед шагами 3 и 5 — явное «ок» тимлида/пользователя (гейт из `CLAUDE.md`).

### 0. Локально: архив исходников

```sh
bash /Users/home/Downloads/avbyartur-prod/output/audit-release-20261111-r1/00-local.sh
```

Печатает путь архива, размер, commit, sha256 и команду `scp` (сам не запускает). Пишет рядом `src.sha256` и `src.commit`.
Отказ: HEAD не на `prod-sync-20261110`; в дереве есть незакоммиченные или неотслеживаемые файлы; в архиве оказался `.env`; в архиве нет `docker-compose.yml`, Dockerfile'ов, `alembic.ini`, `data/catalog.json`.

Загрузка (вручную):

```sh
scp /Users/home/Downloads/avbyartur-prod/output/audit-release-20261111-r1/src.tar.gz \
  fortebit-prod:/home/suite/apps/releases/audit-20261111-r1.src.tar.gz
```

### 1. Подготовка (без изменения сервисов)

Вписать sha256 из шага 0 в `SRC_SHA256` в `10-prepare-server.py`, затем:

```sh
ssh fortebit-prod python3 - < 10-prepare-server.py
```

Что делает по порядку. Сначала только чтение: активная ссылка = `refero-20261108-r1`; 5 контейнеров `running`/`healthy` и принадлежат проекту `avtorinok`; `.env` — symlink, mode 600 (только `stat`); тома `avtorinok_postgres` и `avtorinok_private_media` смонтированы; цепочка web из 16 файлов кончается `docker-compose.refero.yml`; каталоги релиза, `.partial` и бэкапа не существуют; `alembic current` = `0033_listing_in_transit`; снимок HTTP через nginx (`capabilities`, заголовок главной, `/login` → `login_has_register_entry`, статусы несуществующего и архивного объявления); прежние compose-цепочки api/worker и web (они разные) резолвятся в те же образы, что сейчас запущены (готовность отката); sha256 архива; файлы `data/` из текущего маунта api есть в архиве.
Потом запись: очистка диска при < 9 GiB (`docker builder prune -f --filter until=72h`, `docker image prune -f` — только dangling), затем нужно ≥ 7 GiB; `before.json`; `pg_dump -Fc` → `database.dump` + проверка `pg_restore -l` + `database.sha256`; теги `avtorinok-web:rollback-audit-20261111-r1` и `avtorinok-api:rollback-audit-20261111-r1`; распаковка архива в `.audit-20261111-r1.partial` с защитой от path traversal и переименование в `/home/suite/apps/releases/audit-20261111-r1`; symlink `.env` на тот же realpath; `docker-compose.audit.yml`; `docker compose … config` и проверки (образы api/worker/web = тег релиза, образ db не меняется, у api/worker/db нет published ports, порт web как у работающего, имена томов те же, `AVTORINOK_PUBLIC_INDEXING_ENABLED=true` в env и build args web, bind-источники существуют); `env-diff.json` (только имена переменных); `rollback.json`; `prepared.json`.

Печатает: `dump_bytes`, `disk_free_gib`, `pruned`, `login_has_register_entry`, `listing_probe_status`, `rollback_groups`, `env_diff` (по api/worker/web списки `added`/`removed`/`changed` только с именами и `feature_flags`: `same`/`changed`/`added`/`removed`/`absent`), `env_diff_sha256`.

**Ревью env diff обязательно.** Новый `docker-compose.yml` отдаёт api и worker все поля `Settings`; переменные, которые раньше лежали в `.env`, но до контейнера не доходили, теперь включатся. Если в `feature_flags` есть `changed`/`added` для флагов регистрации, SMS, тестовой почты — `capabilities` после деплоя будут отличаться, и шаг 3 откатит релиз автоматически. Решить это до шага 3. После ревью вписать `env_diff_sha256` в `APPROVED_ENV_DIFF_SHA256` в `30-deploy-server.py`.

Отказ после начала записи (бэкап уже создан): повторный запуск откажется. Восстановление вручную: переименовать бэкап-каталог в `…/audit-20261111-r1.failed-<время>` (дамп не удалять), удалить только каталоги `/home/suite/apps/releases/audit-20261111-r1` и `.audit-20261111-r1.partial` (там только распакованные исходники и symlink `.env`). Затем исправить причину и запустить снова.

### 2. Сборка образов и preflight

```sh
ssh -o ServerAliveInterval=30 fortebit-prod python3 - < 20-build-server.py
```

`docker compose … build api web` (вывод — только в `build.log`, при ошибке печатается хвост из 40 строк после редакции). Проверки: образы `avtorinok-api:audit-20261111-r1` и `avtorinok-web:audit-20261111-r1` существуют, amd64 и отличаются от запущенных. Затем во временных контейнерах `compose run --rm --no-deps -T api`, без запуска сервисов: `get_settings()` → `config-ok` (при ошибке печатаются только класс исключения и имена полей pydantic); `alembic heads` — ровно одна голова, не `0033`; `alembic current` — `0033_listing_in_transit` или уже новая голова. Пишет `built.json`, `preflight.log`.
Печатает: id образов, `preflight.alembic_head`, время сборки, свободный диск. Повторный запуск допустим, пока нет `deployed.json`. Если SSH оборвался во время сборки, процесс на сервере тоже прервётся, тогда запустить шаг 2 снова.

### 3. Деплой (после «ок»)

```sh
ssh -o ServerAliveInterval=30 fortebit-prod python3 - < 30-deploy-server.py
```

Предусловия: `APPROVED_ENV_DIFF_SHA256` совпадает с `env-diff.json`; активная ссылка, id и образы всех 5 контейнеров, `StartedAt` db не изменились с шага 1; теги релиза указывают на собранные образы; нет `deployed.json`.
Шаги: `alembic upgrade head` через `run --rm --no-deps -T api` → `alembic current` = голова из шага 2; `up -d --no-deps --no-build --wait --wait-timeout 180 api worker`, затем то же для `web`. Проверки (именованные, неудачные повторяются один раз через 15 с): `containers_healthy`, `db_unchanged` (id и StartedAt), `images_match_built`, `home_via_nginx` (200, заголовок содержит «Автомобили Беларуси», нет `AURUM`, нет `X-Robots-Tag: noindex`), `csp_frame_ancestors`, `capabilities_unchanged` (равенство с `before.json`), `listings_page`, `catalog_makes_cache` (`max-age`), `api_health_ready` (`/health/ready` из контейнера api: `status=ok` и объект `worker`), `dealers_page`, `missing_listing_not_5xx` (нулевой UUID → 404/410; архивное объявление → тот же код, что до релиза), `login_register_entry` (если до релиза на `/login` был «Создать аккаунт», он должен остаться). `POST /api/v1/analytics/errors` и другие запросы с записью не выполняются.
Успех: атомарная смена `/home/suite/apps/avtorinok` (symlink во временное имя + `os.replace`), `deployed.json`, `deployment-receipt.json` в каталоге релиза, `rollback.json` дополнен. Печатает статус проверок, возраст heartbeat воркера, путь к `rollback.json`.
Сбой миграции: контейнеры не тронуты, `{"deployed": false, "rolled_back": false, "failed_check": "migration"}`, код 1.
Сбой с `up` и дальше: **автоматический откат** api+worker по их прежней цепочке (каталог `editorial-ux-20261102-r2` из меток контейнера api), web — по цепочке `refero-20261108-r1`; проверка, что прежние id образов запущены и healthy; ссылка остаётся (или возвращается) на `refero-20261108-r1`; БД не откатывается. Печатает `{"deployed": false, "rolled_back": true|false, "failed_check": …}` и пишет `deploy-failed.json`. Код 1, если откат удался, и 2, если нет: тогда сразу шаг 5.
Повторный деплой после автоотката этим же тегом невозможен (id контейнеров изменились), нужен новый prepare (`-r2`).
Если SSH оборвался посреди шага 3, состояние неизвестно: запустить шаг 4 и по его выводу решить, нужен ли шаг 5.

После шага 3 вручную в браузере: `https://авторынок.бел/login?next=%2Fsell` → «Создать аккаунт» открывает поля имени, email, пароля, повтора, согласий и кнопку «Зарегистрироваться» (`AGENTS.md`). С сервера публичный HTTPS недоступен, поэтому это делается снаружи.

### 4. Пост-проверка (только чтение)

```sh
ssh fortebit-prod python3 - < 40-post-server.py
```

Образы и health 5 контейнеров против `deployed.json`, `RestartCount`, `alembic current` (= голова), возраст свежайшего `worker_heartbeats.last_seen_at` (psql внутри контейнера db через `sh -c`, учётные данные не печатаются; ≥ 60 с — проблема), число JSON-строк логов уровня error/critical по именам событий для api и worker с момента деплоя (тела логов не печатаются), свободный диск. Пишет `post-<время>.json`. Код 0, если `problems` пуст, и 3, если нет. Повторить через 10–15 минут.

### 5. Ручной откат

```sh
ssh fortebit-prod python3 - < 90-rollback-server.py
```

Та же логика, что у автоотката: если тег прежнего образа куда-то уехал, сначала возвращает его из `rollback-audit-20261111-r1`; `up -d --no-deps --no-build --wait` по прежним цепочкам (api+worker, затем web); ждёт healthy на прежних id образов; возвращает ссылку на `refero-20261108-r1`; проверяет, что контейнер db не пересоздан и не перезапущен. БД и тома не трогает. Повторный запуск безопасен. Пишет `rolled-back.json`.
Схема после отката остаётся на `0034` (аддитивная, совместима со старым api). Откат данных — только отдельным решением через `database.dump`.

## Что этот релиз НЕ делает (нужен root, отдельная задача)

- nginx: `set_real_ip_from`/`real_ip_header` из `deploy/avtorinok-domain.nginx.conf` не применяются, лимиты по IP остаются в режиме «IP неизвестен».
- systemd: юниты монитора с алертами и off-host бэкапа из `deploy/systemd/` не устанавливаются и не перезапускаются.
- `/etc/avtorinok/*` и прочие файлы вне `/home/suite` не создаются и не меняются.
- `.env` не меняется. Новые переменные из `.env.example` нужно добавить вручную, отдельно.
- Не удаляются старые релизы, образы и бэкапы; prune только dangling-образов и build cache старше 72 ч.
- Нет даунгрейда БД, нет restore, нет импорта данных, нет записей через публичное API.
- `docs/STATUS.md`, `ROLLBACK.md` и журнал релиза в репозитории обновляются отдельно, после шага 4.

## Файлы

| Файл | Назначение |
|---|---|
| `00-local.sh` | архив, sha256, commit, команда scp |
| `10-prepare-server.py` | снимок, дамп, теги отката, распаковка, overlay, проверка compose, env diff |
| `20-build-server.py` | сборка api/web, preflight настроек и Alembic |
| `30-deploy-server.py` | миграция, up, 12 проверок, автооткат, смена ссылки |
| `40-post-server.py` | пост-проверка только на чтение |
| `90-rollback-server.py` | ручной откат приложения |

Квитанции на сервере: `before.json`, `prepared.json`, `env-diff.json`, `rollback.json`, `database.dump`, `database.sha256`, `build.log`, `preflight.log`, `built.json`, `migrate.log`, `deploy.log`, `deployed.json` или `deploy-failed.json`, `rollback.log`, `post-*.json`, `rolled-back.json`.
