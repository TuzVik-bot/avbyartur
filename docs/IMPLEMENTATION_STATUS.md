# Implementation Status

Objective: deliver the complete closed marketplace pilot described in `docs/superpowers/plans/2026-09-26-avtorinok-pilot.md` and deploy the verified release to `suite-s1.denjik.by`.

## Local categories and services continuation — 5 October 2026

The isolated branch `codex/categories-information-vin-financing` now contains
local work for every requested catalog category, used/new filters, the managed
article section, an input-driven credit/leasing calculator, and an explicitly
unavailable VIN status. The article editor lists all pages and supports
selecting an existing article or starting a new one; editing a new slug does
not reset its fields or select a same-named existing article. Category changes
clear incompatible listing fields. Electric vehicles link to the supported electric-fuel
filter. Listing details now have a print layout. The currency converter uses
the official NBRB rate snapshot and performs conversion in the browser without
sending the entered amount back to the server.

GlobalVIN was assessed from its public Belarus API, pricing, privacy and terms
pages. The Belarus Quick Report is advertised at USD 8 with a typical 5–15
minute turnaround; the generic developer plan advertises a sandbox, but the
specific Belarus service key, test VINs, sandbox billing behavior, processor
locations, report retention and display rights remain unconfirmed. Per the
user's instruction, paid lookups require separate approval. The integration
remains disabled. Findings and vendor questions are in
`docs/research/globalvin-assessment-2026-10-05.md`.

Financing currently performs a local estimate only; it does not send form
values or create a lead. A synthetic test-only example and an unapproved
Belarus personal-data consent checklist are in
`docs/compliance/financing-demo-fixture-2026-10-05.md`. The operator identity,
manager, actual retention schedule and approved consent were not supplied, so
real application collection and partner transfer remain disabled.

Verification on this worktree: web tests **524 passed**; TypeScript typecheck,
production build with `next build --webpack`, OpenAPI type generation and
`make config-check` passed. The backend suite passed **639 tests** on a new
disposable PostgreSQL database inside the isolated Colima network. The runner
used the existing backend test image and the host venv's installed `urllib3`,
which was missing from that image; two third-party deprecation warnings remain.

The user explicitly requested push and deployment on 5 October. Commit
`0f0cd76b0c1c71207a46dc35dd739de04bfdca0a` is pushed to private origin on
`codex/categories-information-vin-financing`; a read-only remote check confirmed
that exact branch SHA and left `main` at `16802ace0d16b013a4398fbcf52b116bd65fd39a`.
Deployment remains blocked: public-key checks returned
`Permission denied (publickey,password)`, no SSH-agent identities are available,
and a later password-only interactive connection to port 23026 closed before
any preflight command ran. DNS resolves `suite-s1.denjik.by` to the supplied
server IP; HTTP/80 redirects to HTTPS and is not a deploy channel. No release,
VPS migration, article publication, or production data change has occurred.
Keep the current pilot access mode, account authentication and `noindex`
boundary.

After the push, a read-only HTTPS smoke returned 200 for `/` and `/cars`, 404
for `/trucks`, `/buses`, `/motorcycles`, `/special-equipment`,
`/agricultural-equipment`, `/trailers`, `/watercraft`, `/parts`, `/wheels`,
`/tires`, `/useful-information`, `/vin-check` and `/financing`, and 401 for
unauthenticated `/api/v1/me`. All checked paths retained `noindex`; this
confirms the new branch is not yet the active release.

## GitHub — 4 October 2026

Project source uploaded to private repository
`https://github.com/TuzVik-bot/avbyartur`, branch `main`; local `origin` is configured.
Runtime secrets/data, licensed catalog sources and local acceptance artifacts are
excluded. Statements below about a missing remote describe earlier dated checks.

## Verified deployment — 2 October 2026

The complete current source is deployed to the existing closed pilot as
`pilot-20261002T133421Z`, schema `0021_dealer_feed_policy`. All4serviceshealthy,
RestartCount0; env/data/catalog/namedvolumes/BasicAuth/noindex preserved.
Production still has100draft(without photos),2paused(with2photos),0active,
0companies/0tariffs. User/admin access and new admin tariffs/catalog-request
pages are verified on the real domain. Sourcebackend483PASS;web411PASS;
typecheck/ops113PASS; clean/0018upgrade/repeat-head migration gatePASS.
Exact final images local29statefulPASS,8/8largeconcurrentphotosready,52/52health
responses200. Live browser smoke and47new-pages/API/role/mobile checks passed;
live listing detail/guest-favorite flow could not run against empty inventory.

Latest load criterion remains OPEN: two full600s/20RPS runs each returned
12000HTTP200 but p95 exceeded500ms (954.69/1285.03ms, then670.15/978.96ms).
Neither is represented as a pass. Deployment is for the existing closed pilot;
full MVP/public launch acceptance is not claimed. Providers/legal/real inventory/
real-deviceHEIC/offsite inputs remain missing. GitHub auth works; no project
remote URL was found/provided, so Git push is pending.

See `DEPLOYMENT.md`, `SERVER.md`, `docs/PROJECT_STATUS_2026-10-02.md` and
`.superpowers/sdd/2026-10-01-project-completion/release-133421-deployment-receipt.json`.

## Historical candidate — 2 October 2026 before final deployment

Current built candidate `pilot-20261002T122033Z` includes the remaining dealer
feed policies/samples, tariff management, catalog intake, guest-contact guards,
role-aware hours/photos, sanitized field/photo history, risk cues, configurable
photo/year policy and dependency security updates, Russian i18n foundation,
locale-aware URL/metadata helpers and release package/image safeguards.
Full source backend **482 PASS**, web **411 PASS**, typecheck/codegen PASS,
focused release preflight **14 PASS**. All 42
production Python package pins and the web dependency audit report zero known
vulnerabilities at that package-audit check. The new native AMD64 API image uses
Python **3.12.15** / Expat **2.8.5**; imports, new API routes and synthetic HEIF
processing passed without network/database. Isolated web HTTP checks confirmed
Russian aliases, noindex, metadata and primary asset rendering. These offline
checks do not replace database/browser/stateful acceptance of the new image.

