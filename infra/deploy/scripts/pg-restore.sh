#!/usr/bin/env bash
#
# pg-restore.sh — restore the voyagent DB from a named pg_dump file.
#
# DESTRUCTIVE: drops and recreates the voyagent database. Stops the voyagent
# API/web/worker services before the restore and starts them back up after.
# Requires confirmation via an exact phrase — there is intentionally no -y
# / --force flag in v0.
#
# Usage:
#   sudo ./pg-restore.sh /opt/voyagent/backups/voyagent-20260415T030000Z.dump
#
# Env overrides (same semantics as pg-backup.sh):
#   VOYAGENT_PG_ENV_FILE   default /etc/voyagent/postgres-master.env
#   VOYAGENT_DB_NAME       default voyagent
#   VOYAGENT_DB_USER       default voyagent
#   VOYAGENT_DB_HOST       default 127.0.0.1
#   VOYAGENT_DB_PORT       default 5432
#   VOYAGENT_RESTORE_SERVICES  space-separated list of services to stop/start
#                              default: voyagent-api voyagent-web voyagent-marketing voyagent-worker

set -euo pipefail

DUMP_PATH="${1:-}"
if [[ -z "$DUMP_PATH" ]]; then
  echo "usage: $0 <path-to-dump>" >&2
  exit 2
fi

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "pg-restore: dump file not found: $DUMP_PATH" >&2
  exit 2
fi

ENV_FILE="${VOYAGENT_PG_ENV_FILE:-/etc/voyagent/postgres-master.env}"
DB_NAME="${VOYAGENT_DB_NAME:-voyagent}"
DB_USER="${VOYAGENT_DB_USER:-voyagent}"
DB_HOST="${VOYAGENT_DB_HOST:-127.0.0.1}"
DB_PORT="${VOYAGENT_DB_PORT:-5432}"
SERVICES="${VOYAGENT_RESTORE_SERVICES:-voyagent-api voyagent-web voyagent-marketing voyagent-worker}"

log() {
  printf '[pg-restore] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}
die() {
  log "ERROR: $*" >&2
  exit 1
}

cat >&2 <<EOF
================================================================
  VOYAGENT DATABASE RESTORE
  dump:   $DUMP_PATH
  target: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}
  This will DROP and RECREATE the target database.
  All voyagent app services will be stopped during the restore.
================================================================
EOF

printf 'Type "RESTORE VOYAGENT" to continue: ' >&2
read -r CONFIRM
if [[ "$CONFIRM" != "RESTORE VOYAGENT" ]]; then
  die "confirmation phrase not matched; aborting"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  die "env file not found: $ENV_FILE"
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
if [[ -z "${PGPASSWORD:-}" && -n "${VOYAGENT_PG_PASSWORD:-}" ]]; then
  export PGPASSWORD="$VOYAGENT_PG_PASSWORD"
fi
[[ -n "${PGPASSWORD:-}" ]] || die "PGPASSWORD not set after sourcing $ENV_FILE"

STOPPED=()
for svc in $SERVICES; do
  if systemctl is-active --quiet "$svc"; then
    log "stopping $svc"
    systemctl stop "$svc"
    STOPPED+=( "$svc" )
  fi
done

cleanup() {
  for svc in "${STOPPED[@]}"; do
    log "starting $svc"
    systemctl start "$svc" || log "WARN: failed to start $svc"
  done
}
trap cleanup EXIT

log "dropping + recreating $DB_NAME"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS ${DB_NAME};
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
SQL

log "restoring dump via pg_restore"
pg_restore \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --no-owner \
  --clean --if-exists \
  "$DUMP_PATH"

log "restore complete"
log "NEXT: verify via curl https://voyagent.globusdemos.com/health and a test sign-in"
