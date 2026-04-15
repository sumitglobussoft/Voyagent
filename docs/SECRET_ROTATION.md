# Secret rotation

Voyagent stores production secrets in `/opt/voyagent/.env.prod` (root:root
0600) and in the per-component env files under `/etc/voyagent/`. This
document covers when to rotate them, how to rotate them, and what breaks
when you do.

Tools:

- `infra/deploy/scripts/rotate-secret.sh` — interactive rotation, one
  secret at a time, with backup + smoke test.
- `infra/deploy/scripts/verify-secrets.sh` — read-only sanity check.

## When to rotate

### Scheduled

| Secret | Cadence |
|---|---|
| `VOYAGENT_AUTH_SECRET` (JWT signing key) | every 90 days |
| `VOYAGENT_DB_URL` password | every 180 days |
| `VOYAGENT_REDIS_URL` password | annually |
| `VOYAGENT_METRICS_TOKEN` | annually |
| `VOYAGENT_KMS_KEY` | annually (more often if a leak is suspected) |

Stick these on the team calendar. "Annually" means once every 12 months,
not "whenever we remember".

### Incident response (rotate immediately)

- A secret leaked in a commit, log line, screenshot, or Slack message.
- A laptop that held `.env.prod` was lost or stolen.
- An employee with access left or changed roles.
- You see auth anomalies you can't explain (brute-force signature, odd
  geographies).

For incident rotation, see "Emergency playbook" below.

## Supported secrets

| Key | Side-effects | Downtime? |
|---|---|---|
| `VOYAGENT_AUTH_SECRET` | logged-in users get kicked | near-zero (services restart) |
| `VOYAGENT_DB_URL` | `ALTER USER voyagent WITH PASSWORD` + update `/etc/voyagent/postgres-master.env` | brief (API restart, ~5 s) |
| `VOYAGENT_REDIS_URL` | rewrites `requirepass` in `redis.conf` + restarts redis | brief (~5 s) |
| `VOYAGENT_METRICS_TOKEN` | dashboards/scrapers using the old token break | zero until the scraper retries |
| `VOYAGENT_KMS_KEY` | **NOT zero-downtime yet** — see below | TBD |

### What can't be rotated without downtime (yet)

- `VOYAGENT_KMS_KEY` rotation requires re-encrypting everything it
  protects. The rotation script only updates the key — the re-encryption
  pass is a separate manual procedure we haven't automated yet. **Don't
  rotate KMS without a plan** — it will leave existing ciphertext
  unreadable.
- If you rotate the DB password during business hours there's a brief
  window (milliseconds) where in-flight connections holding the old
  password will fail. Acceptable; users retry transparently.

## How to rotate (normal path)

Dry-run first so you can see exactly what would change:
```
sudo infra/deploy/scripts/rotate-secret.sh --dry-run
```

Real run, interactive:
```
sudo infra/deploy/scripts/rotate-secret.sh
```

The script will:

1. Ask which secret to rotate.
2. Print a warning if you picked `VOYAGENT_AUTH_SECRET`.
3. Require you to type `ROTATE <KEY>` exactly as confirmation.
4. Back up `/opt/voyagent/.env.prod` to
   `/opt/voyagent/.env.prod.bak.<ts>`.
5. Generate a new value (48-byte urlsafe token).
6. Rewrite the single line in `.env.prod` via Python (not `sed`).
7. Apply side-effects (ALTER USER, redis.conf update, etc.).
8. `systemctl restart` the voyagent services.
9. `curl /health` as a smoke test.

Non-interactive (for scripting):
```
sudo infra/deploy/scripts/rotate-secret.sh --secret VOYAGENT_METRICS_TOKEN
```

## Verification

Any time after `.env.prod` changes:
```
sudo infra/deploy/scripts/verify-secrets.sh
```

It checks:

- every required secret is set and non-empty,
- nothing matches an obvious placeholder (`changeme`, `REPLACE_ME`, etc.),
- `VOYAGENT_AUTH_SECRET` is at least 32 characters,
- `VOYAGENT_METRICS_TOKEN` is at least 16 characters,
- `VOYAGENT_DB_URL` parses as a URL with user + password + host,
- `VOYAGENT_REDIS_URL` parses as a URL with host.

Exit 0 on success; exit 1 with a printed list of problems on failure.
Safe to run as often as you like — it's read-only.

## Emergency playbook (leaked credential)

Time is of the essence. Order matters.

1. **Declare the incident.** Ping the team channel.
2. **Identify which secret(s) leaked.** If unsure, rotate all of them.
3. **Rotate** in this order (fastest blast-radius reduction first):
   1. `VOYAGENT_AUTH_SECRET` — kills any attacker-held JWTs.
   2. `VOYAGENT_DB_URL` — locks out DB access even with network access.
   3. `VOYAGENT_REDIS_URL`.
   4. `VOYAGENT_METRICS_TOKEN`.
   5. Any third-party keys (Anthropic, GDS vendor, Sentry) — rotate
      through their respective dashboards, not this script.
4. **Purge the leak.** Expire the git commit (rewrite + force push),
   delete the Slack/Sentry/log line, invalidate the screenshot.
5. **Rotate backups.** If the leak included `.env.prod.bak.*`, delete
   those backup files too.
6. **Audit.** Look at access logs for the affected service for the 24 h
   before the leak was spotted. Look for unusual sign-ins, unusual
   queries, unusual token usage.
7. **Post-mortem** within a week.

## What the rotation script does NOT do

- It does not rotate third-party vendor keys (Anthropic, Sentry, GDS
  sandbox). You do those in the vendor's own dashboard and then paste the
  new value into `.env.prod` by hand.
- It does not replicate the new secret to staging. If staging shares
  credentials with prod, you're doing it wrong — staging should have its
  own values.
- It does not ship the backup `.env.prod.bak.*` files anywhere. If the
  host dies, those backups die with it. That is intentional — they hold
  old-but-still-sensitive material. Clean them up periodically:
  ```
  sudo find /opt/voyagent -maxdepth 1 -name '.env.prod.bak.*' -mtime +30 -delete
  ```
