# Voyagent deployment runbook

This is the committed, in-repo runbook for deploying and operating
voyagent on the native live host. On-call and future engineers: read
this before touching production. It mirrors `memory/deployment_runbook.md`
from the session memory but lives in git so it survives machine wipes.

## 1. Live host

- **Public host:** `voyagent.globusdemos.com` (Cloudflare-fronted)
- **Origin IP:** `163.227.174.141` — SSH MUST use this IP, not the
  hostname. Cloudflare does not proxy port 22, so `ssh
  voyagent.globusdemos.com` times out.
- **SSH user:** `empcloud-development`. Password stored locally as
  `VOYAGENT_DEPLOY_PASSWORD` in `local.env` (never committed).
- **Repo on server:** `/opt/voyagent/repo` (git checkout of
  `origin/main`).
- **Secrets on server:**
  - `/opt/voyagent/.env.prod` — app env (root:adm 0640). JWT signing
    secret, DB URL, Redis URL, etc.
  - `/etc/voyagent/postgres-master.env` — Postgres superuser password
    (root:adm 0640). Used by `pg-backup.sh` and by ad-hoc admin ops.
  - `/etc/redis/redis.conf` — Redis `requirepass`.
- **Logs:** `/opt/voyagent/logs/{api,web,marketing}.log` plus
  `journalctl -u voyagent-*` and `/var/log/nginx/`.
- **Backups:** `/opt/voyagent/backups/voyagent-*.dump` (custom-format
  pg_dump). **Local to the host only — no off-site copy yet. See
  section 9.**

## 2. Service topology

All native, no Docker. Four systemd-managed services plus two
native dependencies:

| Service               | Port        | Unit                        | Runs                                |
|-----------------------|-------------|-----------------------------|-------------------------------------|
| voyagent-api          | 127.0.0.1:8010 | voyagent-api.service       | uvicorn serving services/api        |
| voyagent-web          | 127.0.0.1:3011 | voyagent-web.service       | `next start -H 127.0.0.1 -p 3011`   |
| voyagent-marketing    | 127.0.0.1:3012 | voyagent-marketing.service | `next start -H 127.0.0.1 -p 3012`   |
| postgresql@16-main    | 127.0.0.1:5432 | postgresql@16-main.service | Postgres 16, DB + role `voyagent`   |
| redis-server          | 127.0.0.1:6379 | redis-server.service       | Redis 7, `requirepass`, voyagent uses DB index 3 |

Nginx fronts all three HTTP services at `/`, `/app`, `/api`. Certbot
handles TLS renewal. Wrappers for the app services live at
`/opt/voyagent/bin/voyagent-{api,web,marketing}` and are called from
unit files in `/etc/systemd/system/voyagent-*.service`.

Node is installed via nvm at
`/home/empcloud-development/.nvm/versions/node/v24.14.0`. pnpm is
activated via corepack against that node. Python is system 3.12 plus
`uv` at `~/.local/bin/uv`. The shared Python venv is at
`/opt/voyagent/repo/.venv` and is created by
`uv sync --package voyagent-api`.

## 3. Restart procedure

```bash
sudo systemctl restart voyagent-api voyagent-web voyagent-marketing
sleep 3
systemctl is-active voyagent-api voyagent-web voyagent-marketing
# Expect three "active" lines.

# Loopback probes:
curl -sS http://127.0.0.1:8010/health
curl -sSI http://127.0.0.1:3011/   # web
curl -sSI http://127.0.0.1:3012/   # marketing
```

If any service is not `active`, check `journalctl -u voyagent-<name>
-n 200 --no-pager` and the per-service log in `/opt/voyagent/logs/`.

## 4. Deploy procedure

Standard cadence, driven by `deploy_native.py` from a dev machine.
The script SSHes to the origin IP and runs the steps below. Run them
by hand if the script is unavailable.

1. **Local prep:** commit + push to `origin/main`.

2. **SSH to origin IP** (NOT hostname — Cloudflare blocks port 22).
   Prefer paramiko with password auth from `local.env`. Wrap
   Windows-side runners with `PYTHONIOENCODING=utf-8` to avoid
   cp1252 stdout crashes on unicode output.

