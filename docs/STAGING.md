# Staging environment

A near-identical copy of voyagent living at
`staging.voyagent.globusdemos.com`. Use it to validate every deploy before
it touches prod.

## What staging is for

- Rehearsing deploys (`deploy_native.py` against the staging env).
- Smoke-testing migrations on real-ish data (periodically refreshed from a
  prod dump — see "Data refresh" below).
- Holding risky feature flags on while we watch them in a browser.
- Dog-fooding new GDS drivers with sandbox credentials so no prod booking
  accidentally gets a live PNR.

It is **not**:
- A QA environment for long-running campaigns (ephemeral; may be reset).
- A load-test target (same host as prod in the default topology).

## Topology

Two supported shapes:

1. **Co-located** (default, effectively free)
   - Same VM as prod.
   - Separate systemd units (`voyagent-*-staging`), separate Postgres DB
     (`voyagent_staging`), separate nginx vhost, separate ports (+10).
   - Cost: $0 incremental.
   - Tradeoff: a runaway staging process can starve prod. Watch the
     journal when you first roll a big change to staging.

2. **Dedicated VM** (recommended once we're past early access)
   - Second host of the same size.
   - Identical setup steps; just point a different DNS record at it.
   - Cost: whatever the prod VM costs — as of 2026-04 that's ~$20-40/mo
     for the 4 vCPU / 8 GB shape we use.

## Bringing it up

The idempotent bootstrap is `infra/deploy/staging/setup-staging.sh`. It
handles every step it safely can, and explicitly delegates two to you:

| Step | Script | Human |
|---|---|---|
| Prereq check (postgres/redis/nginx/certbot) | yes | |
| Create `voyagent_staging` DB + role | yes | |
| Lay out `/opt/voyagent-staging/` | yes | |
| Clone repo | yes | |
| Seed `.env.staging` with fresh JWT + metrics token | yes | fill in provider keys |
| Install systemd units (enabled, not started) | yes | |
| Install nginx vhost (HTTP-only) | yes | |
| DNS A/AAAA record for `staging.voyagent.globusdemos.com` | | **yes** |
| Run certbot to get the TLS cert | | **yes** |
| First `pnpm install && pnpm -r build` + `uv sync` | | **yes** |
| `alembic upgrade head` | | **yes** |
| Start the services | | **yes** |

Dry-run first:
```
sudo infra/deploy/staging/setup-staging.sh --dry-run
```

## Deploying to staging

Use the same deploy path as prod, but point it at the staging tree:

```
VOYAGENT_ENV=staging \
VOYAGENT_DEPLOY_ROOT=/opt/voyagent-staging \
VOYAGENT_SERVICE_SUFFIX=-staging \
python infra/deploy/ansible/deploy_native.py
```

(The deploy script already honors `VOYAGENT_DEPLOY_ROOT` /
`VOYAGENT_SERVICE_SUFFIX` — if it doesn't on your branch, fall back to
`git pull` + `pnpm -r build` + `systemctl restart voyagent-*-staging` by
hand.)

## Promoting from staging to prod

Staging is a rehearsal, not the source of artefacts. To promote:

1. Merge the green branch to `main` on GitHub.
2. On the prod host, run the normal deploy against the prod tree
   (no `-staging` overrides).
3. Tail `journalctl -u voyagent-api -f` and `curl /health` until green.
4. Close the loop: run the same manual smoke in staging one more time to
   confirm staging is still reachable (sometimes a shared-config change
   breaks it).

## Data refresh

Staging starts empty. To seed it with prod-shaped data:

```
# one-shot, run as root on the host
sudo -u postgres pg_dump -Fc voyagent > /tmp/prod-for-staging.dump
sudo -u postgres pg_restore --clean --if-exists -d voyagent_staging /tmp/prod-for-staging.dump
# scrub PII — staging is not prod
psql -U voyagent_staging -d voyagent_staging -f infra/deploy/staging/scrub.sql   # (add when we have one)
```

Do this sparingly — PII in staging ages badly. Prefer synthetic data from
`infra/deploy/scripts/seed-demo.sh` when a spec doesn't need real records.

## Cost notes

- Co-located: $0.
- Dedicated VM: ~$20-40/month for our standard shape.
- Offsite backups for staging: don't bother. Staging is disposable; losing
  it is a rebuild, not an incident.

## Teardown

```
sudo systemctl disable --now voyagent-api-staging voyagent-web-staging voyagent-marketing-staging
sudo rm /etc/systemd/system/voyagent-*-staging.service
sudo systemctl daemon-reload
sudo rm /etc/nginx/sites-enabled/staging.voyagent.globusdemos.com.conf
sudo rm /etc/nginx/sites-available/staging.voyagent.globusdemos.com.conf
sudo systemctl reload nginx
sudo -u postgres psql -c 'DROP DATABASE voyagent_staging;'
sudo -u postgres psql -c 'DROP ROLE voyagent_staging;'
sudo rm -rf /opt/voyagent-staging /etc/voyagent/staging-postgres.env
```
