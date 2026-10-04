# ABW metadata import evidence — 2026-09-29

## Result

Imported 100 ABW metadata records into the live pilot database as unpublished
`draft` listings. None were made public. The snapshot did not contain seller
identity, phone, photos, region, condition, or VIN; those values were not
fabricated or imported. The existing application schema defaults
`damaged=false` and `parts_only=false` for new rows; this limitation is retained
only on these drafts and is not source evidence.

The records are attributed internally to the existing active operator account
`Pilot Admin` (`admin@suite-s1.denjik.by`) because the schema requires an owner.
This is an operational attribution, not a claim that the admin is the seller.

## Artifacts and backup

- Snapshot: `data/abw_import_20260929.json`
- Snapshot SHA-256: `3f07f0aa74945afe1a6d9e46993169bdb459ad28e8c0fbca54774e390a458c8e`
- Importer SHA-256 used on VPS: `a31aa40a786f628fd5763dfd237e47135a9469866d30f1a8e0655a86bdb66b46`
- Active release: `/home/suite/apps/releases/pilot-20260929T125300Z`
- Pre-import database backup: `/home/suite/backups/avtorinok/abw-import-before-20260929T144936Z/database.dump`
- Backup size: 12,101,517 bytes; `pg_restore --list` succeeded with 171 TOC entries.
- Backup SHA-256: `2c545baf917a5bd5f7c91dd2b873b1e4688814fbe04698d180f9e58fee2bafdf`
- Backup TOC SHA-256: `da550c1a53cc0113de2cdb9f779ab5e7ceceaef898079210eee7c7cacd349bd3`

The host `.env` was mode `600`; the PostgreSQL and private-media volumes were
present. No migration, service restart, volume change, or Nginx change was made.

## Import and idempotency checks

- Live database dry-run before insert: `requested=100`, `existing=0`,
  `would_insert=100`, status `draft`.
- Import result: `requested=100`, `inserted=100`, `existing=0`, status `draft`.
- Repeat dry-run: `requested=100`, `existing=100`, `would_insert=0`.
- Database verification: 100 `abw-*` rows; all 100 are `draft`, owned by the
  operator account, with 100 `imported_abw_metadata` audit events.
- Imported rows have 0 photos, 0 status transitions, blank contact phone, and
  null VIN. No record is active or pending review.
- Public listings API returned `pagination.total=0` after import, as expected
  for drafts.

## Source-field completeness

The input has 100 unique HTTPS ABW detail URLs. In imported records:

- 32 have no city; 1 has no year; 5 have no engine volume; 10 have no power.
- All 100 have unknown condition, blank contact phone, no VIN, and no photos.
- The importer preserves unknown condition as `NULL`; it does not infer `used`.
- The records have source URL/provenance in description and audit metadata; raw
  source descriptions, phone numbers, VINs, and images are excluded.

These drafts cannot safely be submitted or published until a human supplies and
verifies the required seller/contact and location details and real photos. Do
not promote their status directly: the normal submit path requires those
fields, while a direct status change would bypass the application workflow.

## Inspection path and runtime caveat

The owner-facing page is `/account/listings` after signing in as the existing
operator account. The web container was still restarting with exit 139 during
verification, so the browser UI was unavailable and no visual UI acceptance is
claimed. API and database were healthy; the API and DB counts above were read
directly from the live application/database. The web issue is separate from
the imported draft records.
