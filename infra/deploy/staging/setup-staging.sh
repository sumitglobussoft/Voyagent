#!/usr/bin/env bash
#
# setup-staging.sh — idempotent bootstrap for staging.voyagent.globusdemos.com
#
# A human runs this once on a fresh (or existing) VM to bring up the staging
# copy of voyagent. Safe to re-run: each step checks its own preconditions.
#
# What this script DOES:
#   1. Checks prerequisites (postgresql@16, redis, nginx, certbot)
#   2. Creates the staging DB + role with a fresh random password
#   3. Lays out /opt/voyagent-staging/{repo,backups,logs}
#   4. Clones the repo (if not already cloned)
#   5. Seeds /opt/voyagent-staging/.env.staging from .env.prod.example
#   6. Installs the staging systemd units (disabled + not started)
#   7. Installs the staging nginx vhost (HTTP-only until certbot runs)
#   8. Prints the remaining manual steps
#
# What this script does NOT do (on purpose):
#   * Run certbot — needs a real DNS record + live port 80. Printed at the end.
#   * Start the app services — you must edit .env.staging first to add your
#     Anthropic key / Sentry DSN / whatever else is env-specific.
#   * Touch anything under the prod tree (/opt/voyagent).
#
# Flags:
#   --dry-run    print every action but make no changes

set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

STAGING_ROOT="/opt/voyagent-staging"
STAGING_REPO="${STAGING_ROOT}/repo"
STAGING_ENV="${STAGING_ROOT}/.env.staging"
STAGING_PG_ENV="/etc/voyagent/staging-postgres.env"
STAGING_DB="voyagent_staging"
STAGING_ROLE="voyagent_staging"
STAGING_HOST="staging.voyagent.globusdemos.com"
REPO_URL="${VOYAGENT_REPO_URL:-https://github.com/voyagent/gbs-agentic-travel.git}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNITS_DIR="${SCRIPT_DIR}/systemd-units"
NGINX_TEMPLATE="${SCRIPT_DIR}/voyagent-staging.nginx.conf"

log()  { printf '[setup-staging] %s\n' "$*"; }
step() { printf '\n[setup-staging] === %s ===\n' "$*"; }
run()  {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '    DRY: %s\n' "$*"
  else
    eval "$@"
  fi
}

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "this script must be run as root (sudo)" >&2
    exit 1
  fi
}

require_cmd() {
  local name="$1" pkg="${2:-$1}"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "missing prerequisite: $name (install with: apt-get install -y $pkg)" >&2
    exit 1
  fi
}

if [[ "$DRY_RUN" -eq 0 ]]; then
  require_root
fi

step "1. prerequisites"
require_cmd psql       postgresql-client
require_cmd redis-cli  redis-tools
require_cmd nginx      nginx
require_cmd certbot    certbot
require_cmd git        git
require_cmd python3    python3
log "all prerequisite binaries present"

step "2. staging database"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${STAGING_ROLE}'" 2>/dev/null | grep -q 1; then
  log "role ${STAGING_ROLE} already exists — leaving alone"
else
  STAGING_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  run "sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE ${STAGING_ROLE} WITH LOGIN PASSWORD '${STAGING_PASS}';
CREATE DATABASE ${STAGING_DB} OWNER ${STAGING_ROLE};
SQL"
  run "install -d -m 0750 -o root -g adm /etc/voyagent"
  run "install -m 0640 -o root -g adm /dev/null ${STAGING_PG_ENV}"
  run "printf 'PGPASSWORD=%s\nVOYAGENT_PG_PASSWORD=%s\n' '${STAGING_PASS}' '${STAGING_PASS}' > ${STAGING_PG_ENV}"
  log "created staging DB + role; credentials in ${STAGING_PG_ENV}"
fi

step "3. directory layout"
run "install -d -m 0755 ${STAGING_ROOT}"
run "install -d -m 0755 ${STAGING_ROOT}/backups"
run "install -d -m 0755 ${STAGING_ROOT}/logs"

