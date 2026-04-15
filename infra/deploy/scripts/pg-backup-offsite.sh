#!/usr/bin/env bash
#
# pg-backup-offsite.sh — wraps pg-backup.sh and uploads the freshest local
# dump to an S3-compatible offsite bucket via rclone.
#
# Supported backends (anything rclone supports): AWS S3, Backblaze B2,
# Cloudflare R2, Wasabi, MinIO, DigitalOcean Spaces, Scaleway Object Storage.
# The rclone remote must already be configured on the host (run `rclone config`
# once as root to create the remote named in VOYAGENT_BACKUP_REMOTE).
#
# Opt-in: if /opt/voyagent/.env.offsite-backup is absent, this script exits 0
# without doing anything offsite-related. The local backup still runs.
#
# Required env (in /opt/voyagent/.env.offsite-backup, root:root 0600):
#   VOYAGENT_BACKUP_REMOTE       rclone remote name, e.g. "b2-backups"
#   VOYAGENT_BACKUP_BUCKET       bucket name
# Optional:
#   VOYAGENT_BACKUP_PREFIX              default: voyagent/
#   VOYAGENT_BACKUP_RETENTION_REMOTE    days to keep remote, default: 90
#
# Usage:
#   sudo /opt/voyagent/repo/infra/deploy/scripts/pg-backup-offsite.sh [--dry-run]
#
# Exit codes:
#   0 — success, or opt-in file absent (intentional no-op)
#   1 — misconfiguration or upload failure

set -euo pipefail

OFFSITE_ENV_FILE="${VOYAGENT_OFFSITE_ENV_FILE:-/opt/voyagent/.env.offsite-backup}"
BACKUP_DIR="${VOYAGENT_BACKUP_DIR:-/opt/voyagent/backups}"
LOCAL_BACKUP_SCRIPT="${VOYAGENT_PG_BACKUP_SCRIPT:-/opt/voyagent/repo/infra/deploy/scripts/pg-backup.sh}"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

log() {
  printf '[pg-backup-offsite] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

if [[ ! -f "$OFFSITE_ENV_FILE" ]]; then
  log "opt-in file $OFFSITE_ENV_FILE not found; skipping offsite upload"
  exit 0
fi

# shellcheck disable=SC1090
set -a; . "$OFFSITE_ENV_FILE"; set +a

: "${VOYAGENT_BACKUP_REMOTE:?VOYAGENT_BACKUP_REMOTE not set in $OFFSITE_ENV_FILE}"
: "${VOYAGENT_BACKUP_BUCKET:?VOYAGENT_BACKUP_BUCKET not set in $OFFSITE_ENV_FILE}"
PREFIX="${VOYAGENT_BACKUP_PREFIX:-voyagent/}"
RETENTION_REMOTE="${VOYAGENT_BACKUP_RETENTION_REMOTE:-90}"

REMOTE_PATH="${VOYAGENT_BACKUP_REMOTE}:${VOYAGENT_BACKUP_BUCKET}/${PREFIX}"

if ! command -v rclone >/dev/null 2>&1; then
  die "rclone not installed — see docs/BACKUPS.md"
fi

# 1. Run the local backup first (delegates to the already-shipped script).
if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ -x "$LOCAL_BACKUP_SCRIPT" ]]; then
    log "invoking local backup: $LOCAL_BACKUP_SCRIPT"
    "$LOCAL_BACKUP_SCRIPT"
  else
    die "local backup script not found or not executable: $LOCAL_BACKUP_SCRIPT"
  fi
else
  log "DRY RUN — skipping local pg-backup.sh invocation"
fi

# 2. Pick the newest local dump.
NEWEST="$(ls -1t "$BACKUP_DIR"/voyagent-*.dump 2>/dev/null | head -1 || true)"
if [[ -z "$NEWEST" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY RUN — no local dumps present; would upload nothing"
    exit 0
  fi
  die "no local dumps found in $BACKUP_DIR"
fi

log "newest dump: $NEWEST"
log "remote path: $REMOTE_PATH"

# 3. Upload.
RCLONE_ARGS=( "copy" "$NEWEST" "$REMOTE_PATH" )
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "DRY RUN — rclone ${RCLONE_ARGS[*]} --dry-run"
  rclone "${RCLONE_ARGS[@]}" --dry-run
  log "DRY RUN — retention prune would run: rclone delete $REMOTE_PATH --min-age ${RETENTION_REMOTE}d --dry-run"
  rclone delete "$REMOTE_PATH" --min-age "${RETENTION_REMOTE}d" --dry-run || true
  exit 0
fi

rclone "${RCLONE_ARGS[@]}" --progress

# 4. Remote retention.
log "pruning remote dumps older than ${RETENTION_REMOTE}d"
rclone delete "$REMOTE_PATH" --min-age "${RETENTION_REMOTE}d"

log "uploaded $(basename "$NEWEST") to $REMOTE_PATH"