A full quiet repeat on the previous exact Oct 1 acceptance image completed
**12,000 HTTP 200 / 600 seconds / 20 RPS**, search p95 **275.31 ms**, detail
p95 **294.20 ms**; both passed the <=500 ms gate. The original failed result is
preserved. This repeat covers the old image's search/detail baseline only;
latest-image and photo-upload load gates remain open.

This source is not deployed. Local Alembic validation through `0021` was twice
rejected by automatic approval review despite an isolated empty-test-DB probe;
separate explicit permission is pending. Do not bypass that gate. Updated-image
stateful/browser/load acceptance, offsite restore, real provider/operator/data
and real-phone HEIC gates remain open. Source candidate and result logs are in
`.superpowers/sdd/2026-10-01-project-completion/`.

## Verified release — 1 October 2026

The active closed pilot is `pilot-20261001T160530Z` on
`https://suite-s1.denjik.by`; Alembic is `0018_profile_identity`.
Fresh SSH authentication succeeded. API, worker, web and PostgreSQL are healthy;
application images are the new immutable linux/amd64 release. Runtime `.env`,
named PostgreSQL/media volumes and all existing account/listing/photo counts
were preserved. The previous `pilot-20260930T052948Z` source and images remain
available for application rollback.

Fresh pre-release checks: backend **396 passed**, web **312 passed**, typecheck
and Compose/catalog config PASS. Clean and schema-only 0011 upgrades to 0018,
including an idempotent second upgrade, passed in isolated disposable databases.
The VPS production image build passed with Turbopack. Live browser smoke passed
**29/29**, plus **41** new API/page/catalog/access checks at desktop/mobile widths.
The HTTPS Basic Auth/noindex boundary passed with and without credentials.

Admin users/audit/catalog/settings/content/monitoring and the new account/profile,
dealer/import, listing/search and billing code are deployed. Real SMS/email,
checkout, offsite backup and host-monitor installation remain unconfigured.
There are still zero active listings and zero companies; no synthetic production
data was introduced. Stateful buyer/company/payment acceptance, load/HEIC and
offsite restore remain outstanding. Full MVP completion is not claimed.

See [DEPLOYMENT.md](../DEPLOYMENT.md) for backup paths and deployment evidence.
Git push is awaiting a repository URL: this workspace has no Git metadata/remote.

## Historical status before the 1 October release

The older workstreams and dated entries below are historical. Their release,
SSH and migration statements do not override the verified release above.

The project still has no Git metadata. Release `pilot-20260930T004119Z` is
active on the closed pilot at `suite-s1.denjik.by`; `pilot-20260930T000430Z`
remains the rollback candidate. The release carries all nine owner-authorized
Drom catalog batches, the saved-search and in-app notification slices,
company/dealer hardening, and archived-listing `410` behavior. The deployment
command reported all four Compose services healthy. Fresh HTTPS edge checks
passed, and the browser smoke passed `29/29` for public routes, seller/admin
sessions, notifications, moderation queues, and mobile widths. There are no
active public listings, so the live detail/favorite path was not exercised.

The database was already at Alembic `0009_notification_outbox`; no migration
was needed. The pre-deploy format-5 backup for this release has 31 verified
checksums and a readable PostgreSQL dump. A post-deploy backup is still
outstanding: fresh BatchMode SSH now returns `Permission denied
(publickey,password)`, so current restart counts, `.env` mode, and volume IDs
could not be reread. The pilot remains behind Basic Auth and `noindex`; email
delivery remains unsupported without a configured provider.

The pre-release local Docker audit found Colima/ARM64 with 8.4 GiB available, below the release build gate; no local images, volumes or cache were pruned. The latest API/web images were built and verified as AMD64 using the prepared builder. The earlier VPS capacity measurements are historical; current host capacity was not refreshed after SSH authentication failed. The isolated acceptance Compose project `avtorinok-acceptance-20260927` remains available at `127.0.0.1:18080` with separate image tags and named database/media volumes.

## Workstreams

| Workstream | Status | Evidence |
|---|---|---|
| Shared API contract | Typed success/error contract generated and verified | FastAPI OpenAPI generation is deterministic across 51 paths (including live/ready health paths); all JSON success bodies are typed, `/api/v1` default and validation errors use the runtime error envelope, idempotency headers are required, and photo bytes are documented as binary WebP |
| FastAPI, PostgreSQL schema, auth, listings, moderation, saved searches and web notifications | Core is deployed; latest company validation is local pending release | Current checkout backend suite: 234 tests passed on a newly created disposable PostgreSQL 17.11 `_test`. The deployed database is at Alembic `0009_notification_outbox`. Company/report/photo/saved-search/notification mutations use revision checks; in-app web outbox delivery is idempotent, while email is retained as `unsupported` without a provider. |
| Next.js public and account pages | Core is deployed; latest mobile-navigation fix is local pending release | Current web suite: 208 tests across 43 files; TypeScript and optimized production build passed. Company/dealer pages have retry, status, privacy and pagination states; saved searches, notifications and the branded archived `410` page are covered. |
| Licensed Drom batches | All nine permissioned batches imported into the VPS catalog | All nine filesets contain 194,817 rows and unique canonical source URLs; the deployed database has 194,817 modifications and repeat dry-runs report no new rows |
| Compose, closed-pilot helpers, catalog and runbooks | Implemented; v1–v5 backup compatibility and current Compose restore rehearsal passed | Backup/restore/offsite/retention/daily-backup tests: 58 passed; version 5 includes all 26 Drom artifacts from batches 1–9 while restore/offsite keep v1–v4 support; the current isolated Compose rehearsal restored a synthetic listing and WebP photo with matching SHA-256 |
| Integrated local run and end-to-end acceptance | Current-source browser and API checks passed on isolated data | Existing private/company seller and moderation flows remain covered by the PostgreSQL suite. Current-source preview uses the 41-make Drom catalog; Playwright verified generation-specific body-variant filtering, named chip, reset behavior, and responsive search at 320 and 1440 px. A matching worker remains on the isolated preview database. No production data was written |
| VPS release | Deployed; runtime follow-up and latest local changes await SSH | `pilot-20260930T004119Z` is the last confirmed active release and the deployment command reported four healthy services. Fresh anonymous edge smoke passes. The latest company-validation and mobile-navigation changes are not in that release; SSH-agent has no loaded identities, so `.env`, restart counts, volume IDs and a post-deploy backup cannot be rechecked or created. |

