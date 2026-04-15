# Staging environment bootstrap

This directory contains everything needed to bring up a staging copy of
voyagent at `staging.voyagent.globusdemos.com`.

## Files

| File | Purpose |
|---|---|
| `setup-staging.sh` | Idempotent bootstrap script. Run once on a fresh host. |
| `voyagent-staging.nginx.conf` | nginx vhost template (HTTP-only until certbot runs). |
| `systemd-units/voyagent-api-staging.service` | API unit template (port 8020). |
| `systemd-units/voyagent-web-staging.service` | Web unit template (port 3021). |
| `systemd-units/voyagent-marketing-staging.service` | Marketing unit template (port 3022). |

All staging ports are offset from prod by +10:

| Component | Prod | Staging |
|---|---|---|
| API        | 8010 | 8020 |
| Web        | 3011 | 3021 |
| Marketing  | 3012 | 3022 |

## Quick start

Dry run first — shows every action without touching anything:
```
sudo infra/deploy/staging/setup-staging.sh --dry-run
```

Real run:
```
sudo infra/deploy/staging/setup-staging.sh
```

See `docs/STAGING.md` for the full story (promotion flow, cost notes,
deploys).
