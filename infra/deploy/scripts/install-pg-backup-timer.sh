#!/usr/bin/env bash
#
# install-pg-backup-timer.sh — one-shot installer for the voyagent Postgres
# nightly backup timer. Run ONCE per fresh host, as root.
#
#   sudo /opt/voyagent/repo/infra/deploy/scripts/install-pg-backup-timer.sh
#
# What it does:
#   1. Sanity checks that the env file and backup script exist.
#   2. Ensures /opt/voyagent/backups exists and is root-owned.
#   3. Copies the .service and .timer units into /etc/systemd/system/.
#   4. Reloads systemd, enables + starts the timer.
#   5. Prints the timer status so you can verify the next scheduled run.

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "must run as root" >&2
  exit 1
fi

REPO_DIR="${VOYAGENT_REPO_DIR:-/opt/voyagent/repo}"
SRC_SYSTEMD="$REPO_DIR/infra/deploy/systemd"
SRC_SCRIPT="$REPO_DIR/infra/deploy/scripts/pg-backup.sh"
ENV_FILE="/etc/voyagent/postgres-master.env"
BACKUP_DIR="/opt/voyagent/backups"

echo "[install] sanity checks"
[[ -f "$ENV_FILE"   ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
[[ -f "$SRC_SCRIPT" ]] || { echo "missing $SRC_SCRIPT" >&2; exit 1; }
[[ -f "$SRC_SYSTEMD/voyagent-pg-backup.service" ]] || { echo "missing service unit" >&2; exit 1; }
[[ -f "$SRC_SYSTEMD/voyagent-pg-backup.timer"   ]] || { echo "missing timer unit"   >&2; exit 1; }

echo "[install] ensuring $BACKUP_DIR exists"
install -d -o root -g root -m 0750 "$BACKUP_DIR"

echo "[install] marking $SRC_SCRIPT executable"
chmod 0750 "$SRC_SCRIPT"

echo "[install] copying unit files to /etc/systemd/system"
install -m 0644 "$SRC_SYSTEMD/voyagent-pg-backup.service" /etc/systemd/system/voyagent-pg-backup.service
install -m 0644 "$SRC_SYSTEMD/voyagent-pg-backup.timer"   /etc/systemd/system/voyagent-pg-backup.timer

echo "[install] reloading systemd"
systemctl daemon-reload

echo "[install] enabling + starting timer"
systemctl enable --now voyagent-pg-backup.timer

echo "[install] timer status:"
systemctl status --no-pager voyagent-pg-backup.timer || true

echo
echo "[install] done. Trigger a manual dry-run with:"
echo "           sudo systemctl start voyagent-pg-backup.service"
echo "           journalctl -u voyagent-pg-backup.service -n 100 --no-pager"