## Acceptance Gates

- [~] Deployment output reports PostgreSQL, API, worker, and web healthy, and external edge/browser smoke passes. The pre-deploy format-5 backup for `pilot-20260930T004119Z` is verified; its post-deploy backup and fresh `.env`/volume/restart-count audit remain blocked by current SSH authentication failure. Prior-release post-deploy backups remain documented below.
- [x] Closed pilot access is verified over HTTPS: Basic Auth protects pages, API, robots and photo paths; noindex headers are present. Seller/admin app sessions work through the browser proxy with Secure/HttpOnly cookies; logout returns `/me` to 401; public registration returns 404.
- [~] Private seller live flow passed on the previous VPS release: catalog selection, draft, JPEG upload and worker readiness, moderation, exact Drom filter/search, public WebP delivery without EXIF, public contact omission, favorite add/read/remove, and pause. The new release's browser smoke is read-only; no active listing exists for repeating detail/favorite checks.
- [~] Company creation, admin approval, company-owned listing and dealer publication pass the current checkout's PostgreSQL integration test, including blocking/privacy checks. The deployed browser loaded `/account/company` and `/dealers`, but the full stateful company flow has not been repeated on the VPS; the latest text-normalization fix is pending release.
- [x] Saved searches have owner-scoped CRUD, pause/resume, revision and idempotency checks, a 20-search account quota, relative `/cars` URL validation, and a responsive `/account/saved-searches` page. The deployed `0009_notification_outbox` matching path enqueues an outbox and idempotently delivers in-app web notifications through authenticated list/read endpoints; `/account/notifications` returned 200. Email selections remain explicitly `unsupported` with `email_provider_unconfigured`; no email provider is configured.
- [x] A previously published archived listing now returns API `410 Gone` for every archive reason with an active status-history event; never-published archived records remain `404`. The Next.js detail route renders a branded gone state for API `410` and archived success payloads.
- [x] PostgreSQL tests cover moderator decisions, revision conflicts, ownership, and concurrent quota races.
- [x] Moderators can block active listings with a reason and revision check; only admins can approve companies; operator user blocking records an audit event and revokes sessions.
- [x] PostgreSQL tests cover favorites, reports, contact reveal, pause, resume, and sold states; public search and city-filter SSR returned expected results.
- [x] Photo validation, orientation, EXIF removal, derivatives, ownership, private-draft access, worker retries, and publication gating passed backend tests; an end-to-end HEIF test covers authenticated upload through worker, moderation and public WebP delivery. Photo serving grants moderator/admin reviewers access only while a listing is `pending_review`; lifecycle regressions preserve owner access while denying paused, rejected, blocked, archived and old sold listings.
- [~] Catalog provenance/import and preservation are tested; the seed has 8 body types, 24 sourced BMW body variants, and aliases for BMW/3 Series. Drom labels with one explicit `YYYY - н.в.` or `MM.YYYY - н.в.` range now preserve `year_from` and keep `year_to` null. BMW Gen7 and Passat B9 still have unknown end years; five other control models still lack verified generation boundaries. `generation_depth_verified` remains false.
- [x] Owner-authorized Drom batches 1–3 are imported into the isolated source preview and the closed-pilot VPS database; this is the historical format-4 subset. Combined counts for that subset are 165,133 modifications, 11,164 Drom generations, and 10,684 Drom body variants; 4 ambiguous crosswalk pairs remain separate. The complete production import is recorded below for batches 1–9.
- [x] Owner-authorized batches 4–9 passed ZIP CRC and CSV/JSON/report reconciliation (29,684 rows), then were dry-run and imported on the VPS after a format-5 backup. The production catalog now contains 194,817 Drom modifications; these are catalog records, not sale listings, and no synthetic sale listings were added.
- [x] Current-source browser flow created a private Drom listing (`source_id=23965`), processed a synthetic photo, submitted it, and received moderator approval; the public detail retained Drom specifications, hid the synthetic phone before explicit reveal, and showed it after the button action.
- [x] Search supports exact `modification_id` and generation-specific `body_variant_id` filtering alongside existing constraints. Backend and web tests cover conjunctive filters, URL state, SSR chip labels, invalid IDs, and dependent-filter reset.
- [x] Sellers can select, edit, and review a generation-specific body variant. The variant is restored in the workspace, saved with drafts, reset when generation changes, and rejected if it belongs to another generation.
- [x] A synthetic company profile passed separate admin approval, then a company-owned Drom listing passed photo processing, premoderation, and public dealer-page publication. The seller can pause and resume it; public dealer output omits company UNP and phone.
- [x] A saved favorite appeared in the favorites cabinet; a synthetic report was submitted and resolved; account status actions returned the company listing from paused to active.
- [x] Account listing and edit pages handle incomplete drafts with null make/model/price/region values without SSR failure. Regression tests cover the list fallback and reopening the vehicle step.
- [x] Third Drom batch was reconciled and imported: 1,427 source rows, 85 models, 255 generations; CSV and JSON match on all 19 fields and source IDs, with no cross-batch source-ID collisions. The report lists `Aro` but the CSV has no `Aro` rows, so no empty make was created.
- [~] The deployed pilot pages return `noindex, nofollow, noarchive`, public registration returns 404, and current edge/browser checks pass. Basic Auth and app login are verified on the new release; the full seller-to-moderator-to-public-photo flow was last verified on the previous release.
- [~] Earlier pre-import, post-import and post-deploy format-5 backups include all 31 expected checksum entries; current `pilot-20260930T004119Z` pre-deploy backup is verified. Its post-deploy backup is not yet recorded. Off-host transfer/restore and measured RPO/RTO remain outstanding.
- [x] Local backup tooling emits format 5 only when batches 1–9 are complete; it checksums all 26 Drom artifacts and retains format 1–4 restore/offsite support. The v5 backup was created and verified on the VPS.
- [x] Current-source API load acceptance completed for 10,000 synthetic listings, 20 VUs, 20 RPS, and 600 seconds: 12,000/12,000 HTTP 200 responses, no errors or skipped slots, search p95 34.99 ms and detail p95 14.31 ms. This is a local source-mounted sidecar result, not a release-image or VPS result.
- [~] Closed release `pilot-20260930T004119Z` remains the last confirmed VPS version; its Compose start reported four healthy services, browser smoke passed `29/29`, and a fresh anonymous HTTPS edge smoke still confirms Basic Auth/noindex. Latest local source changes have not been deployed. SSH-agent has no loaded identities, blocking fresh host audit, post-deploy backup, and deployment of those changes. The pilot remains behind Basic Auth and noindex; public launch is not claimed.

