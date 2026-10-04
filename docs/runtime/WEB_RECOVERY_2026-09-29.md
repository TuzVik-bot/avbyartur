# Web recovery check — 2026-09-29

Read-only inspection found the deployed web container repeatedly exiting with
status 139. The kernel journal recorded repeated Node general-protection faults
in `ld-musl-x86_64.so.1`; Docker reported `OOMKilled=false`. The host and both
the current and prior web images are x86_64 / `linux/amd64`. Host memory and
disk had ample availability.

At 14:52:45 UTC, from release
`/home/suite/apps/releases/pilot-20260929T125300Z`, recreated only `web` with
`docker compose up -d --no-deps --no-build --force-recreate web`. It reused
image `avtorinok-web:pilot-20260929T125300Z`
(`sha256:15d0d5243a4408bb7b52d4518c588e2b183bf42324992e1b491345f48445b6e0`).
No API, database, worker, volume, or Nginx changes were made. Compose reported
an existing prior-release candidate as an orphan; it was left untouched.

At 14:55:09 UTC, 144 seconds later, web was again `Restarting (139)` with 11
restarts, unhealthy, and `OOMKilled=false`. A request to the local upstream
`http://127.0.0.1:8080/` failed with connection refused (HTTP status `000`).
The unauthenticated public HTTPS request to `/` returned `401`, so the Basic
Auth barrier remained active. No authenticated UI smoke was possible while the
upstream was unavailable; no Basic Auth credential was supplied for this check.

The web-only recreate did not restore the UI. Further recreates are not
recommended; investigate and ship a web runtime/image fix before another start
attempt. No whole-release rollback was performed.

The prior web image `pilot-20260929T094728Z` is retained, but is not verified
as a recovery image on the current kernel: it exited 143 when stopped before
the current boot and has not been started since. Both images are `linux/amd64`
and share the first five of nine filesystem layers; the remaining layers differ.
Thus its behavior with the current musl/kernel interaction and compatibility
with the active API remain unverified. Switching only the web image is a
possible later diagnostic, but was not performed or approved here.
