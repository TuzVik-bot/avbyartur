# Moderation layout deployment — 22 October 2026

Deployed `moderation-layout-20261022-r2` to `https://авторынок.бел`.
Fresh SSH inspection identified the actual base as `product-wave-articles-20261022-r1`; the locally documented r2 did not exist on that host. The candidate copied the active server release and added only the moderation card layout and administrator header CSS. The dirty local checkout was not deployed wholesale.

## Changes

- Moderation information occupies a full row above actions and the photo badge editor.
- Editor fieldset and grid cells can shrink within the card.
- Desktop administrator navigation wraps onto a separate header row, retaining all navigation links.

## Verification

- Production builds passed for both intermediate r1 and final r2.
- Isolated browser layout regression failed against original deployed CSS and passed against patched CSS at 1440, 1024, 768, 390 and 320 px, including open rejection controls.
- Local relevant component tests: 3 files, 20 tests passed.
- Final live browser used the canonical HTTPS domain with no injected CSS: login returned 200; registration showed name, email, password/repeat, both consents and submit button; administrator login succeeded.
- Real moderation queue contained one listing. At 1440 and 390 px, information and actions did not overlap, the editor stayed within the card, and page scrollWidth equaled viewport width.
- No listings were approved, rejected, blocked or otherwise modified. Registration was not submitted.

## Preservation and rollback

- Database backups: `/home/suite/backups/avtorinok/pre-moderation-layout-20261022T135937Z` and `/home/suite/backups/avtorinok/pre-moderation-layout-20261022T140247Z`. Each contains a custom dump, SHA-256 manifest and successful pg_restore TOC listing.
- Before/after container IDs and mounts for API, worker, database and mail matched. `.env` checksum matched and permissions remained 600.
- Final release: `/home/suite/apps/releases/moderation-layout-20261022-r2`.
- Immediate rollback: `/home/suite/apps/releases/moderation-layout-20261022-r1`; original release and image also retained. Roll back only web using the retained compose files and image; preserve API/worker/DB/volumes.
- Shared Nginx configuration was not changed; read-only inspection showed `auth_basic off`.