## Decisions

- Keep the existing host Nginx and external HTTPS proxy; route the app through loopback only.
- Keep the API's proxy trust disabled until the live chain is inspected. Phone reveal is limited to 30 attempts per account per hour, as approved by the owner; this avoids combining unrelated browsers behind the web-container IP. Do not add a forwarded-IP limit until proxy-hop and spoofing tests pass.
- The checked-in catalog seed is CC0 and must be readable by the non-root API container (UID 10001); `data/catalog.json` is mode 644. Licensed Drom source files remain mode 600.
- A pre-release workstation audit found Colima/Buildx below the release build gates (less than 15 GiB engine space and no advertised `linux/amd64`). This did not block release `pilot-20260928T052525Z`, which was built natively on the VPS; do not prune shared local Docker state to change the workstation builder.
- Seed only verified catalog data. The strict Wikidata relation policy uses direct `P1716`; six manufacturer-backed manual model rows fill specific gaps without changing Wikidata attribution. Catalog coverage now includes BMW 3 Series Gen7 from 2018, Passat B8 for 2014-2023, and Passat B9 from 2024; `generation_depth_verified` remains false because BMW Gen7 and Passat B9 end years are unknown.
- Generate pilot secrets outside the repository and make local handoff explicit.
- Do not prune shared Docker images, volumes, or build caches without authorization.

## Detailed verification notes

The first two suite counts below are an earlier source snapshot and are superseded
by the 30 September release verification at the end of this document.

