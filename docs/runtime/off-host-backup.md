# Off-host Backup Delivery

## Encrypted bundle workflow

Off-host copying is opt-in and is not triggered by `make backup` or the daily
backup timer. Encrypt each completed snapshot before sending it to a remote
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

## Legacy plaintext snapshot transfer

`backup-offsite.sh BACKUP_DIRECTORY` and
`backup-offsite.sh --preflight BACKUP_DIRECTORY` remain available for
compatibility with existing v1–v5 workflows. They transfer the snapshot
directory in plaintext. Do not use this path for off-host storage when the
encrypted-bundle workflow is available.

The legacy preflight validates the local manifest and checksums, SSH host-key
access, remote `rsync`, checksum utilities, GNU `mv -T -n`, writable target
or nearest existing parent, a free final snapshot name, and enough remote
space for the local snapshot plus a 10% margin. It does not write remotely.
The transfer rechecks the snapshot in a per-snapshot staging directory before
a no-clobber rename. A failed transfer can leave a hidden `.incoming`
directory for inspection.

Both transfer modes require `AVTORINOK_OFFSITE_TARGET` to be explicitly set.
The repository contains no remote credentials or configured destination.
Until an operator configures a real target, runs preflight and transfer, and
completes a separate isolated restore rehearsal, off-host delivery is not
confirmed.
