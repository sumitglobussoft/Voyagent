# Voyagent deployment

Single-host Docker Compose stack for **voyagent.globusdemos.com**
(`163.227.174.141`). Designed to coexist with the other apps already
running on that box by exposing **exactly one** high host port
(`${VOYAGENT_EDGE_PORT}`, default `8480`). The machine's existing
nginx reverse-proxies the subdomain into that port and owns TLS.

---

## Stack layout

| Service          | Image                                  | Network-only port | Role                                   |
|------------------|----------------------------------------|-------------------|----------------------------------------|
| `nginx`          | `nginx:1.27-alpine`                    | 80 (pub: 8480)    | Inner edge; routes `/`, `/app`, `/api` |
| `marketing`      | built from `Dockerfile.marketing`      | 3000              | Public site (Next.js)                  |
| `web`            | built from `Dockerfile.web`            | 3001              | Authenticated app (Next.js)            |
| `api`            | built from `Dockerfile.api`            | 8000              | FastAPI + in-process agent runtime     |
| `postgres`       | `postgres:16.4-bookworm`               | 5432 (internal)   | Relational store                       |
| `redis`          | `redis:7.4-alpine`                     | 6379 (internal)   | Offer cache + pub/sub                  |
| `alembic`        | reuses API image                       | —                 | One-shot migration runner (profile)    |
| `worker`         | built from `Dockerfile.worker`         | —                 | Temporal worker (profile `future`)     |
| `browser_runner` | built from `Dockerfile.browser_runner` | —                 | Playwright tasks (profile `portals`)   |
| `temporal`       | `temporalio/auto-setup:1.25`           | —                 | Temporal server (profile `future`)     |

Only `nginx` publishes a host port. Everything else is on the private
`voyagent_net` bridge.

## Port map (host → container)

```
host :443          -> host nginx   (existing, not ours)
host :80           -> host nginx   (existing; HTTP->HTTPS redirect)
host :8480         -> voyagent_nginx:80          (this stack)
(internal)         -> voyagent_nginx -> marketing:3000 / web:3001 / api:8000
```

The stack touches **no other host ports**. No `0.0.0.0` bindings on 80,
443, 3000, 3001, 5432, 6379, 8000, 8088, 8080, or anything else.

---

## First-time host bootstrap

```bash
# 1. SSH in as a sudo-capable user.
ssh empcloud-development@voyagent.globusdemos.com

# 2. Drop the repo (or at least infra/deploy/) onto the box at /opt/voyagent/repo.
#    `scp -r` from your dev machine, `git clone`, or let the Ansible playbook
#    do it — see infra/deploy/ansible/.

# 3. Run bootstrap once (installs Docker, creates the voyagent user + dirs).
sudo bash /opt/voyagent/repo/infra/deploy/scripts/bootstrap.sh
```

`bootstrap.sh` is idempotent: re-running it is safe.

## Preparing `.env.prod`

```bash
sudo -u voyagent cp /opt/voyagent/repo/infra/deploy/.env.prod.example \
                    /opt/voyagent/.env.prod
sudo chmod 600 /opt/voyagent/.env.prod
sudo -u voyagent $EDITOR /opt/voyagent/.env.prod
```

You **must** fill in:

- `POSTGRES_PASSWORD` — a strong random string.
- `VOYAGENT_KMS_KEY` — generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- Any provider credentials you actually want live (Anthropic, Clerk,
  Amadeus, Tally, etc.). Anything left blank simply disables that
  integration.

`deploy.sh` rejects the file if `change-me` survives in a required key.

## Deploy flow

```bash
# As the `voyagent` user.
sudo -u voyagent bash /opt/voyagent/repo/infra/deploy/scripts/deploy.sh
```

What happens, in order:

1. `git pull` (skip with `--no-pull`).
2. `.env.prod` is validated — required keys present, no placeholders.
3. `VOYAGENT_VERSION` is set to the short git SHA.
4. `docker compose build --pull` on the production compose file.
5. `docker compose --profile migrate run --rm alembic alembic upgrade head`
   (skip with `--no-migrate`).
6. `docker compose up -d --remove-orphans`.
7. Poll `http://127.0.0.1:${VOYAGENT_EDGE_PORT}/health` for up to 120s.
8. Append a line to `/opt/voyagent/deploy-history.log`.
9. Print a one-line `OK version=… edge=…` summary.

A non-zero exit means **something did not come up** — inspect
`docker compose -f infra/deploy/compose.prod.yml logs` immediately.

## DNS + TLS

- **DNS:** `voyagent.globusdemos.com` → `A 163.227.174.141`. Create at
  the zone registrar; no wildcard needed.
- **TLS:** managed by the existing certbot install on the host. Run
  once:
  ```bash
  sudo certbot --nginx -d voyagent.globusdemos.com
  ```
  Then install `infra/deploy/nginx-host/voyagent.globusdemos.com.conf`
  per the header comment in that file. The inner compose nginx never
  sees TLS — it trusts `X-Forwarded-Proto` from the outer edge.

## Routing at the outer edge

```
/              -> inner nginx -> marketing:3000
/app, /app/*   -> inner nginx -> web:3001        (Next.js basePath=/app)
/api, /api/*   -> inner nginx -> api:8000        (SSE, CORS, auth)
/_next/*       -> inner nginx -> web (Next.js chunks)
/health        -> inner nginx -> api:8000/health
```

SSE survives end-to-end because both nginx layers set
`proxy_buffering off` and `proxy_http_version 1.1` on `/api/`.

## Rollback