- Historical backend source snapshot: 167 tests passed against a disposable PostgreSQL 17.11 `_test` database; no tests were skipped. The source-preview database migrated from `0004_geography_provenance` through `0006_unbounded_generation_labels`. Clock-skew regressions verify immediate claims and retry backoff against PostgreSQL time, and seller photo workflows assert they process their own queued jobs. One existing Starlette/AnyIO `BlockingPortal` deprecation warning remains.
- Historical web source snapshot: 119 tests passed across 29 files; typecheck passed. A webpack production build passed in an isolated copy so active development output was preserved. Playwright verified the 41-make Drom preview, AITO M5 generation/modification filtering, named body-variant chip, dependent-filter reset, phone-to-login behavior, no horizontal overflow at 320 and 1440 px, and anonymous seller redirect.
- Earlier current-source route smoke at `127.0.0.1:3003`: `/` and `/cars?generation_id=...&body_variant_id=...` returned 200; the active filter chip showed the catalog name, and API search combined both IDs conjunctively. That preview used API `127.0.0.1:8003` and the isolated `_test` database; it is not required for the deployed VPS release.
- HEIF media acceptance: a generated HEIF with EXIF orientation 6 and timestamp completes authenticated upload, worker conversion, submission, moderation and public photo delivery. The returned asset is WebP at the correctly transposed `40x80` size with no EXIF. The test found and fixed Pillow-heif's normalized EXIF orientation: the worker now falls back to `original_orientation` only when the EXIF tag is already 1. This verifies a synthetic fixture, not real phone samples.
- Drom import: batch 1 CSV SHA-256 `efb72b1c33acd4e8c5fe3787e3294f1a60c498370c1aea022eb2ad2dcaa32c4f`; batch 2 CSV `f317efb41424719fdf545b34a2db04fd5d667d005deaf998aa5d53645559b37b`, JSON `33e379172874a1835979502015971e42feddb937206d6efb41e88a744cdef3c3`, report `48f7402a67bef412e5383af2165f57f967007d06b24987e62e1eab52de64d61a`; batch 3 CSV `264ea9a14471a8768c7d61e4a494a825993e8579e63420aed55c2dfe29a3583e`, JSON `78683881cae57b4befde62fa7a0e3644b186316f708d2b306412332d8670b757`, report `cff20a31826e8a75d09daaa5f96682c7ac4bb699a7c4aa8542d3d32fe930e98d`. Batch 2 and 3 CSV/JSON pairs match on all 19 fields and IDs; there are no cross-batch source-ID collisions. The batch 2 report lists `AC` and batch 3 lists `Aro`, but neither CSV has rows for that make, so no empty make was created. Combined crosswalk: 53 unique / 4 ambiguous / 1,473 unmatched, yielding 1,477 new Drom models. Combined data: 165,133 modifications, 11,164 generations, 10,684 body variants. A non-empty summary row round-tripped all 19 CSV columns. Across the three batches, `production_period` is missing in 77 rows, 20 periods end before they start, 1,304 generations have an explicit open start with unknown end year, 4,115 trim names are missing, and 153,105 rows have empty `summary`. The longest generation label is 414 characters; migration `0006_unbounded_generation_labels` stores generation names and listing snapshots as `TEXT` without truncation.
- Drom open-generation years: parser tests cover month/year open ranges, bare-year open ranges, invalid months, and reversed ranges. Reapplying batches 1–3 to the isolated `avtorinok_preview_20260927_00aa22_test` database updated 816, 446, and 42 generation rows respectively; no modification rows changed. The current-source API now returns AITO M5's `year_from=2024` and `year_to=null` for its open generation.
- Web runtime image: starts with UID 1000 (`node`); `/app/.next/cache` is writable by that user. The active release uses the pinned Debian `node:22.23.3-bookworm-slim` image; the Alpine/musl exit-139 loop belongs to the superseded image.
- Runtime helpers: backup/restore/offsite/retention/daily-backup suites passed 58 tests; shell syntax and targeted Ruff checks passed. Backup format v5 preserves all 26 licensed files from batches 1–9 while v1–v4 restore/offsite compatibility remains supported. A current-script full Compose rehearsal in the isolated project `avtorinok_rehearsal2_20260929_225157_96639` completed successfully: backup 22 s, restore 43 s, all four services healthy, and the restored photo matched SHA-256 `81b722fd16b6b0d8ced07dc0eae47d540d5d823a3fde3bd51b244d67d1471b3a`. Temporary resources were removed; no real off-host target was configured, no off-host restore was performed, and production RPO remains unmeasured.
- Historical pre-deployment HTTPS check: without Basic Auth, `/` and `/healthz` returned 401; the later release verification below independently confirmed the live host over `fortebit-prod`. No remote write was made by that documentation pass.
- Lint: targeted Ruff checks pass for `backend/app/api/listings.py`, `backend/tests/test_auth_security.py`, `backend/app/api/media.py`, and `backend/tests/test_media_access.py`. The full repository Ruff check has not been run.
- Worker recovery: regressions cover commit-ack ambiguity, transient retry without duplicate jobs/variants, and missing/failed photos not succeeding. Ready variants are validated on retry; published targets survive transient DB commit errors. Full backend suite passed with these changes.
- Moderation/lifecycle contract: tests cover pending/active blocking, required reasons/revisions/audit events, admin-only company approval, user blocking/session revocation, favorites, reports, contact reveal, ownership, pause/resume/sold, and concurrent quota races. The complete media-access test file passed 39 tests; moderator/admin photo access is limited to `pending_review`, including regressions for paused, rejected, blocked, archived, and sold more than 30 days ago, with owner access preserved.
- Catalog JSON/import: the checked-in catalog has 25 makes, 253 models, 16 sourced manual generation rows, 8 Wikidata body types, and 24 BMW body variants. BMW aliases include `БМВ`, `3 серия`, and `3er`. Refresh tests passed 13/13 and pure catalog tests passed 6/6. Five named control models have launch/update evidence but no source-confirmed generation boundaries; no generations were invented. `generation_depth_verified` remains false.
- Control-model source audit (2026-09-28): primary manufacturer pages still do not establish dated generation intervals for BELGEE X50/X70, Geely Coolray, BYD ATTO 3/Yuan PLUS, or ZEEKR 001. BYD labels China-market Yuan PLUS generations 2 and 3 but gives no production interval; the 2026-04-24 page is a reveal. Coolray's 2023 "New Coolray" is not labeled a generation change. ZEEKR's 2024 "all-new" is not numbered. Drom request now names these models explicitly and asks for market-specific IDs and production bounds.
- Phone reveal: the owner approved a per-account limit of 30 attempts per hour. Integration tests verified that users sharing a container IP do not share a quota and that one account remains limited across IPs. The full backend suite passed on an isolated disposable PostgreSQL database; the database was removed and verified absent.
- Login throttling: ten failed attempts per 15 minutes are counted by peer IP and normalized login. Successful active logins do not consume the bucket and remain possible after it fills, preventing lockout through a shared web-container IP. Invalid attempts beyond the limit still require one Argon2 verification before returning 429; no additional IP-only cap is active because the proxy chain is not verified.
- Isolated Compose acceptance project `avtorinok-acceptance-20260927` remains running at `127.0.0.1:18080`; only web is published there. Five synthetic roles completed private/company seller, upload/worker, moderation, search/detail/favorites/phone, and reports flows. Public registration returned 404, photo delivery returned WebP, and public phone data stayed hidden.
- Earlier isolated acceptance API JSON and SSR include photo URLs; public listing JSON omits phone; the image endpoint returned `200 image/webp`. Listing cards prefer `photo_urls` and fall back to `cover_url` for compatibility. The historical current-source preview was `127.0.0.1:3003` -> source API `127.0.0.1:8003`; its worker and the older `3002 -> 8002` preview are not part of the current VPS release. The isolated acceptance site at `127.0.0.1:18080` remains the available local demo surface.
- `docker compose config --quiet` and `make config-check` passed. A pre-release workstation audit found the local builder limited to ARM64/386 with 8.4 GiB engine space, below the 15 GiB gate. The current release images were instead built and architecture-checked as `linux/amd64` on the VPS. No local Docker cache, image, or shared volume was pruned.
- Historical 600-second ARM64 baseline used 10,000 synthetic listings and the unchanged API image `a4b8b7d1aae44f265533a187f83eb863a8f2ba445a2ac2f9cfc217f138ca14a`, so recent source changes were not measured. At an offered 20 RPS with a cap of 20 in-flight requests, 10,024/10,024 completed requests returned HTTP 200 with no server or transport errors; completed throughput was 16.71 RPS and 1,976 scheduled slots were skipped. Search latency p50/p95/p99 was 1,764/2,364/2,657 ms; detail latency was 272/620/821 ms. The search p95 <=500 ms gate failed on that stale image.
- Current-source 600-second sidecar run used the same 10,000-listing dataset and planned 20 VUs / 20 RPS. All 12,000 requests completed at 20 RPS with HTTP 200, no server/transport errors, and no skipped slots. Search p50/p95/p99 was 27.77/34.99/79.02 ms; detail was 8.84/14.31/40.77 ms. Host guard collected 60 CPU/memory samples (minimum CPU idle 24.46%, free memory 38%); sidecar API, database, and worker stayed within their configured resource limits. The source was mounted read-only; the release image was not rebuilt. The sidecar was removed, and the prior baseline API and 10,000-row database were verified unchanged.
- Earlier VPS access checks covered the prior release and confirmed the HTTPS Basic Auth boundary; the deployment-time smoke evidence is in `DEPLOYMENT.md`. The pre-deployment local runner record below predates the successful `fortebit-prod` SSH preflight and must not be used as current host evidence.
- Post-release UI work in the active release source includes `/dealers` pagination, seller review previews, manual-town search, and the blue cornflower icon set. The light theme and cornflower assets are deployed. A mobile navigation fix was added after that release; the current checkout now passes 208 web tests across 43 files, typecheck, and production build.
- Local demo seed: 100 active synthetic listings now populate preview database `avtorinok_preview_20260927_00aa22_test`, across 25 makes and 9 body types; 50 belong to a clearly named demo dealer and 50 to 10 test sellers. These are browse/search fixtures inserted directly for UI inspection; they do not represent 100 seller upload or moderation runs. Titles/descriptions carry marker `DEMOSEED-20260928-AUTO100`; photos use the labeled synthetic fallback and phone fields remain absent from public summaries. Cleanup manifest: `/Users/home/.config/avtorinok/demo-seed-local-20260928.json`. Do not point the schema-dropping backend test fixture at this preview database.
- Remaining work: configure an off-host backup target and complete an off-host restore; measure RPO/RTO; test samples from real phones; measure the release image under load; and repeat the full company-creation-to-dealer-publication flow on the VPS. Canonical metadata, sitemap, and structured data remain prerequisites for a crawlable public release; the current pilot stays noindex. Additional forwarded-IP contact limiting remains deferred until the proxy chain and spoofing behavior are verified. The catalog generation-depth threshold remains unmet because source-confirmed boundaries are unavailable for BMW Gen7, Passat B9, and five other named controls.

