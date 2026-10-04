# Backend

FastAPI service for the closed vehicle marketplace pilot. PostgreSQL 17 is the source of truth. Public registration is disabled; pilot accounts are created by an operator. Put the API and site behind the pilot password gate at the reverse proxy. In production, use same-origin HTTPS, keep the database and worker private, and mount `/app/private-media` as a private writable volume. Mount the seed input read-only at `/app/data/catalog.json`.

## Local startup

Requirements: Python 3.12, `uv`, and PostgreSQL 17. The repository runtime setup may provide PostgreSQL through Compose.

```sh
cd backend
uv sync --python 3.12
export DATABASE_URL='postgresql+psycopg://avtorinok:avtorinok@localhost:5432/avtorinok'
export SESSION_SECRET='replace-with-a-random-secret-of-at-least-32-bytes'
export SESSION_COOKIE_SECURE=false
uv run alembic upgrade head
uv run python -m app.cli create-user --email admin@example.test --display-name 'Pilot Admin' --role admin
uv run python -m app.cli import-catalog --path ../data/catalog.json --dry-run
uv run python -m app.cli import-catalog --path ../data/catalog.json
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`create-user` prompts for the password without echo. Use at least 12 characters. Public account registration stays disabled unless separately opted in. For production keep `SESSION_COOKIE_SECURE=true`; session cookies are HttpOnly, Secure, SameSite=Lax and expire after seven days. The browser-readable CSRF cookie must be copied into `X-CSRF-Token` on every state-changing request. `GET /api/v1/me` returns the current CSRF token after reload.

Only configure `TRUSTED_PROXY_CIDRS` when the immediate peer is an owned reverse proxy. Forwarded client IPs are ignored otherwise.

Start the durable worker in a separate process with the same database and private-media mount:

```sh
cd backend
uv run python -m app.worker
```

The worker claims PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, leases each claim, retries failures with bounded exponential delay, recovers expired leases, and uses a PostgreSQL advisory lock so only one worker process handles an image at a time. Photo originals stay in `/app/private-media/.quarantine`; successful jobs write WebP variants under a random directory and remove the original. Submit is rejected until every selected photo is `ready`. The same queue refreshes the official USD rate daily; stale or missing rates are omitted from BYN conversion.

## Catalog seed format

`/app/data/catalog.json` is a read-only operator-supplied input. Version 1 is an object with:

```json
{
  "schema_version": 1,
  "source": {
    "name": "Wikidata",
    "license": "CC0 1.0",
    "retrieved_at": "2026-09-27T00:00:00Z",
    "query_url": "https://query.wikidata.org/"
  },
  "makes": [
    {
      "qid": "Q...",
      "name": "Example make",
      "slug": "example-make",
      "aliases": [],
      "models": [
        {
          "qid": "Q...",
          "name": "Example model",
          "slug": "example-model",
          "aliases": [],
          "generations": [
            {"qid": "Q...", "name": "Generation", "year_from": null, "year_to": null, "body_variants": []}
          ]
        }
      ]
    }
  ],
  "body_types": [{"name": "Sedan", "slug": "sedan"}],
  "regions": [{"name": "Region", "slug": "region", "cities": [{"name": "City", "slug": "city"}]}]
}
```

Models, generations, body variants, body types, regions and cities may be empty arrays when the source has no verified facts. Each import validates before the transaction, records the SHA-256 and source/license metadata, and upserts by Wikidata QID (`wikidata:Q...`) or parent plus slug. Repeating the same file is a no-op. Omitted rows are retained, stable IDs remain in PostgreSQL, and rows marked `manual_override=true` are not overwritten. `--dry-run` validates and executes the import in a rolled-back transaction.

## API

The OpenAPI schema in development is at `/openapi.json`; interactive docs are at `/docs`. Application endpoints use `/api/v1` and error JSON uses `{code,message,field_errors,request_id}`.

- `POST /auth/login`, `POST /auth/logout`, `GET /me`: existing email/password and server-side sessions remain available. The provider-neutral SMS OTP API is present at `GET /auth/otp/csrf`, `POST /auth/otp/request`, and `POST /auth/otp/verify`; its login switch defaults to `SMS_LOGIN_ENABLED=false`. Registration OTP is separately gated by `PUBLIC_REGISTRATION_ENABLED=false` and, when enabled in a future release, requires configured `REGISTRATION_TERMS_VERSION` and `REGISTRATION_PRIVACY_VERSION` values. Both OTP request routes require the pre-auth CSRF token and `Idempotency-Key`; the code is single-use, expires after five minutes by default, and is stored only as a keyed digest. IP and phone rate limits apply. A repeated key acknowledges only a delivered or intentionally suppressed challenge. If delivery failed or its outcome is uncertain, repeating that key returns 503; retry with a new key after the resend cooldown.
- `POST /auth/register`: public email/password registration, off by default (`EMAIL_REGISTRATION_ENABLED=false`). It requires the pre-auth CSRF token from `GET /auth/otp/csrf`, a password of at least 12 characters, accepted terms and privacy versions that match the configured and published approved documents, and it is rate-limited per IP. A duplicate email returns 409 `email_taken`; success creates the account with consent records and a session. The email is not verified at signup; the user can verify it from the profile once SMTP is configured.
- `GET /catalog/*`, `GET /locations/*`: read-only imported catalog and geography.
- `POST /listings/drafts`, `PATCH /listings/{id}`, `POST /listings/{id}/submit`: owner-only drafts, revision checks, company selected from the signed-in owner's approved company, and quota reservation during review.
- `POST /listings/{id}/pause|resume|sold`, `GET /me/listings`: owner workspace and state changes.
- `GET /listings`, `GET /listings/{id}`: active search and public listing details. Drafts and blocked listings return 404 to other users. Money amounts are decimal strings. Price filter and price sort require an explicit currency until a validated cross-currency rate path is available.
- `POST /listings/{id}/phone-reveal`, `POST /listings/{id}/reports`: protected contact and complaint actions.
- `GET /me/favorites`, `PUT|DELETE /me/favorites/{listing_id}`: idempotent favorites.
- `POST /listings/{id}/photos`, `GET /listings/{id}/photos`, `DELETE /listings/{id}/photos/{photo_id}`, `POST /listings/{id}/photos/reorder`, `POST /listings/{id}/photos/{photo_id}/cover`: owner draft uploads and status polling. Each upload requires `Idempotency-Key`; the multipart field is `file`.
- `GET /me/company`, `POST /companies`, `PATCH /companies/{id}`, `GET /dealers`, `GET /dealers/{slug}`: a single owner account per company; edits to approved details send the company back to review.
- `GET /moderation/listings|companies|reports`, decision endpoints under `/moderation/*`: moderator/admin only; state decisions are audited.
- `/health/live`, `/health/ready`: process and PostgreSQL health.

The SMS provider factory intentionally returns an unconfigured provider. No vendor, credentials, or consent text are selected here, and enabling `SMS_LOGIN_ENABLED` alone cannot send a message. Before configuring a real adapter, set a random `SMS_OTP_SECRET` of at least 32 characters; do not put the value in source control. Public registration also requires separately approved legal copy/version identifiers and `PUBLIC_REGISTRATION_ENABLED=true`. Keep both SMS switches off until a real SMS provider is configured; email registration is enabled separately with `EMAIL_REGISTRATION_ENABLED=true` and the same consent version settings. P0 intentionally has no public signup, live SMS delivery, chat UI, payments, external dealer feeds, VIN history check, saved-search notifications, moderator impersonation, or public phone in listing JSON. HEIC decoding depends on the pinned pillow-heif build and still needs verification with real HEIC samples on the target container architecture.

## Tests

Unit and PostgreSQL integration tests live in `tests/`. Set `TEST_DATABASE_URL` to a dedicated disposable PostgreSQL database whose name ends in `_test`, and set `TEST_DATABASE_DISPOSABLE_CONFIRMATION` to that exact database name. The fixture refuses the known preview database, the runtime database, and targets without the matching confirmation before it creates or drops tables.

```sh
cd backend
export TEST_DATABASE_URL='postgresql+psycopg://avtorinok:avtorinok@localhost:5432/avtorinok_test'
export TEST_DATABASE_DISPOSABLE_CONFIRMATION='avtorinok_test'
uv run pytest
```