```bash
sudo -u voyagent bash /opt/voyagent/repo/infra/deploy/scripts/rollback.sh           # previous
sudo -u voyagent bash /opt/voyagent/repo/infra/deploy/scripts/rollback.sh <sha>     # explicit
```

The script reads `/opt/voyagent/deploy-history.log`, confirms the
target image exists locally, and `docker compose up -d` with
`VOYAGENT_VERSION` pinned to that tag. If the images were pruned, you
must rebuild from the matching commit first.

## Logs

```bash
cd /opt/voyagent/repo
docker compose -f infra/deploy/compose.prod.yml logs -f api
docker compose -f infra/deploy/compose.prod.yml logs -f web marketing nginx

# Host-level
journalctl -u nginx -f                       # outer edge access/error
less /opt/voyagent/deploy-history.log        # deploy audit trail
```

## Scaling worker / browser_runner later

Both services ship with profiles so they stay dormant:

```bash
# Turn on the Temporal worker (requires Temporal server, too).
sudo -u voyagent bash .../deploy.sh --with future

# Turn on the Playwright browser runner.
sudo -u voyagent bash .../deploy.sh --with portals
```

Replace the placeholder worker CMD in `Dockerfile.worker` with a real
entrypoint before relying on it in production.

## Running tests on the host

Every test suite in the repo can be executed on the server using only
Docker — no host-level Python or Node install is required. A single
throw-away image per language runs to completion and writes structured
reports to `/opt/voyagent/test-results/`.

### Suites

| Suite     | What it proves                                                                   | Network   |
|-----------|----------------------------------------------------------------------------------|-----------|
| `py-unit` | Pydantic canonical model, drivers (Amadeus/Tally/BSP/VFS), agent runtime, FastAPI chat surface (stubbed), Postgres storage, browser_runner unit tests. | none      |
| `py-live` | Live HTTP integration tests against the running edge (`tests/live/**`).          | voyagent_net |
| `e2e`     | Playwright end-to-end tests (`tests/e2e/**`).                                    | voyagent_net |

`py-live` and `e2e` attach to the existing `voyagent_net` bridge as
an **external** network reference — the prod stack (compose.prod.yml)
owns that network's lifecycle. Both suites default
`VOYAGENT_BASE_URL=http://nginx:80`, which is the in-network edge,
so tests avoid Cloudflare-fronted public flakes. If the prod stack
isn't running, `run-tests-on-server.sh` fails fast with a message
telling you to run `deploy.sh` first.

### One-command usage

```bash
sudo -u voyagent bash /opt/voyagent/repo/infra/deploy/scripts/run-tests-on-server.sh
```

This:

1. Verifies `voyagent_nginx` is running.
2. Builds `voyagent-tests-py` and `voyagent-tests-e2e` images.
3. Runs `py-unit`, then `py-live`, then `e2e` in sequence.
4. Snapshots every suite's reports into
   `/opt/voyagent/test-results/<UTC-stamp>/{py-unit,py-live,e2e}/`.
5. Prints a summary table and exits with the worst suite's exit code.

### Running a single suite

```bash
sudo -u voyagent bash .../run-tests-on-server.sh --only py-unit
sudo -u voyagent bash .../run-tests-on-server.sh --only py-live
sudo -u voyagent bash .../run-tests-on-server.sh --only e2e

# Retry without rebuilding images:
sudo -u voyagent bash .../run-tests-on-server.sh --only e2e --no-build

# Point live + e2e at the public URL instead of the in-network edge:
sudo -u voyagent bash .../run-tests-on-server.sh --base-url https://voyagent.globusdemos.com

# Prune stamped result dirs older than 7 days:
sudo -u voyagent bash .../run-tests-on-server.sh --prune
```

### Where reports land

```
/opt/voyagent/test-results/
├── py-unit/                 # latest run (compose bind mount)
│   ├── junit.xml
│   └── report.json
├── py-live/                 # latest run
│   ├── junit.xml
│   └── report.json
├── e2e/                     # latest run
│   ├── playwright-report/   # Playwright HTML (open index.html)
│   └── test-results/
│       └── junit.xml
└── 20260414T103000Z/        # one stamped snapshot per run
    ├── py-unit/{junit.xml,report.json}
    ├── py-live/{junit.xml,report.json}
    └── e2e/{playwright-report,test-results}
```

Copy reports off the box with plain `scp`:

```bash
scp -r empcloud-development@voyagent.globusdemos.com:/opt/voyagent/test-results/20260414T103000Z ./
```

### Baseline expectation (live + e2e)

Until real `ANTHROPIC_API_KEY` and `CLERK_SECRET_KEY` land in
`/opt/voyagent/.env.prod`, the `tests/live` and `tests/e2e` suites pin
the **error contract**: the chat surface must return `401`/`403`/`503`
(depending on which secret is missing), **not** a successful turn. This
is intentional. The tests still pass under that contract — they're
proving the stack fails *correctly*. Once real keys are wired in, the
same suites flip to asserting a successful conversational turn without
any test-code changes.

## Known limitations

- **Single host, no HA.** A box reboot == downtime until Docker comes
  back. No leader election, no redundant Postgres.
- **No blue/green.** Deploy is rolling via `docker compose up -d`;
  expect a few-second gap per service on restart.
- **No image registry.** Images are built on the box from source.
  Rollback requires the previous image to still be on disk.
- **No secret rotation automation.** Rotating `VOYAGENT_KMS_KEY` or
  provider creds is a manual `sed` + redeploy.
- **Docker-in-Docker unsupported.** The browser runner runs Chromium
  inside its container; do not nest.
- **Backups not wired here.** `postgres:16` data lives in the named
  volume `voyagent_pg_data`; operator is responsible for
  `pg_dump`/snapshot cadence.