3. **Pull:**
   ```bash
   cd /opt/voyagent/repo
   git fetch origin
   git reset --hard origin/main
   ```
   Do NOT `git pull` — avoid merge-conflict surprises on the server.

4. **Python deps:**
   ```bash
   uv sync --package voyagent-api
   ```
   Critical — plain `uv sync` only installs root dev-deps and misses
   voyagent-api runtime deps. This WILL bite you if you forget the
   `--package` flag.

5. **Node deps + builds (in order):**
   ```bash
   pnpm install --no-frozen-lockfile              # no lockfile committed
   pnpm -r --filter "./packages/*" build          # MUST build packages first
   NEXT_TELEMETRY_DISABLED=1 pnpm --filter @voyagent/marketing build
   NEXT_TELEMETRY_DISABLED=1 pnpm --filter @voyagent/web build
   ```
   Packages (`icons`, `ui`, `core`, `sdk`, `chat`) are tsc-compiled
   and apps import from their `dist/`. If marketing build fails with
   `Can't resolve '@voyagent/icons'`, you skipped the packages
   build.

6. **Migrations (always from repo root, NEVER from `infra/`):**
   ```bash
   set -a; . /opt/voyagent/.env.prod; set +a
   cd /opt/voyagent/repo
   .venv/bin/alembic -c infra/alembic/alembic.ini upgrade head
   ```
   `script_location = infra/alembic` is relative, so running from
   `infra/` breaks with `No 'script_location' key found`.

7. **Restart services:** see section 3.

8. **Verify public endpoints:**
   ```bash
   curl -sSI https://voyagent.globusdemos.com/app/sign-up | grep -iE '^(http|x-clerk)'
   curl -sS   https://voyagent.globusdemos.com/health
   curl -sS   https://voyagent.globusdemos.com/api/auth/me
   ```
   Expect: 200 with **zero** `x-clerk-*` headers, `{"status":"ok"}`,
   and `{"detail":"unauthorized"}`. Any `x-clerk-*` header means
   the old Clerk-wired build is still live — the rebuild did not
   take.

9. **E2E smoke (5 seconds):** sign up with `@mailinator.com` (NOT
   `@voyagent.test` — `.test` is RFC 2606 reserved and
   email-validator rejects it), confirm 201 + access_token, GET /me
   with the token → 200, sign-in with wrong password → 401.

## 5. Common gotchas

One-liners with the fix pattern. Detail lives in
`memory/session_learnings_2026_04_14.md` and
`memory/session_learnings_2026_04_15.md`.

1. **`uv sync` installs nothing useful.** Root pyproject has no
   runtime deps. Always `uv sync --package voyagent-api`.
2. **Packages must build before apps.** `pnpm -r --filter
   "./packages/*" build` before any app build.
3. **Alembic must run from repo root.** `script_location =
   infra/alembic` is a relative path.
4. **`cookies()` is async in Next.js 15.** `const jar = await
   cookies();` everywhere. Same for `searchParams` in page
   components.
5. **`basePath` strips the prefix inside middleware.** `pathname`
   is already `/chat`, not `/app/chat`. A naive
   `pathname.startsWith("/app")` mis-matches `/approvals`. Use
   exact-prefix checks.
6. **`basePath` does NOT rewrite `<form action>`.** `<Link>` and
   `redirect()` auto-prepend the prefix; HTML forms do not. Keep
   the full prefix in form actions.
7. **`/app` bare path cannot 308 to `/app/`** under Next 15
   basePath — `trailingSlash: false` normalizes it back and you get
   an infinite loop. Proxy `/app` directly to upstream.
8. **`req.url` behind nginx leaks `127.0.0.1:3011`.** Reconstruct
   the public origin from `X-Forwarded-Host` + `X-Forwarded-Proto`
   when building redirect URLs.
9. **nginx `proxy_set_header` inheritance trap.** Defining ANY
   `proxy_set_header` in a `location` discards ALL parent headers.
   Re-declare the full Host / X-Forwarded-* / Upgrade / Connection
   set inside every location that needs any of them.
10. **TWO nginx configs in the repo, only ONE is live.**
    `infra/deploy/nginx-host/voyagent.globusdemos.com.conf` is the
    live host vhost. `infra/deploy/nginx/voyagent.conf` is the dead
    docker-era inner nginx. Always verify which file before editing.
