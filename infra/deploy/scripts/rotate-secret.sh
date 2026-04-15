#!/usr/bin/env bash
#
# rotate-secret.sh — interactive secret rotation for voyagent production.
#
# Picks which secret to rotate, generates a fresh value, backs up .env.prod,
# updates the single env var in-place (via python, not sed — safer for values
# with special characters), applies any side-effects (ALTER USER for the DB
# password, redis.conf + restart for the redis password, systemctl restart for
# everything that needs to re-read .env.prod), and runs a smoke curl.
#
# NOT idempotent by design — each invocation is a real rotation event with a
# new backup file. Safe to abort mid-run (nothing is applied before the
# confirmation prompt).
#
# Flags:
#   --dry-run    show every action, touch nothing
#   --secret K   skip the interactive menu, rotate K directly

set -euo pipefail

ENV_FILE="${VOYAGENT_ENV_FILE:-/opt/voyagent/.env.prod}"
REDIS_CONF="${VOYAGENT_REDIS_CONF:-/etc/redis/redis.conf}"
SERVICES_TO_RESTART="${VOYAGENT_SERVICES:-voyagent-api voyagent-web voyagent-marketing voyagent-worker}"
SMOKE_URL="${VOYAGENT_SMOKE_URL:-https://voyagent.globusdemos.com/health}"

DRY_RUN=0
SECRET_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --secret)  SECRET_KEY="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

log() { printf '[rotate-secret] %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '    DRY: %s\n' "$*"
  else
    eval "$@"
  fi
}

SUPPORTED=(
  VOYAGENT_AUTH_SECRET
  VOYAGENT_DB_URL
  VOYAGENT_REDIS_URL
  VOYAGENT_METRICS_TOKEN
  VOYAGENT_KMS_KEY
)

prompt_menu() {
  echo "Which secret do you want to rotate?"
  local i=1
  for k in "${SUPPORTED[@]}"; do
    printf '  %d) %s\n' "$i" "$k"
    i=$((i+1))
  done
  printf 'choice: '
  read -r CHOICE
  if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || (( CHOICE < 1 || CHOICE > ${#SUPPORTED[@]} )); then
    echo "invalid choice" >&2; exit 2
  fi
  SECRET_KEY="${SUPPORTED[$((CHOICE-1))]}"
}

if [[ -z "$SECRET_KEY" ]]; then
  prompt_menu
fi

# validate secret key is supported
ok=0
for k in "${SUPPORTED[@]}"; do [[ "$k" == "$SECRET_KEY" ]] && ok=1; done
[[ "$ok" -eq 1 ]] || { echo "unsupported secret: $SECRET_KEY" >&2; exit 2; }

if [[ "$SECRET_KEY" == "VOYAGENT_AUTH_SECRET" ]]; then
  cat >&2 <<'EOF'

  !!! WARNING: rotating VOYAGENT_AUTH_SECRET invalidates every existing
      signed JWT. All logged-in users will be forced to sign back in.
      Do this outside business hours unless it's an incident response.

EOF
fi

printf 'Type "ROTATE %s" to continue: ' "$SECRET_KEY" >&2
read -r CONFIRM
[[ "$CONFIRM" == "ROTATE $SECRET_KEY" ]] || { echo "aborted" >&2; exit 1; }

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2; exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${ENV_FILE}.bak.${TS}"
log "backing up $ENV_FILE -> $BACKUP"
run "install -m 0600 ${ENV_FILE} ${BACKUP}"

new_token() {
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
}

NEW_VALUE=""
NEW_DB_PASSWORD=""
NEW_REDIS_PASSWORD=""

case "$SECRET_KEY" in
  VOYAGENT_AUTH_SECRET|VOYAGENT_METRICS_TOKEN|VOYAGENT_KMS_KEY)
    NEW_VALUE="$(new_token)"
    ;;
  VOYAGENT_DB_URL)
    NEW_DB_PASSWORD="$(new_token)"
    # Rebuild the URL with the new password; preserve user/host/port/db.
    OLD_URL="$(grep "^VOYAGENT_DB_URL=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    NEW_VALUE="$(python3 - "$OLD_URL" "$NEW_DB_PASSWORD" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit, quote
old, new_pw = sys.argv[1], sys.argv[2]
p = urlsplit(old)
user = p.username or "voyagent"
host = p.hostname or "127.0.0.1"
port = f":{p.port}" if p.port else ""
netloc = f"{user}:{quote(new_pw, safe='')}@{host}{port}"
print(urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment)))
PY
)"
    ;;
  VOYAGENT_REDIS_URL)
    NEW_REDIS_PASSWORD="$(new_token)"
    OLD_URL="$(grep "^VOYAGENT_REDIS_URL=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    NEW_VALUE="$(python3 - "$OLD_URL" "$NEW_REDIS_PASSWORD" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit, quote
old, new_pw = sys.argv[1], sys.argv[2]
p = urlsplit(old)
host = p.hostname or "127.0.0.1"
port = f":{p.port}" if p.port else ""
netloc = f":{quote(new_pw, safe='')}@{host}{port}"
print(urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment)))
PY
)"
    ;;
esac

log "updating $SECRET_KEY in $ENV_FILE"
if [[ "$DRY_RUN" -eq 0 ]]; then
  python3 - "$ENV_FILE" "$SECRET_KEY" "$NEW_VALUE" <<'PY'
import sys, pathlib
path, key, value = sys.argv[1:4]
p = pathlib.Path(path)
lines = p.read_text().splitlines()
seen = False
out = []
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"{key}={value}")
p.write_text("\n".join(out) + "\n")
PY
else
  log "DRY: would set ${SECRET_KEY}=<new>"
fi

# Side-effects
case "$SECRET_KEY" in
  VOYAGENT_DB_URL)
    log "ALTER USER voyagent WITH PASSWORD <new>"
    run "sudo -u postgres psql -v ON_ERROR_STOP=1 -c \"ALTER USER voyagent WITH PASSWORD '${NEW_DB_PASSWORD}';\""
    # Update the master env file too so pg-backup.sh keeps working.
    if [[ -f /etc/voyagent/postgres-master.env ]]; then
      run "python3 -c 'import sys,pathlib; p=pathlib.Path(sys.argv[1]); new=sys.argv[2]; lines=p.read_text().splitlines(); out=[]; seen=False;
[out.append(f\"PGPASSWORD={new}\") if l.startswith(\"PGPASSWORD=\") else out.append(l) for l in lines];
p.write_text(\"\n\".join(out)+\"\n\")' /etc/voyagent/postgres-master.env ${NEW_DB_PASSWORD}"
    fi
    ;;
  VOYAGENT_REDIS_URL)
    log "updating $REDIS_CONF requirepass"
    run "sed -i.bak 's/^requirepass .*/requirepass ${NEW_REDIS_PASSWORD}/' ${REDIS_CONF}"
    run "systemctl restart redis-server"
    ;;
esac

log "restarting voyagent services: $SERVICES_TO_RESTART"
for svc in $SERVICES_TO_RESTART; do
  run "systemctl restart ${svc}"
done

log "smoke test: $SMOKE_URL"
if [[ "$DRY_RUN" -eq 0 ]]; then
  if curl -fsS --max-time 10 "$SMOKE_URL" >/dev/null; then
    log "smoke OK"
  else
    log "SMOKE FAILED — consider rolling back from $BACKUP"
    exit 1
  fi
else
  log "DRY: would curl $SMOKE_URL"
fi

log "done. Backup of previous env is at $BACKUP"
