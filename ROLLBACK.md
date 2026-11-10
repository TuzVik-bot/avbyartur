# Application rollback

Previous release: /home/suite/apps/releases/listing-improvements-20261028-r1
Previous API: avtorinok-api:listing-improvements-20261028-r1
Previous worker: avtorinok-api:catalog-category-aware-20261025-indexed-r3
Previous web: avtorinok-web:listing-improvements-20261028-r1
Backup: /home/suite/backups/avtorinok/pre-deploy-live-20261028-VS2nhE

Before rollback, confirm database migration compatibility and check that these images and the previous release override are still present. Application rollback does not undo migrations or imported data; restoring data requires a separate decision.

From /home/suite/apps/releases/listing-improvements-20261028-r1, inspect `docker compose config --images` and confirm the distinct worker image above. Then atomically repoint /home/suite/apps/avtorinok to that previous release and run `docker compose up -d --no-build --wait` from the previous release. Verify service health and actual container image IDs afterward. Do not delete volumes.