11. **SDK consumers must add `/api` to `baseUrl`.** Nginx strips
    `/api/` before proxying, so SDK paths are bare (`/chat/sessions`,
    `/health`). Consumers pass `https://host/api` as `baseUrl`.
    FastAPI routers use plain prefixes (`/auth`, `/chat`) — NEVER
    include `/api/` in a router prefix.
12. **`route.ts` / `page.tsx` reject non-route exports.** Next 15
    allowlists `default`, `metadata`, `GET`/`POST`/..., `runtime`,
    `revalidate`, `generateStaticParams`. Move test hooks to a
    sibling `_helpers.ts`.
13. **MDX 3 parses `<https://...>` as a JSX tag.** Use
    `[text](url)` or backticks. Same for `D<N>`-style angle
    brackets.
14. **Tailwind is a runtime dep for Next builds.** Missing it on
    a fresh host surfaces as a cryptic PostCSS error.
15. **`aiosqlite + StaticPool + TestClient` race.** Intermittent
    `no such table` mid-test. Fix by switching fixtures to
    `tmp_path` file SQLite.
16. **`email-validator` rejects `.test`, `.example`,
    `.invalid`, `.localhost`.** Use `@mailinator.com` for smoke
    tests.
17. **`pg_hba.conf` uses `peer` auth for local.** Admin ops go
    through `sudo -u postgres psql`, not password auth.

## 6. Database backup and restore

### Automated backups

A systemd timer (`voyagent-pg-backup.timer`) runs
`infra/deploy/scripts/pg-backup.sh` every day at 02:00 UTC. Each
run writes
`/opt/voyagent/backups/voyagent-<UTC-timestamp>.dump` (custom-format
pg_dump) and prunes dumps older than the 30 most recent. Retention
is controlled by `VOYAGENT_BACKUP_RETENTION` if you need to override
it.

**One-time install on a fresh host:**
```bash
sudo /opt/voyagent/repo/infra/deploy/scripts/install-pg-backup-timer.sh
sudo systemctl list-timers voyagent-pg-backup.timer
```

**Manual run (same path the timer uses):**
```bash
sudo systemctl start voyagent-pg-backup.service
journalctl -u voyagent-pg-backup.service -n 100 --no-pager
```

**Direct invocation of the script (debugging):**
```bash
sudo /opt/voyagent/repo/infra/deploy/scripts/pg-backup.sh
ls -lh /opt/voyagent/backups/
```

### Restore

```bash
# 1. Stop the app so nothing is writing during restore.
sudo systemctl stop voyagent-api

# 2. Drop + recreate the database.
sudo -u postgres dropdb voyagent
sudo -u postgres createdb -O voyagent voyagent

# 3. Restore the custom-format dump.
sudo -u postgres pg_restore \
  --no-owner \
  --role=voyagent \
  -d voyagent \
  /opt/voyagent/backups/voyagent-<timestamp>.dump

# 4. Verify.
sudo -u postgres psql -d voyagent -c "\dt"
sudo -u postgres psql -d voyagent -c "SELECT count(*) FROM users;"

# 5. Bring the app back.
sudo systemctl start voyagent-api
curl -sS http://127.0.0.1:8010/health
```

## 7. Secret rotation

All secrets live in three places. When you rotate one, update the
file, restart the service, and verify with a smoke call.

| Secret              | File                                | Consumers                    |
|---------------------|-------------------------------------|------------------------------|
| JWT signing secret  | `/opt/voyagent/.env.prod` (`JWT_SECRET`) | voyagent-api                 |
| Postgres password   | `/etc/voyagent/postgres-master.env` AND `/opt/voyagent/.env.prod` (`DATABASE_URL`) | voyagent-api, pg-backup      |
| Redis password      | `/etc/redis/redis.conf` (`requirepass`) AND `/opt/voyagent/.env.prod` (`REDIS_URL`) | voyagent-api, redis-server   |

### JWT secret

