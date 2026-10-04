# Identity package report

## Scope

Implemented the profile identity package for Task 11:

- two-code, purpose-bound phone replacement proof using the existing SMS adapter;
- idempotency, expiry, attempt limits, uniqueness checks, stale/replayed-code
  rejection, and revocation of all active sessions after a successful change;
- versioned global web/email notification preferences and a delivery policy
  helper. Existing accounts without a preference row remain enabled for both
  channels; explicit email opt-out is enforced by the worker integration;
- registration consent version contracts and fail-closed validation against
  published, approved managed legal documents;
- Alembic migration `0018_profile_identity` after `0017_listing_completion`.

## Owned files

- `backend/app/profile_identity_models.py`
- `backend/app/profile_identity_schemas.py`
- `backend/app/profile_identity_service.py`
- `backend/app/api/profile_identity.py`
- `backend/alembic/versions/0018_profile_identity.py`
- `backend/tests/test_profile_identity.py`

Required integration edits were also made in `backend/app/api/auth.py`,
`backend/app/sms_auth_schemas.py`, and `backend/alembic/env.py`; `main.py` and
`worker.py` remain coordinator-owned.

## Verification

- `python -m compileall` passes for all identity modules and tests.
- A protected identity-lane run was attempted with the required runner and
  dedicated test database. The sandbox cannot connect to the runner's loopback
  PostgreSQL port (`Operation not permitted`), so no PostgreSQL integration
  result is claimed here. Logs are retained under
  `.superpowers/sdd/2026-10-01-project-completion/`.
- A genuine route-level RED test was captured before the router was integrated:
  the new phone-change endpoint returned `404` instead of the required
  unauthenticated `401`. The post-integration test still requires a
  DB-capable runner invocation by the coordinator.

## Coordinator integration still required

- Add the `notification_delivery_allowed(..., "email")` guard in the existing
  worker email branch. The worker already enforces verified contact, provider,
  public URL, and saved-search gates.
- Run the identity lane from the DB-capable process, adapt existing SMS
  registration fixtures with approved managed legal documents and the two
  displayed document versions, and resolve any migration-chain conflict if a
  parallel task adds another revision after `0017`.
