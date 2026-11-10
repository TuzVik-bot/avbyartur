# Off-host Backup Delivery

Only age-encrypted bundles leave the host. The former plaintext transfer of a
snapshot directory (database dump, private media) has been removed:
`scripts/backup-offsite.sh` without `--encrypted-bundle` prints usage and
exits with status 2 without contacting the remote host.

## Daily automatic delivery

`deploy/systemd/avtorinok-offsite-backup.timer` starts
`avtorinok-offsite-backup.service` every day at 04:30 (plus up to 15 min random
delay, `Persistent=true`), after the local `avtorinok-backup` timer has
produced the newest snapshot. The service runs
`scripts/backup-offsite-daily.py --backup-root /home/suite/backups/avtorinok`,
which:

1. Picks the newest complete snapshot directory named
   `avtorinok-YYYYMMDDTHHMMSSZ` (partial or suffixed names are skipped).
2. Exits successfully without a transfer if `offsite-status.json` already
   records that snapshot's bundle as delivered.
3. Encrypts the snapshot with `scripts/backup-encrypt.py` into a private
   temporary work directory inside the backup root.
4. Sends only the `.tar.age` ciphertext with
   `scripts/backup-offsite-encrypted.py` (the same code path as
   `backup-offsite.sh --encrypted-bundle`): staged upload, remote SHA-256
   check, then a no-clobber rename.
5. On success, atomically writes `BACKUP_ROOT/offsite-status.json` (mode `600`)
   with `schema_version`, `bundle`, `snapshot_created_at_utc` and
   `delivered_at_utc`. The local ciphertext is always removed afterwards; it
   can be recreated from the snapshot.

Each run logs one JSON line to stderr (journald): `offsite_backup_delivered`,
`offsite_backup_current`, or `offsite_backup_failed` with `reason`
(`no_snapshot`, `encrypt`, `transfer`). A failure leaves the previous status
file untouched.

`avtorinok-monitor.service` passes `--offsite-status-file
/home/suite/backups/avtorinok/offsite-status.json --max-offsite-age-hours 48`
to `scripts/monitor-runtime.py`. The monitor raises `offsite_backup_stale`
when the status file is missing, not a regular file, accessible to group or
others, unreadable or invalid, or when the newest
delivered snapshot is older than 48 hours (allowed range 1–336).

### Installation (operator, on explicit request only)

1. Generate the age identity on a separate recovery workstation (see step 1 of
   the manual workflow below). Only the public `age1...` recipient goes to the
   server.
2. Create `/etc/avtorinok/offsite-backup.env` as `root:root`, mode `600`:

   ```sh
   AVTORINOK_OFFSITE_TARGET=backup-user@backup-host:/absolute/path
   AVTORINOK_BACKUP_AGE_RECIPIENT=age1...
   ```

   The script refuses to start unless both variables and the backup root are
   set.
3. Give the `suite` user a passphrase-less SSH key restricted to the backup
   host, and provision the backup host key in `~suite/.ssh/known_hosts`
   through a trusted channel (`StrictHostKeyChecking=yes`, `BatchMode=yes`).
4. Run a manual preflight with an encrypted bundle (step 3 of the manual
   workflow) before enabling the timer.
5. Install the unit and timer from `deploy/systemd/`, then
   `systemctl enable --now avtorinok-offsite-backup.timer`. Without root,
   follow the user-unit instructions in the header of
   `avtorinok-offsite-backup.service`.
6. Start one run with `systemctl start avtorinok-offsite-backup.service`,
   check `journalctl -u avtorinok-offsite-backup.service` for
   `offsite_backup_delivered`, and confirm that `offsite-status.json` exists.
   The monitor alert `offsite_backup_stale` stays active until the first
   successful delivery.

Remote bundles are never pruned or overwritten by these scripts; the remote
retention schedule is operator-managed.

## Manual encrypted bundle workflow

Use these steps for a one-off copy, a preflight before enabling the timer, or
an investigation. Encrypt each completed snapshot before sending it to a remote
host:

1. On a separate recovery workstation, generate and protect an age identity.
   Keep this private identity outside the backup host and repository:

   ```sh
   mkdir -m 700 -p "$HOME/.config/avtorinok"
   age-keygen -o "$HOME/.config/avtorinok/backup-identity.txt"
   chmod 600 "$HOME/.config/avtorinok/backup-identity.txt"
   age-keygen -y "$HOME/.config/avtorinok/backup-identity.txt"
   ```

   Give the backup operator only the public `age1...` recipient printed by
   `age-keygen -y`. Keep at least one protected copy of the identity separate
   from the encrypted bundles; losing it makes those bundles unrecoverable.