1. Generate: `openssl rand -hex 64`.
2. Edit `/opt/voyagent/.env.prod`, replace `JWT_SECRET`.
3. `sudo systemctl restart voyagent-api`.
4. Smoke: sign in fresh, confirm 200. **All existing sessions are
   invalidated** — expected.

### Postgres password

1. Generate new password.
2. `sudo -u postgres psql -c "ALTER ROLE voyagent WITH PASSWORD '<new>';"`.
3. Update `PGPASSWORD` in `/etc/voyagent/postgres-master.env` and
   `DATABASE_URL` in `/opt/voyagent/.env.prod`.
4. `sudo systemctl restart voyagent-api`.
5. Trigger a manual backup to confirm the new password works:
   `sudo systemctl start voyagent-pg-backup.service`.

### Redis password

1. Generate new password.
2. Edit `requirepass` in `/etc/redis/redis.conf`.
3. Update `REDIS_URL` in `/opt/voyagent/.env.prod`.
4. `sudo systemctl restart redis-server voyagent-api`.

### If a secret is exposed

Rotate IMMEDIATELY using the procedure above. Then:
- Grep the git history for the exposed value: `git log -p -S'<value>'`.
- If it ever appeared in a commit, rewrite history (`git filter-repo`)
  and force-push — but only with explicit sign-off from the owner.
- Revoke any third-party credentials that shared the same secret.
- File an incident note in `docs/INCIDENTS.md` (create if absent).

## 8. Rollback

Not graceful, but it works:

```bash
cd /opt/voyagent/repo
git fetch origin
git reset --hard <previous-good-sha>
# Re-run deploy steps 4-7 from section 4.
```

If the bad release ran a forward-only migration, you will also need
to restore the latest pre-deploy dump using the procedure in
section 6. **There is no Docker rollback option** — the docker
images were deleted during the native migration.

## 9. Logs

| What              | Where                                              |
|-------------------|----------------------------------------------------|
| voyagent-api      | `/opt/voyagent/logs/api.log`, `journalctl -u voyagent-api` |
| voyagent-web      | `/opt/voyagent/logs/web.log`, `journalctl -u voyagent-web` |
| voyagent-marketing| `/opt/voyagent/logs/marketing.log`, `journalctl -u voyagent-marketing` |
| pg-backup         | `journalctl -u voyagent-pg-backup.service`         |
| Postgres          | `journalctl -u postgresql@16-main`, `/var/log/postgresql/` |
| Redis             | `journalctl -u redis-server`                       |
| nginx             | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |

## 10. On-call triage (site is down)

Run these in order. Stop at the first failure — that is your bug.

1. **Host reachable?**
   `ssh empcloud-development@163.227.174.141 'uptime'`.
   If this fails, the problem is the host itself (provider console,
   reboot, disk full, etc.).

2. **systemd services up?**
   `systemctl is-active voyagent-api voyagent-web voyagent-marketing postgresql@16-main redis-server nginx`.
   Any `inactive` or `failed` — check `journalctl -u <name> -n 200`.

3. **nginx healthy?**
   `sudo nginx -t && curl -sSI https://voyagent.globusdemos.com/health`.
   If nginx is ok but TLS is broken, check `certbot certificates`.

4. **Postgres reachable from the app user?**
   `sudo -u postgres psql -d voyagent -c 'SELECT 1;'`.
   If this hangs, check disk space (`df -h`), connection count
   (`SELECT count(*) FROM pg_stat_activity;`), and replication
   lag (not relevant today, one instance).

5. **Redis reachable?**
   `redis-cli -a "$(grep ^requirepass /etc/redis/redis.conf | awk '{print $2}')" ping`.
   Expect `PONG`.

If all five pass and the site is still broken, the problem is
almost certainly in the latest deploy. Roll back (section 8) and
investigate from a known-good state.

## 11. Known follow-ups

- **Off-site backups.** Today every dump lives on the single live
  host. A disk failure loses everything. Pick an S3 / B2 / managed
  pgBackRest target and pipe the nightly dump into it. Until then,
  plan for the possibility of data loss.
- **No staging environment.** Every deploy goes straight to prod.
- **No synthetic monitoring.** The Playwright CI job is the closest
  thing today; add a real uptime probe (Cloudflare health check or
  equivalent) so alerts fire without a human running CI.
