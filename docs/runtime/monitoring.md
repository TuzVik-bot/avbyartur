# Runtime Monitoring

The admin-only `GET /api/v1/admin/monitoring` endpoint returns a typed,
uncached snapshot of safe aggregates. It never returns job payloads, database
row identifiers, source names, phone numbers, email addresses, provider
references, error messages, or credentials. The route is protected by the
existing admin dependency and sets `Cache-Control: no-store`.

## API metrics

- Worker failures, queued jobs past `run_after`, and running jobs with expired
  leases; ages are seconds only.
- Saved-search outbox failures and unsupported deliveries, aged queued work,
  identity email outbox failures/backlog, and the oldest failed notification
  age across those stores.
- SMS send, delivery-failure, and suppression counts for recent challenges.
  These fields are `null` when no recent SMS challenge rows exist.
- Dealer feed import failures in the previous 24 hours.
- Failed payment attempts and pending attempts at least 30 minutes old.
- The latest USD exchange-rate fetch time and age, marked stale after 72 hours.
- A public active-listing count from the same PostgreSQL query and filters
  used by the application listing search. There is no external search index;
  `external_search` is always `false` and parity is reported as `same_store`.
- Optional local Sentry SDK counters. They appear as `null` when Sentry is
  disabled. `accepted` means the SDK accepted the event for transport; Sentry
  does not provide a synchronous remote delivery receipt. Counts are
  process-local and are not a multi-worker or historical total.

Alerts contain only fixed safe codes, severity, and aggregate counts. No
notifications are sent by the API.

## Optional host status file

The API reports host backup/runtime details as `unconfigured` by default. An
unset or empty `MONITORING_STATUS_PATH` is normalized to `None`, so the closed
pilot can run without a host monitor or extra mount. If configured, the API
accepts only a regular, non-symlink file owned by the API UID, mode `0400` or
`0600` (or stricter), and at most 4 KiB. It opens with no-follow semantics,
checks that the file did not change while being read, and validates an exact
allowlist schema. Invalid, missing, or older-than-15-minute status is reported
as unavailable/stale without returning the path or parse error.

The status document contains only schema version, monitor state, check time,
Docker health, backup service state and timestamps, checksum result, and fixed
alert codes. It contains no host paths, backup names, row data, credentials, or
logs. When enabled, mount that single host file read-only into the API
container, set `MONITORING_STATUS_PATH` to its container-side path, and ensure
the file owner is UID `10001` and parent directories are traversable by that
UID. Keep the Basic Auth credential file separate from this status directory.
The compose mount and setting are optional and are not part of the default
stack.

## Host monitor

`scripts/monitor-runtime.py` is a local host checker. It:

1. Reads Basic Auth credentials from a caller-specified regular file owned by
   the executing user with mode `0400` or `0600`; credentials never appear in
   arguments, output, or logs.
2. Uses an authenticated GET of `/healthz` and checks `db`, `api`, `worker`,
   and `web` with `docker compose ps --format json`.
3. Reads the last result and completion timestamp of
   `avtorinok-backup.service` through `systemctl show`.
4. Selects the newest timestamped local backup directory, validates its
   manifest and full SHA-256 set with `backup_snapshot.validate_snapshot`, and
   takes freshness from the backup's manifest timestamp and successful
   systemd completion time. It does not infer backup freshness from file
   modification time.
5. Writes a mode-`0600` safe status document and an alert-state file atomically.
   Repeated unchanged alert codes do not appear as new alerts in JSON output.

The command exits `0` when healthy, `1` on an actionable runtime/backup
failure, and `2` when it cannot safely persist monitoring state. JSON output
contains only health booleans, timestamps, alert counts, and fixed codes. The
tool does not create backups, repair services, or send email, Slack, Telegram,
or other messages.

The systemd files in `deploy/systemd/avtorinok-monitor.{service,timer}` are
templates only; they have not been installed or started on a host. The sample
unit checks the closed-pilot origin and expects an operator-provisioned
`/etc/avtorinok/monitor-basic-auth` file. Review the hostname, credential-file
ownership/mode, directory access, backup root, and Compose project path before
any separate authorized host installation. The unit runs as root because it
must read mode-`0700` backup directories, query the Docker socket and publish a
mode-`0600` status file owned by UID `10001`; filesystem writes are restricted
to its state directory, project and backup trees are read-only, and the project
`.env` path is inaccessible to the service. Do not install or enable the timer
as part of a source-only change.

Example invocation (the access file must already be provisioned securely):

```sh
sudo python3 scripts/monitor-runtime.py \
  --project-dir /home/suite/apps/avtorinok \
  --base-url https://suite-s1.denjik.by \
  --access-file /etc/avtorinok/monitor-basic-auth \
  --backup-root /home/suite/backups/avtorinok \
  --state-file /var/lib/avtorinok-monitor/alerts.json \
  --status-file /var/lib/avtorinok-monitor/status.json \
  --status-owner-uid 10001
```

Do not put the credential contents into a shell command. The monitor requires
the backup timer and Docker Compose services to exist. A status file should be
mounted into the API container only after it has been generated and its owner,
mode, schema, and read-only mount have been checked.

## Verification limits

Unit tests exercise the host checks with local fixtures and stubbed Docker and
systemd responses. They do not prove a live VPS health request, service
installation, backup freshness on the VPS, an API status-file mount, or alert
delivery. No remote action or alert delivery is performed by this feature.

The source monitor timer runs every five minutes with at most one minute of
random delay; the API accepts host status up to fifteen minutes old. This
leaves schedule and execution headroom before reporting stale status. The
updated timer is a template; it has not been installed on the VPS.
