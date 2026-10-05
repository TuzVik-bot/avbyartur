# Runtime Runbook

> **5 октября 2026:** активный выпуск `marketplace-20261005T0956Z-baa9102`, Alembic head `0023_managed_articles`. По явному запросу пользователя общий HTTP Basic Auth отключён; не включать его повторно без нового запроса. Анонимные страницы отвечают 200, `/api/v1/me` без сессии — 401, `noindex` сохранён. Все четыре сервиса healthy; `.env` mode 600, именованные тома сохранены. Текущие backup, live smoke и ограничения — в [DEPLOYMENT.md](../../DEPLOYMENT.md). Авторизация аккаунтов и внутренняя маршрутизация API/БД остаются обязательными.

## Local Run

Docker Compose builds the app from `backend/Dockerfile` and `web/Dockerfile`. PostgreSQL, API, worker, and web each run in Compose. The database and private photo volume are named volumes and survive `make down`; do not use `docker compose down -v` for routine stops.

1. Create the ignored runtime env file once with `make secrets`. The command refuses to replace an existing file, writes it with mode `600`, and does not print values.
2. For browser-only local HTTP testing, set `APP_ENV=development` and `SESSION_COOKIE_SECURE=false` in `.env`. Keep the bound port on loopback.
3. Run `make up`. It builds the local images, starts PostgreSQL, stops API, worker, and web while Alembic migrations run, then starts those three services.
4. Run `make catalog-import-dry-run`; inspect its counts, then use `make catalog-import` to apply the seed.
5. Open `http://127.0.0.1:8080`. The host Basic Auth proxy is not part of local Compose.

`make config-check` validates Compose with the local image tag and the catalog JSON. Local build, start, inspection, and catalog-import Make targets use `local`, even if `AVTORINOK_IMAGE_TAG` is set in the shell. `make backup` follows the tag configured for the active Compose stack so its one-off API container uses the same image. Health checks cover PostgreSQL readiness, API readiness, web HTTP response, and worker process liveness.

## AMD64 Release Build

Use a dated or otherwise unique release tag; do not use `local` or `latest`:

```sh
make release-amd64 AVTORINOK_IMAGE_TAG=pilot-2026-09-27
```

The script requires at least 15 GiB free on both the project filesystem and Docker engine storage, builds the API image and then the web image for `linux/amd64`, pulls the pinned PostgreSQL image for the same architecture, verifies all three architectures, and prints their local image sizes. Compose's default image tag remains `local`; pass the release tag to Compose when testing or starting those images:

```sh
export AVTORINOK_IMAGE_TAG=pilot-2026-09-27
docker compose config --quiet
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d --no-build api worker web
```

The API and worker share one image. `--no-build` makes the final start use only the already-verified release images. These direct Compose commands intentionally use the exported release tag; local Makefile lifecycle and catalog-import commands override it with `local`. Keep the release tag set when running `make backup` against this stack. The image sizes reported by Docker are local uncompressed sizes, not registry transfer sizes.

## Closed Pilot Host

The pilot plan's sizing guideline is 4 vCPU, 8 GiB RAM, and at least 60 GB SSD. The 2026-09-26 inventory recorded about 3.3 GiB RAM and a 49 GB filesystem, with roughly 37 GiB free after cleanup; those RAM and filesystem figures are historical. A fresh read-only preflight on 2026-09-30 confirmed `x86_64`, Docker `linux/amd64`, 4 vCPU and about 72 GiB free on the 99 GiB filesystem; it did not confirm a separate data-disk mount. Compose caps the containers at 2.25 GiB RAM and 3.5 CPU in total. At the historical RAM size that leaves roughly 1 GiB for Ubuntu, Docker, and filesystem cache. PostgreSQL is configured with 128 MiB shared buffers, 4 MiB work memory, and 40 connections. This is a bounded pilot budget; it is not a load-test result.

Run the project under a separate application directory such as `/home/suite/apps/avtorinok`, outside `/var/www/suite-s1.denjik.by`. Create `.env` on the host with `./scripts/init-secrets.sh`; keep it mode `600`. Use the tagged `linux/amd64` images verified by the AMD64 release procedure above, then transfer and load those exact image tags on the VPS. Never deploy ARM images to this host. Compose uses ordinary named volumes, so PostgreSQL and media will live under Docker's configured data-root unless the deployment is changed. Before deployment, check `docker info --format '{{.DockerRootDir}}'`, its backing mount, and free space; the prior inventory does not confirm a separate data disk.

Only web is published, as `127.0.0.1:8080:3000`. API port 8000 and PostgreSQL 5432 have no host port mapping. The existing Nginx and upstream TLS proxy remain in place. The checked-in `deploy/suite-s1.denjik.by.nginx.conf` is a static-site placeholder, not the pilot proxy. For the pilot, the correct vhost proxies the app to `127.0.0.1:8080`; general HTTP Basic Auth is intentionally disabled by explicit user request for portal testing. Keep `noindex`, application-account authentication, private API/database routing, and review the proxy against trusted `X-Forwarded-Proto` settings before any Nginx reload. Re-enable general Basic Auth only after a new explicit request.

Generate the hash and one-time password handoff file on the VPS with:

```sh
sudo ./scripts/generate-pilot-auth.sh \
  --htpasswd /etc/nginx/.htpasswd-suite-s1.denjik.by \
  --password-file /root/.config/avtorinok/pilot-password
```

The script refuses to overwrite either output. It stores only a SHA-512 crypt hash in the Nginx file with mode `640` and group `www-data`; it does not print the hash or password. The plaintext handoff is mode `600`, outside the repository. Distribute the password through an approved private channel, then remove the handoff file when it is no longer needed. Keep `.env` separate; it contains the database and application session secrets, not the Basic Auth password.

