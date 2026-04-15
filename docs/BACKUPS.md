# Voyagent Backups

This document covers the full backup story for the voyagent production
database: where dumps live, how long we keep them, how to ship them offsite,
and how to restore from a dump if something goes very wrong.

> Scripts referenced here live in `infra/deploy/scripts/`. The existing
> `pg-backup.sh` + `voyagent-pg-backup.{service,timer}` ship the local
> backup; `pg-backup-offsite.sh` + `voyagent-pg-backup-offsite.{service,timer}`
> add the offsite leg.

---

## 1. Local backups (always on)

| Item | Value |
|---|---|
| Directory | `/opt/voyagent/backups/` |
| File pattern | `voyagent-YYYYMMDDTHHMMSSZ.dump` |
| Format | `pg_dump -Fc --no-owner` (custom format) |
| Schedule | 02:00 UTC daily (`voyagent-pg-backup.timer`) |
| Retention | 30 most recent dumps |
| Runs as | root |
| Script | `infra/deploy/scripts/pg-backup.sh` |

View the timer state:
```
systemctl status voyagent-pg-backup.timer
journalctl -u voyagent-pg-backup.service --since -2d
```

---

## 2. Offsite backups (opt-in)

Offsite is opt-in so a fresh host doesn't fail its nightly run because no
bucket exists yet. Enable it by creating `/opt/voyagent/.env.offsite-backup`.

### Supported backends

Anything `rclone` supports. Tested shapes:

- **AWS S3** — standard or S3-compatible regions
- **Backblaze B2** — cheapest for cold storage
- **Cloudflare R2** — no egress fees, good for disaster recovery pulls
- **Wasabi** / **MinIO** / **DigitalOcean Spaces** / **Scaleway**

### One-time host setup

1. Install rclone (not bundled — user action):
   ```
   sudo apt-get update && sudo apt-get install -y rclone
   ```
2. Create a remote config interactively (as root, since the timer runs as
   root):
   ```
   sudo rclone config
   ```
   Give the remote a memorable name, e.g. `b2-backups`. It will be stored
   at `/root/.config/rclone/rclone.conf` with mode 0600.
3. Create the credential env file:
   ```
   sudo install -m 0600 -o root -g root /dev/null /opt/voyagent/.env.offsite-backup
   sudo tee /opt/voyagent/.env.offsite-backup >/dev/null <<'EOF'
   VOYAGENT_BACKUP_REMOTE=b2-backups
   VOYAGENT_BACKUP_BUCKET=voyagent-prod-dumps
   VOYAGENT_BACKUP_PREFIX=voyagent/
   VOYAGENT_BACKUP_RETENTION_REMOTE=90
   EOF
   ```
4. Install the offsite timer + service:
   ```
   sudo cp infra/deploy/systemd/voyagent-pg-backup-offsite.service /etc/systemd/system/
   sudo cp infra/deploy/systemd/voyagent-pg-backup-offsite.timer   /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now voyagent-pg-backup-offsite.timer
   ```

### Dry-run validation (no credentials burned, no bytes moved)

```
sudo /opt/voyagent/repo/infra/deploy/scripts/pg-backup-offsite.sh --dry-run
```

The `--dry-run` path:
- skips the local `pg-backup.sh` invocation,
- runs `rclone copy --dry-run` against the newest existing local dump,
- runs `rclone delete --dry-run` to preview the retention prune.

### Schedule + retention

| Item | Value |
|---|---|
| Schedule | 03:30 UTC daily (90 min after the local backup) |
| Retention | 90 days in the remote bucket |
| Pruning | `rclone delete --min-age ${VOYAGENT_BACKUP_RETENTION_REMOTE}d` |

---

## 3. Restoring from a dump

Use `pg-restore.sh`. It is intentionally interactive and intentionally
destructive — a restore is a manual incident-response action, not a cron.

1. Fetch the dump (from local or offsite):
   ```
   # local
   ls -1t /opt/voyagent/backups/voyagent-*.dump | head

   # offsite
   sudo rclone copy b2-backups:voyagent-prod-dumps/voyagent/voyagent-20260415T030000Z.dump /opt/voyagent/backups/
   ```
2. Run the restore:
   ```
   sudo /opt/voyagent/repo/infra/deploy/scripts/pg-restore.sh \
        /opt/voyagent/backups/voyagent-20260415T030000Z.dump
   ```
3. When prompted, type `RESTORE VOYAGENT` exactly. Anything else aborts.
4. The script stops voyagent-api / web / marketing / worker, drops and
   recreates the DB, runs `pg_restore`, then restarts the services.

---

## 4. Verifying a restore

After the script exits, do all of the following before declaring the
restore good:

1. `curl -fsS https://voyagent.globusdemos.com/health` — should return 200.
2. Sign in as a known test user on the web app.
3. Spot-check one booking and one invoice from the affected day.
4. Tail the API log for 60 s and confirm no unexpected 500s:
   ```
   journalctl -u voyagent-api -f
   ```

If any of these fail, escalate per `docs/RUNBOOK.md`.

---

## 5. What is NOT backed up here

- Redis (treated as cache — no dumps)
- Object storage (handled by the storage backend's own versioning)
- Secrets in `/etc/voyagent/` and `/opt/voyagent/.env.prod` (see
  `docs/SECRET_ROTATION.md` — these must be backed up out-of-band to a
  password manager, never to the same bucket as the DB dumps)
