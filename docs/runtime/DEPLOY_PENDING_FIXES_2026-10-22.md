# Web release and pending acceptance — 2026-10-22

## Release record

- Active release symlink: `/home/suite/apps/releases/product-wave-articles-20261022-r2`.
- Web container `a9ea6e4c4aa9…` ran `avtorinok-web:product-wave-articles-20261022-r2` and reported `healthy`.
- Before switching, a custom database dump was saved at `/home/suite/backups/avtorinok/pre-web-product-wave-articles-20261022-r2-20261022T102138Z/database.dump`. SHA-256: `1ba87c9ac947c5be53124f2bab09992985754dbdb698337a5574b3a5f8c799c4`; `pg_restore --list` read 542 entries.
- API, worker, database and mail container IDs remained unchanged. The `avtorinok_postgres` and `avtorinok_private_media` volumes and mounts remained unchanged. Host `.env` retained mode `600` and its prior hash.
- Compose overrides were added only inside the release candidate directory to pin the r2 web image and the exact r1 rollback image. Shared Compose and `.env` were not edited. The existing orphan warning for `avtorinok-web-candidate-20260929` was left in place.

## Deployed changes and live browser evidence

- Import feedback now reports truthful advertisement import statuses, and draft links use neutral wording.
- Search defaults to BYN only when a price bound is present and no currency was selected. Explicit currencies remain selected, and equipment normalization is retained.
- The browser opened the home page, exact BMW search, article index and an article detail. The BMW, price and year filters remained selected; the UI displayed `Цена, BYN` without a global error. The production catalog had no matching listings, so no inventory result was accepted.
- The article index showed three cards. The detail page showed article text, update date 22 October, a CTA and related articles.
- After hydration, `/login?next=%2Fsell` displayed “Создать аккаунт”, name/email/password/repeat fields, two consent controls and the registration button. The form was not submitted.

## Still pending / evidence limits

- Backend journey runtime acceptance was not run; the separate journey collect-only check remains blocked pending a dedicated disposable test database.
- Mobile viewport acceptance was not completed.
- Public HTTP response codes were not recorded. Python requests from the VPS returned `URLError` / `HTTP=000`; this is inconclusive. Browser-rendered page content does not establish a specific HTTP status.
- No claim is made that registration submission, backend user journey or mobile behavior passed acceptance.
- Local changes remain uncommitted and were not pushed.
