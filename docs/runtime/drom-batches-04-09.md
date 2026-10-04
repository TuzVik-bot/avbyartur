# Drom batches 4–9

The owner states that Drom supplied these files under written permission. The six ZIP archives were kept unchanged in the user's Downloads folder; their extracted CSV, normalized JSON, and report files are stored under `data/licensed/` with mode `600`.

Each archive passed ZIP CRC verification and contained exactly one CSV, one JSON file, and one report. The CSV and JSON matched across all 19 columns, and each report's row count matched its files.

| Batch | Rows | Original archive SHA-256 |
|---:|---:|---|
| 4 | 1,938 | `38cdaa1b089763b41f229a2a0937199baf8a35826bfb5c95f74dfa4e05499b46` |
| 5 | 3,755 | `fe35a20de2a7f0e7675f8e5de18a8b774d82082fdd9e11f2591eeb62f12701c0` |
| 6 | 6,988 | `608024d4bcbca6059e838c81fb965066ea8db8ab0f33fab3cb5399ec51345bad` |
| 7 | 7,090 | `cc15c487daf73a7e09ff8ff64ebf524fd11e11f717f2972b162f700790008500` |
| 8 | 4,903 | `cbf2c21daa8cac86e3e0a8575023575697de22dcb419f733bea2e0ccdac6f3bc` |
| 9 | 5,010 | `545afddd52148a76bd361d2d70e76f394350d6ef30ea7afe69b6eb13dd059617` |

Across batches 1–9, the source data contains 194,817 rows with unique source URLs. There are 90 groups of repeated `source_id` values, so a source ID alone is not a global key. The importer canonicalizes each Drom URL and derives the external modification ID from that URL. It preserves an existing legacy record's UUID and changes its external ID only when the stored URL matches the same canonical URL.

A disposable PostgreSQL database accepted dry-run, import, and repeat import of all nine CSVs. The fresh test catalog contained 86 makes, 2,457 models, 13,993 generations, 13,249 body variants, 194,817 modifications, and 9 import records; these figures describe that empty test catalog, not the production catalog crosswalk. Re-import left the modification and import counts unchanged.

After deploying the URL-based identity importer, re-import batches 1–9 in order on the VPS after a verified format-5 pre-import backup. Replaying batches 1–3 migrates existing legacy keys in place while preserving matching modification UUIDs; applying only the new six batches would leave those older keys unmigrated.

The filtered code release excludes `data/licensed/`. Transfer the extracted source artifacts to the matching release directory separately, keep them mode `600`, and create the format-5 backup only after the complete batch 1–9 set is present. The API service mounts `data/` read-only; the one-off CLI process uses the service's database connection and does not modify the licensed files.

These files provide vehicle catalog data, not for-sale listings. The six new batches were imported to the VPS in release `pilot-20260929T222500Z` after a verified format-5 pre-import backup. They were replayed with dry-run checks showing no new modifications.