Next: configure encrypted off-host backup delivery and test a restore in a separate target, then measure RPO/RTO. After that, repeat the remaining HEIC and company-flow checks and review public-launch requirements. Keep the pilot behind Basic Auth and noindex until a public launch is explicitly approved.

## Local continuation — 29 September 2026

- Archived listings now return API `410` when status history proves they were previously active, regardless of the archive reason. Never-published archived listings remain `404`. The Next.js detail route renders a branded gone state for API `410` and archived success payloads; direct HTML/HEAD proxy probes preserve the `410` response while RSC navigation uses the route's not-found/gone handling.
- Trusted `SITE_ORIGIN` and `SITE_NAME` feed metadata. Search canonicals use normalized supported filters and preserve pagination. Page-level noindex remains enabled; robots permits crawlers to read those directives while disallowing `/api/v1/`; the closed-pilot sitemap is empty.
- A pinned generator now exports the FastAPI OpenAPI schema and generates TypeScript for 51 paths (including live/ready health paths). All JSON success bodies are typed, `422` uses the runtime API error envelope, `Idempotency-Key` is required for draft, submit, and photo-upload operations, and the photo endpoint is binary `image/webp`. Other route-specific HTTP error statuses are not yet fully enumerated in each OpenAPI operation.
- Seller and company account pages show moderator rejection reasons from private API responses. Frontend photo/source types also allow nullable values emitted by the backend.
- Historical pre-notification-release checks (29 September): 186 web tests across 40 files, 227 backend tests on a temporary `_test` PostgreSQL container, `pnpm typecheck`, `pnpm build`, `docker compose config --quiet`, and deterministic generated API types. The current source follow-up added 3 backend notification tests (230 total); no JSON response body remains `unknown` in the generated TS contract. Focused archive/gone-route and saved-search suites passed; the reusable UI runner remains available for the isolated preview. At that point the deployed release was rebuilt as AMD64 and migrated to `0008_saved_searches` with pre/post backups; current release verification is recorded below.
- Reusable read-only Playwright runner `scripts/smoke-pilot-ui.py` exercises public routes, search, detail, guest favorite redirect, mobile widths, and optional Basic Auth/seller/admin routes using credentials only from the environment. The pre-deployment local run reported 18 passed / 0 failed, no JS or network errors, and skipped seller/admin branches because the local preview DB has no pilot accounts. The current VPS release and edge boundary are verified in the final preflight below. The acceptance site at `127.0.0.1:18080` remains available for local demo inspection. The historical production-build preview at `127.0.0.1:3004` used current-source API `127.0.0.1:8004` and local demo DB `avtorinok_preview_20260927_00aa22_test` (103 synthetic listings); it is not running now.
- Remaining launch work is limited to off-host backup/restore and measured RPO/RTO, the fresh stateful company flow on VPS, real-device HEIC samples, release-image load measurements, and legal/public-indexing preparation. The pilot remains behind Basic Auth and noindex.

## Drom archive increment — 29 September 2026

- The six supplied ZIP files (batches 4–9) passed CRC verification and contained exactly one CSV, one normalized JSON file, and one report each. CSV, JSON, and report counts match across all 19 fields. Their combined 29,684 rows bring batches 1–9 to 194,817 records; all source URLs are unique, while 90 groups reuse a `source_id` across batches.
- Original archives remain in Downloads; extracted licensed CSV/JSON/report artifacts are stored in `data/licensed/` with mode `600`. Archive names and SHA-256 values are recorded in `docs/runtime/drom-batches-04-09.md`.
- The importer now keys a modification by canonical Drom source URL. When a matching legacy `drom:<source_id>` row is found, its UUID is preserved and the key is migrated only if its stored URL matches. The 13 Drom importer tests passed against a separate disposable PostgreSQL instance. A second isolated run dry-ran, imported, and repeated all nine actual CSVs: 86 makes, 2,457 models, 13,993 generations, 13,249 body variants, 194,817 modifications, and 9 import records remained stable after re-import. These counts describe a fresh test catalog, not the production crosswalk.
- New archive SHA-256 values: batch 4 `38cdaa1b089763b41f229a2a0937199baf8a35826bfb5c95f74dfa4e05499b46`; batch 5 `fe35a20de2a7f0e7675f8e5de18a8b774d82082fdd9e11f2591eeb62f12701c0`; batch 6 `608024d4bcbca6059e838c81fb965066ea8db8ab0f33fab3cb5399ec51345bad`; batch 7 `cc15c487daf73a7e09ff8ff64ebf524fd11e11f717f2972b162f700790008500`; batch 8 `cbf2c21daa8cac86e3e0a8575023575697de22dcb419f733bea2e0ccdac6f3bc`; batch 9 `545afddd52148a76bd361d2d70e76f394350d6ef30ea7afe69b6eb13dd059617`.
- Deployment was pending during the initial 29 September preflight; it was completed later in the same run as release `pilot-20260929T222500Z`. Demo listings remain local; Drom source files populate the vehicle catalog, not sale listings.

