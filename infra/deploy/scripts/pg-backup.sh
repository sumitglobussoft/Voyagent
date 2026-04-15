#!/usr/bin/env bash
#
# pg-backup.sh — nightly Postgres backup for voyagent
#
# Produces a custom-format pg_dump at /opt/voyagent/backups/voyagent-<UTC>.dump
# and retains only the most recent $RETENTION_DAYS dumps.
#
# Requirements on the host:
#   * Postgres 16 native on 127.0.0.1:5432
#   * Master env file at /etc/voyagent/postgres-master.env exporting
#     PGPASSWORD (or VOYAGENT_PG_PASSWORD) for the voyagent role
#   * /opt/voyagent/backups/ writable by the invoking user
#
# Invocation:
#   * Preferred: run via the voyagent-pg-backup.service systemd unit (it reads
#     the env file directly via EnvironmentFile= and runs as root).
#   * Manual: sudo /opt/voyagent/repo/infra/deploy/scripts/pg-backup.sh
#
# Exits non-zero on any failure. Idempotent — safe to run twice back-to-back.

set -euo pipefail

BACKUP_DIR="${VOYAGENT_BACKUP_DIR:-/opt/voyagent/backups}"
ENV_FILE="${VOYAGENT_PG_ENV_FILE:-/etc/voyagent/postgres-master.env}"
DB_NAME="${VOYAGENT_DB_NAME:-voyagent}"
DB_USER="${VOYAGENT_DB_USER:-voyagent}"
DB_HOST="${VOYAGENT_DB_HOST:-127.0.0.1}"
DB_PORT="${VOYAGENT_DB_PORT:-5432}"
RETENTION_DAYS="${VOYAGENT_BACKUP_RETENTION:-30}"

log() {
  printf '[pg-backup] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

if [[ ! -f "$ENV_FILE" ]]; then
  die "env file not found: $ENV_FILE"
fi

# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

# Accept either PGPASSWORD or VOYAGENT_PG_PASSWORD from the env file.
if [[ -z "${PGPASSWORD:-}" && -n "${VOYAGENT_PG_PASSWORD:-}" ]]; then
  export PGPASSWORD="$VOYAGENT_PG_PASSWORD"
fi
if [[ -z "${PGPASSWORD:-}" ]]; then
  die "PGPASSWORD not set after sourcing $ENV_FILE"
fi

mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/voyagent-${TS}.dump"
TMP="${OUT}.partial"

log "starting pg_dump -> $OUT"
if ! pg_dump \
      -h "$DB_HOST" \
      -p "$DB_PORT" \
      -U "$DB_USER" \
      -d "$DB_NAME" \
      -Fc \
      --no-owner \
      --file "$TMP"; then
  rm -f "$TMP"
  die "pg_dump failed"
fi

# Atomic rename so partially written dumps never linger with the final name.
mv -f "$TMP" "$OUT"

SIZE="$(stat -c '%s' "$OUT" 2>/dev/null || wc -c <"$OUT")"
log "dump complete: $OUT ($SIZE bytes)"

# Retention: keep the N most recent dumps, delete the rest.
log "applying retention policy: keep $RETENTION_DAYS most recent dumps"
mapfile -t old < <(
  ls -1t "$BACKUP_DIR"/voyagent-*.dump 2>/dev/null | tail -n +$((RETENTION_DAYS + 1))
)
for f in "${old[@]}"; do
  if [[ -n "$f" && -f "$f" ]]; then
    log "pruning $f"
    rm -f "$f"
  fi
done

log "done"