step "4. repo clone"
if [[ -d "${STAGING_REPO}/.git" ]]; then
  log "repo already cloned at ${STAGING_REPO}"
else
  run "git clone ${REPO_URL} ${STAGING_REPO}"
fi

step "5. staging env file"
if [[ -f "${STAGING_ENV}" ]]; then
  log "${STAGING_ENV} already exists — not overwriting"
else
  EXAMPLE="${STAGING_REPO}/.env.prod.example"
  if [[ ! -f "$EXAMPLE" ]]; then
    log "WARN: ${EXAMPLE} not found; creating a stub .env.staging"
    run "install -m 0600 -o root -g root /dev/null ${STAGING_ENV}"
  else
    run "install -m 0600 -o root -g root ${EXAMPLE} ${STAGING_ENV}"
  fi
  AUTH_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  METRICS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  log "generated staging JWT secret + metrics token (written into ${STAGING_ENV})"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    python3 - "$STAGING_ENV" "$AUTH_SECRET" "$METRICS_TOKEN" "$STAGING_DB" "$STAGING_ROLE" <<'PY'
import sys, pathlib
path, auth, metrics, db, role = sys.argv[1:6]
p = pathlib.Path(path)
lines = p.read_text().splitlines() if p.exists() else []
overrides = {
    "VOYAGENT_AUTH_SECRET": auth,
    "VOYAGENT_METRICS_TOKEN": metrics,
    "VOYAGENT_DB_URL": f"postgresql://{role}:REPLACE_ME@127.0.0.1:5432/{db}",
    "VOYAGENT_ENV": "staging",
    "VOYAGENT_PUBLIC_BASE_URL": "https://staging.voyagent.globusdemos.com",
}
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        k = line.split("=", 1)[0].strip()
        if k in overrides:
            out.append(f"{k}={overrides[k]}")
            seen.add(k)
            continue
    out.append(line)
for k, v in overrides.items():
    if k not in seen:
        out.append(f"{k}={v}")
p.write_text("\n".join(out) + "\n")
PY
  fi
fi

step "6. systemd units"
for unit in voyagent-api-staging.service voyagent-web-staging.service voyagent-marketing-staging.service; do
  src="${UNITS_DIR}/${unit}"
  dst="/etc/systemd/system/${unit}"
  if [[ ! -f "$src" ]]; then
    log "WARN: unit template ${src} missing; skipping"
    continue
  fi
  run "install -m 0644 ${src} ${dst}"
done
run "systemctl daemon-reload"
run "systemctl enable voyagent-api-staging.service voyagent-web-staging.service voyagent-marketing-staging.service || true"
log "units installed + enabled (NOT started — start manually after first build)"

step "7. nginx vhost (HTTP only until certbot runs)"
NGINX_DST="/etc/nginx/sites-available/${STAGING_HOST}.conf"
if [[ -f "$NGINX_DST" ]]; then
  log "${NGINX_DST} already exists — leaving alone"
else
  run "install -m 0644 ${NGINX_TEMPLATE} ${NGINX_DST}"
  run "ln -sf ${NGINX_DST} /etc/nginx/sites-enabled/${STAGING_HOST}.conf"
  run "nginx -t && systemctl reload nginx"
fi

step "DONE — remaining manual steps"
cat <<EOF

  1. DNS:     add an A/AAAA record for ${STAGING_HOST} pointing at this host.
  2. Certbot: sudo certbot --nginx -d ${STAGING_HOST}
  3. Edit ${STAGING_ENV}:
       * replace REPLACE_ME in VOYAGENT_DB_URL with the password from
         ${STAGING_PG_ENV}
       * fill in SENTRY_DSN, ANTHROPIC_API_KEY, any GDS/vendor creds you
         want staging to exercise
  4. First build:
       cd ${STAGING_REPO}
       pnpm install && pnpm -r build
       uv sync && uv run alembic upgrade head
  5. Start the services:
       sudo systemctl start voyagent-api-staging voyagent-web-staging voyagent-marketing-staging
  6. Verify:
       curl -fsS https://${STAGING_HOST}/health

EOF