## VPS release completion — 29 September 2026

- Fresh BatchMode SSH access succeeded through `fortebit-prod`. The target is `x86_64`/Docker `linux/amd64` with about 77 GiB free. The active symlink now points to `/home/suite/apps/releases/pilot-20260929T222500Z`; the former `pilot-20260929T125300Z` release remains available for rollback.
- The web runtime was rebuilt on pinned `node:22.23.3-bookworm-slim` after the prior Alpine/musl image repeatedly exited with code 139. The new API and web images were built and verified as `linux/amd64`; the deployed web container has restart count 0 and is healthy.
- A format-5 pre-import backup was created at `/home/suite/backups/avtorinok/pre-release-20260929T220213Z/avtorinok-20260929T220213Z`; post-import and post-deploy snapshots were also created. Every snapshot contains all 26 licensed Drom artifacts, 31 SHA-256 entries pass, and `pg_restore -l` reads 186 database entries.
- Drom batches 1–9 were dry-run in order, imported, and dry-run again. The production catalog reports 94 makes, 2,630 models, 14,009 generations, 13,273 body variants and 194,817 modifications across the existing Wikidata seed and Drom data. Existing listing rows were preserved; no synthetic sale listings were added.
- Alembic reached `0007_company_report_revisions`. The deployed internal readiness endpoint returned 200, the internal public-listings endpoint returned 200, and unknown API routes returned the standard JSON error envelope with `X-Request-ID`. Anonymous HTTPS requests to `/`, `/healthz` and `/api/v1/listings` returned the expected 401 with `X-Robots-Tag: noindex, nofollow, noarchive`.
- Verification completed locally after the final code changes: backend `224 passed` on a disposable PostgreSQL `_test` database, web `175 passed` across 38 files, web typecheck, Compose config validation and shell syntax checks. One existing Starlette/AnyIO deprecation warning remains.
- Remaining launch gates are deliberate: off-host encrypted backup/restore and measured RPO/RTO, real-device HEIC samples, a fresh stateful company-to-dealer flow through the VPS UI, public-load measurements for the release image, and legal/public-indexing preparation. The closed pilot stays protected and noindexed.

## Предварительная read-only проверка — 30 сентября 2026 (до релиза 0009)

- `ssh -o BatchMode=yes fortebit-prod` прошёл. Хост `x86_64`, Docker `linux/amd64`, 4 vCPU; на `/` и Docker filesystem свободно около 72 GiB.
- `/home/suite/apps/avtorinok` указывает на `pilot-20260929T222500Z`. API, worker, web и PostgreSQL healthy, у всех `RestartCount=0`; web опубликован только на `127.0.0.1:8080`. `.env` имеет mode `600`, тома `avtorinok_postgres` и `avtorinok_private_media` сохранены.
- Alembic: `0007_company_report_revisions (head)`. Внутренние `/health/live`, `/health/ready` и `/api/v1/listings` возвращают `200`; каталог содержит 94 марки, 2,630 моделей, 14,009 поколений, 13,273 кузовных вариантов и 194,817 модификаций. В выдаче нет активных объявлений (`total=0`), что соответствует закрытому пилоту без публичных synthetic listings.
- Pre-release, post-import и post-deploy format-5 snapshots имеют по 31 проверяемой SHA-256 записи; `pg_restore -l` для каждого прочитал 186 записей.
- Внешние `/`, `/healthz`, `/robots.txt` и `/api/v1/listings` без Basic Auth возвращают `401` с `X-Robots-Tag: noindex, nofollow, noarchive`. В этой проверке удалённых изменений, миграций, импортов, рестартов и Nginx reload не выполнялось.

## VPS release completion — 30 September 2026, `pilot-20260930T000430Z`

- Fresh `ssh -o BatchMode=yes fortebit-prod` authentication succeeded. The target
  is `x86_64`/Docker `linux/amd64`; release `pilot-20260930T000430Z` is active.
  API and web images have IDs
  `sha256:dde43eb8e5c2bbba97be4dd18d06e7ade97954df1f50318b26c2602f243ad044`
  and `sha256:fc554173eee2f4c050b94366e23b4b958bbb695c368faedefcd1befd13e5eee7`.
- Migration `0009_notification_outbox` applied from `0008_saved_searches` and
  is `head`; the production notification outbox and `/account/notifications`
  page were queried successfully. Email delivery remains unsupported without a
  provider.
  The catalog remains 94 makes, 2,630 models, 14,009 generations, 13,273 body
  variants and 194,817 modifications. Listings are `100 draft` and `2 paused`,
  with zero active public listings.