Before reloading Nginx, verify its config with `nginx -t`. Preserve the existing TLS and upstream proxy settings. Do not expose Compose ports directly. While the portal is available without a general password for testing, keep `X-Robots-Tag: noindex, nofollow, noarchive` and application-account access controls. Removing `noindex`, enabling public registration, or declaring a public launch requires separate approval.

## Application Accounts

Public registration remains disabled for the pilot. Create named test accounts with the backend CLI inside the API image. Supply each password over stdin from an interactive secure prompt; do not put passwords in shell arguments, Compose files, or source control. The shared Basic Auth credential does not replace application sessions or roles.

Block or reactivate an account with `set-user-status`. Supply the target user ID, an active admin's user ID, and a non-empty reason; the reason is retained in the moderation audit. Run the command inside the API container:

```sh
docker compose exec -T api python -m app.cli set-user-status \
  --user-id "$USER_UUID" \
  --status blocked \
  --actor-id "$ACTIVE_ADMIN_UUID" \
  --reason "Repeated fraudulent listing reports"
```

Use `--status active` to reactivate the account. Blocking revokes all existing sessions. Reactivation does not restore those sessions, so the user must sign in again. The CLI rejects an actor that is missing, inactive, or not an admin; it does not add a public account-management endpoint.

## Routine Operations

- `make down` stops services and preserves both named volumes.
- `make up` rebuilds the local images, starts PostgreSQL, stops API, worker, and web while Alembic migrations run, then starts those three services.
- `make catalog-dry-run` fetches and validates a new Wikidata subset without writing files.
- `make catalog-refresh` replaces the source snapshot after preserving non-Wikidata records already present.
- `make catalog-import-dry-run` validates the mounted catalog through the backend importer.
- `make catalog-import` applies it; the importer preserves stable IDs and manual database overrides and never deletes omitted rows.
- `make backup` writes a checksummed database, photo, and catalog backup outside the repository by default.

### Automatic Backup Timer

The Linux systemd unit templates assume the project is installed at `/home/suite/apps/avtorinok`, runs as user/group `suite`, and writes backups to `/home/suite/backups/avtorinok`. Confirm or edit those values and `ReadWritePaths` before installation. The backup path is on the host's local filesystem; the timer keeps seven copies and does not copy them off-host.

```sh
sudo install -o root -g root -m 0644 deploy/systemd/avtorinok-backup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/systemd/avtorinok-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now avtorinok-backup.timer
systemctl list-timers avtorinok-backup.timer
sudo systemctl start avtorinok-backup.service
sudo journalctl -u avtorinok-backup.service --since today
```

Verify the service result and checksum a generated backup. Use the explicit encrypted-bundle workflow in [off-host-backup.md](off-host-backup.md) to preflight and copy it; the timer itself does not upload or prune encrypted bundles, and local copies do not protect against VPS or disk loss.

The current closed-pilot deployment and its read-only verification are recorded in
`DEPLOYMENT.md` and `docs/IMPLEMENTATION_STATUS.md`. Those records distinguish
the deployed release from isolated local restore/load rehearsals; they do not
claim that production rollback, off-host restore, or production-load testing was
performed.

### Optional Runtime Monitor

The admin runtime snapshot and host-side Docker/backup checker are documented
in [monitoring.md](monitoring.md). The API host-status path defaults to
unconfigured and the monitor systemd timer is a template only; neither has been
mounted, installed, or enabled by this source change.

On 2026-09-27, a later read-only HTTPS GET smoke confirmed Basic Auth at the edge: `/`, `/healthz`, and `/api/v1/listings` returned 401 without credentials and 200 with credentials. A sentinel private-photo path returned 401 without credentials and 404 with credentials, as expected for a nonexistent photo. This confirms the checked paths are behind the gate and the authenticated API listing responds; it does not verify the active Nginx configuration, delivery of a real private photo, or the full seller-to-buyer flow. No remote writes were made.

For a repeatable anonymous/authenticated edge check, use
`scripts/smoke-pilot-edge.sh --base-url https://suite-s1.denjik.by`. With no
credentials it expects HTTP 401 and `X-Robots-Tag: noindex`; credentials are
optional and are read only from `SMOKE_BASIC_AUTH_USER` and
`SMOKE_BASIC_AUTH_PASSWORD`. The script performs GET requests and does not
write to the application.

Before pointing an approved release at the active symlink, run
`scripts/release-preflight.sh` against the candidate and previous release. It
checks required release files, protected `.env` permissions, the active and
rollback symlink relationship, and the effective image list from
`docker compose config --images`. Pass `--expected-image-tag` and the protected
runtime env file; pass `--override-file` when the deployment override is stored
outside the release directory. Otherwise, a present
`docker-compose.override.yml` next to the compose file is included
automatically. The API and web images must use the same explicit release tag;
all effective images must have a safe, non-floating tag.

When checking a source archive, supply both `--source-archive` and `--sha256`.
The preflight compares the archive digest with that expected value and rejects
unsafe paths, duplicate members, links, non-file entries, secret/config paths,
and runtime/cache payloads. Source tests and `data/catalog.json` remain valid
archive contents. A matching digest checks integrity against the value supplied
to the command; it does not authenticate who created the archive or establish
that the supplied digest is trusted.

The preflight only reads Compose's resolved image list and archive metadata. It
never starts services, changes symlinks, or touches named volumes. See
`docs/ACCEPTANCE_MATRIX_2026-09-30.md` for the current acceptance gates and the
evidence that remains external.
