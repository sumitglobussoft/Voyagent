# Infra shell tests

Plain-shell (`bash`) tests for the infra scripts under
`infra/deploy/scripts/` and `infra/deploy/systemd/`. No `bats` dependency
— these use `set` + `assert` helpers defined inline.

## Running

From the repo root:

```
bash tests/infra/test_pg_backup_scripts.sh
bash tests/infra/test_verify_secrets.sh
```

Each test script prints a per-assertion `ok`/`FAIL` line and exits non-zero
if any assertion failed. They are intentionally fast (< 2 s each) and safe
to run on a laptop — they do not touch `/opt/voyagent`, systemd, Postgres,
Redis, or the network. They use a fresh `$TMPDIR` under `mktemp -d` and
clean up via `trap EXIT`.

## What they cover

### `test_pg_backup_scripts.sh`

- `pg-backup.sh`, `pg-backup-offsite.sh`, `pg-restore.sh` exist and have a
  bash shebang.
- Both new scripts use `set -euo pipefail`.
- `pg-backup-offsite.sh` is opt-in: exits 0 when the opt-in env file is
  absent.
- `pg-backup-offsite.sh --dry-run` passes `--dry-run` through to rclone
  (verified by intercepting a fake `rclone` on `$PATH`).
- `pg-restore.sh` rejects a wrong confirmation phrase, exits 2 on missing
  argument, exits 2 on missing file.
- The offsite systemd timer schedules after the local backup.

### `test_verify_secrets.sh`

- A well-formed `.env.prod` passes (exit 0).
- A missing required var fails (exit 1).
- `VOYAGENT_AUTH_SECRET=changeme` is caught as a placeholder.
- A too-short `VOYAGENT_AUTH_SECRET` fails length check.
- An empty `VOYAGENT_METRICS_TOKEN` fails.
- A too-short `VOYAGENT_METRICS_TOKEN` fails.
- `VOYAGENT_DB_URL` without a password fails.
- A nonexistent file exits 2.

## CI status

Not wired into CI. CI is currently Python-focused (pytest + ruff + mypy).
These are **manual verification** tests — run them after any change in
`infra/deploy/scripts/` or `infra/deploy/systemd/` before you commit.

If we later want them in CI, the natural home is a new `shell-tests`
GitHub Actions job that runs `bash tests/infra/test_*.sh` on ubuntu-latest.
Don't add a bats dependency — the point is zero-dep.

## Conventions

- Tests must be hermetic: `mktemp -d`, `trap 'rm -rf' EXIT`, no writes
  outside `$TMPDIR`.
- Tests must never call `systemctl`, `psql`, `rclone copy`, or any other
  real side-effecting command. Fake binaries go on `$PATH` when needed.
- Prefer explicit `assert_rc` / `assert` helpers so the output reads like
  a checklist.