- Pre-deploy and post-deploy backups are
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20260930T000430Z/avtorinok-20260930T000514Z`
  and
  `/home/suite/backups/avtorinok/post-deploy-pilot-20260930T000430Z/avtorinok-20260930T000830Z`.
  Both have 31 passing SHA-256 entries and readable PostgreSQL dumps. The source
  archive is stored on the host with SHA-256
  `0da32c47be2476a4187dbc076b48fbd943d8c3e9704b54e60dc4c39eb1396cdb`.
- All four Compose services are healthy with restart count `0`; `.env` is mode
  `600`, the named PostgreSQL/media volumes are unchanged, and Nginx/TLS was not
  modified. Anonymous HTTPS edge checks return `401` with the pilot noindex
  header, while internal `/health/live`, `/health/ready` and web
  `/account/notifications` return `200`.
- Current-source verification for this release: backend `230 passed` on a
  disposable PostgreSQL `_test` database; the initial web suite passed `200`
  tests across `43` files. The follow-up auth-error regression fix and smoke
  coverage raise the current web suite to `207` tests; typecheck and isolated
  production build pass.
  Compose config, Python compileall, and backup helper tests passed for the
  release process. One existing Starlette/AnyIO deprecation warning remains.
- Remaining launch gates are explicit: off-host encrypted backup/restore and
  measured RPO/RTO, real-device HEIC samples, release-image load measurement,
  a fresh stateful company-to-dealer flow on the VPS, and legal/public-indexing
  preparation. In-app web notification delivery is deployed and tested; an
  email provider remains unconfigured and unsupported. The closed pilot remains
  behind Basic Auth and `noindex`.

## VPS release completion — 30 September 2026, `pilot-20260930T004119Z`

- The release switch completed at `/home/suite/apps/releases/pilot-20260930T004119Z`;
  `pilot-20260930T000430Z` remains available for rollback. The deployment
  command reported all four Compose services healthy. No migration was run;
  Alembic was already at `0009_notification_outbox`.
- API and web image IDs are
  `sha256:a369bc7f377a0a44eeb4b66fc0e74c3173913d455baec8665f2508d491edd311`
  and
  `sha256:f14684f98fc3a1d11274942e882fdcdd2171fb5861b1307ea2034d3111704ea8`;
  both target `linux/amd64`. The filtered source archive checksum is
  `6c44479786669983a7afc5cf8f9e6b5dea1bd8ce1b70850f57a8362f0cee4459`.
- Pre-deploy snapshot
  `/home/suite/backups/avtorinok/pre-deploy-pilot-20260930T004119Z/avtorinok-20260930T004407Z`
  has 31 verified checksums and a PostgreSQL dump readable by `pg_restore -l`.
  No post-deploy snapshot has been created for this tag yet.
- Anonymous HTTPS edge responses return `401` with `noindex`; authenticated
  edge requests return `200`. The full browser smoke passes `29/29`, with no
  JavaScript errors or failed/server-error requests. Active listings remain
  absent, so buyer detail and favorite mutations were skipped.
- A fresh read-only BatchMode SSH attempt returns
  `Permission denied (publickey,password)`. Therefore restart counts, current
  `.env` mode, and Docker volume IDs are not independently confirmed after the
  switch. The deploy did not delete volumes or modify Nginx/TLS. The next
  operational step is restore SSH-agent authentication, inspect those values,
  and create/verify the post-deploy backup before marking deployment acceptance
  complete.

## Local continuation verification — 30 September 2026

- The current checkout adds trim-before-validation for required company name,
  address, and phone fields, plus a PostgreSQL integration test for company
  creation, admin approval, company-owned listing submission/publication,
  dealer visibility, and hiding the company and listing after blocking. The
  new test uses a unique UNP so it remains isolated from other suite cases.
- Duplicate company UNP conflicts return `409 company_unp_exists`, including
  database uniqueness violations; the company lifecycle test covers the
  duplicate request and the fresh backend suite passed with this change.
- The mobile header now closes its open menu when the seller follows the
  primary “Подать объявление” link. A regression test covers the interaction.
- Full backend suite: `234 passed` against an ephemeral, loopback-only
  PostgreSQL 17.11 container and a dedicated database named
  `avtorinok_codex_20260930_test`; the container was stopped and removed after
  the run. Web suite: `208 passed` across 43 files; typecheck, production build,
  and `make config-check` passed.
- Fresh anonymous edge smoke against `https://suite-s1.denjik.by` passed all
  four expected `401`/`noindex` checks. Authenticated edge requests were
  skipped because credentials were not configured. These local source changes
  are not in `pilot-20260930T004119Z` and have not been deployed.
- Restored the 26 canonical backup artifacts required for Drom batches 1–9
  from all nine owner-supplied ZIPs into `data/licensed/`. ZIP member names and
  CRCs were verified; the directory is mode `700` and files are mode `600`
  (156,399,849 bytes total). A fresh CSV read counted 194,817 rows and 194,817
  unique source URLs. The licensed source directory is excluded from Docker
  builds and future Git tracking. Archive analysis confirms the source does
  not establish global generation boundaries for all named control models,
  so `generation_depth_verified` remains false.
- Fresh backup/restore/offsite/retention/daily-backup checks: `59 passed`;
  `scripts/release-preflight.sh --release-dir . --skip-compose` and shell
  syntax checks passed. `make config-check` also passed in this verification.
- SSH agent currently has no loaded identities; the current Buildx Colima
  builder advertises only `linux/arm64` and `linux/386`, and the default
  builder is unavailable. No off-host target is configured in this session.
  Post-deploy backup, host-state reread, rebuilding/deploying the latest source,
  and off-host backup/restore remain blocked. Real-device HEIC, a load run
  against the exact current release image, and public-launch legal inputs also
  remain external gates.

## SMS migration fix and final local verification — 30 September 2026

- Reproduced the clean-database migration failure at `0011_sms_otp_auth`:
  `0001_initial` creates tables from current ORM metadata, which already
  contains the SMS phone fields and tables; `0011` then tried to add them a
  second time. The migration now checks existing columns, constraints, tables,
  and indexes before adding anything. A regression test exercises `0011` over
  the current-metadata bootstrap schema.
- PostgreSQL 17.11 verified both an empty-database upgrade through
  `0011_sms_otp_auth` and a separate `0009_notification_outbox` to `head`
  upgrade. Repeating `upgrade head` is a no-op. Backend suite: `269 passed`;
  Ruff passed for the migration and test import ordering; Python compilation
  passed for both changed files.
- Web suite: `244 passed`; TypeScript typecheck and optimized production build
  passed. `make config-check` and
  `scripts/release-preflight.sh --release-dir . --skip-compose` passed.
- Batches 4–9 ZIP members match the 18 canonical extracted files byte for byte;
  these files contain 29,684 modification rows. With batches 1–3, the
  documented full catalog is 194,817 modifications. They remain vehicle
  catalog data, not sale listings.
- Fresh anonymous requests to `/`, `/robots.txt`, and `/api/v1/listings` all
  returned `401` with `X-Robots-Tag: noindex, nofollow, noarchive`. A fresh SSH
  login was rejected, including after loading available Keychain identities;
  the agent was returned to its original empty state. No VPS state was read or
  changed, and the local migration fix has not been deployed. The last
  documented active release remains `pilot-20260930T004119Z`; its
  post-deploy backup and fresh runtime audit remain unverified.
