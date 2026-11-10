# Application rollback

Current release: `/home/suite/apps/releases/refero-20261108-r1` (web `avtorinok-web:refero-20261108-r1`, api/worker `avtorinok-api:editorial-ux-20261102-r1`, DB head `0033_listing_in_transit`).
Previous release: `/home/suite/apps/releases/headlights-header-20261102-r1` (web `avtorinok-web:headlights-header-20261102-r1`, also tagged `avtorinok-web:rollback-refero-20261108-r1`; api/worker unchanged).
Backup: `/home/suite/backups/avtorinok/refero-20261108-r1/` (`database.dump`, `rollback.json`, `before.json`, `deployed.json`).

Before rollback, confirm database migration compatibility and check that the previous images and the previous release directory with all its Compose overlays are still present. Application rollback does not undo migrations or imported data; restoring data requires a separate decision.

The exact command is stored in `rollback.json`. It runs from the previous release with its full overlay chain (every file listed in `docs/STATUS.md` except `docker-compose.refero.yml`):

```sh
docker compose -p avtorinok --project-directory /home/suite/apps/releases/headlights-header-20261102-r1 \
  -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.public-launch.yml \
  -f docker-compose.feedback.yml -f docker-compose.yandex.yml -f docker-compose.google.yml \
  -f docker-compose.seo-sorting.yml -f docker-compose.full.yml -f docker-compose.registry.yml \
  -f docker-compose.editorial.yml -f docker-compose.footer.yml -f docker-compose.card-borders.yml \
  -f docker-compose.button-spacing.yml -f docker-compose.content-pages.yml -f docker-compose.headlights.yml \
  up -d --no-deps --no-build --wait --wait-timeout 120 web
```

After health and the browser registration check on `/login?next=%2Fsell` pass, atomically repoint `/home/suite/apps/avtorinok` to the previous release (`ln -s <release> /home/suite/apps/avtorinok.rollback && mv -Tf /home/suite/apps/avtorinok.rollback /home/suite/apps/avtorinok`). Verify service health and actual container image IDs afterward. Do not delete volumes.

Older rollbacks: see the backup and rollback section of each journal in `docs/releases/2026/`. The previous version of this file (rollback to `listing-improvements-20261028-r1`) is obsolete.