2. After `scripts/backup.sh` completes, set `SNAPSHOT` to its printed
   directory and `AGE_RECIPIENT` to that public recipient. Encrypt the
   validated snapshot:

   ```sh
   BUNDLE="$SNAPSHOT.tar.age"
   python3 ./scripts/backup-encrypt.py "$SNAPSHOT" \
     --recipient "$AGE_RECIPIENT" --output "$BUNDLE"
   ```

   The command accepts the exact manifest and file sets for snapshot formats
   1–5, verifies their SHA-256 entries before packaging, streams the files
   directly through age without writing a plaintext archive, and refuses to
   overwrite an existing bundle. The bundle is mode `600`. Per-file and total
   payload limits are 250 GiB and 500 GiB.

3. Provision the remote SSH host key through a trusted channel into
   `known_hosts`. Set `AVTORINOK_OFFSITE_TARGET` to an explicit
   `user@host:/absolute/path`, then run the read-only preflight:

   ```sh
   AVTORINOK_OFFSITE_TARGET='backup-user@backup-host:/srv/avtorinok-backups' \
     ./scripts/backup-offsite.sh --encrypted-bundle --preflight "$BUNDLE"
   ```

   It checks the local age header and file permissions, SSH host-key access,
   remote `rsync`, SHA-256 tooling, GNU `mv -T -n`, destination availability,
   and free space with a 10% margin. It does not create a remote directory,
   stage, or file.

4. After reviewing a successful preflight, explicitly run the transfer:

   ```sh
   AVTORINOK_OFFSITE_TARGET='backup-user@backup-host:/srv/avtorinok-backups' \
     ./scripts/backup-offsite.sh --encrypted-bundle "$BUNDLE"
   ```

   This sends only the encrypted `.age` file into a mode-`700` staging
   directory. The remote SHA-256 must match the local ciphertext digest before
   a no-clobber rename publishes the final file. A failed transfer or check can
   leave a hidden `.incoming` directory for inspection; the script never
   deletes or overwrites a remote bundle. Before transfer, the local script
   creates a private mode-`700` temporary directory and a mode-`600` copy while
   validating and hashing one open source file. Allow temporary storage for
   roughly one additional bundle; read-only preflight does not create this
   copy. SSH uses
   `BatchMode=yes` and `StrictHostKeyChecking=yes`; provision host keys
   separately and use an SSH agent or externally managed key setup.

The scripts do not configure a remote destination, start a transfer, prune
remote bundles, or perform a restore automatically. The normal seven-copy
retention applies to plaintext local snapshot directories only; encrypted
bundles and remote copies need an operator-managed retention schedule that
preserves at least one independently tested recovery copy. Do not remove an
encrypted bundle or its identity before a separate restore rehearsal succeeds.

## Decrypting a bundle

Copy the encrypted file to a protected local directory and use the matching
recovery identity. The output path must not already exist; its parent must
already be a real directory. The command validates age authentication, tar
entry types and paths, supported file names, snapshot manifest, and checksums
before publishing a restore-compatible snapshot directory. The restored
directory is mode `700`; its files are mode `600`. Decryption does not invoke
`restore.sh` or modify application data.

```sh
mkdir -m 700 -p "$HOME/avtorinok-restore"
python3 ./scripts/backup-decrypt.py "$BUNDLE" \
  --identity "$HOME/.config/avtorinok/backup-identity.txt" \
  --output "$HOME/avtorinok-restore/avtorinok-YYYYMMDDTHHMMSSZ"
```

`restore.sh` consumes the resulting snapshot directory. It replaces the
active database, so perform any restore rehearsal in a separate isolated
project with separate databases and volumes. Local encryption/decryption
verification is not evidence of a remote transfer, off-host restore, or
production RPO/RTO measurement.

## Configuration status

`AVTORINOK_OFFSITE_TARGET` must be set explicitly for every transfer. The
repository contains no remote credentials or configured destination. Until an
operator configures a real target, a successful delivery appears in
`offsite-status.json`, and a separate isolated restore rehearsal from a remote
bundle completes, off-host delivery is not confirmed.
