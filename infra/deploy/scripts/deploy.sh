#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Voyagent host-side deploy.
#
# Expected state before first run:
#   - `bootstrap.sh` has been executed once.
#   - The repo lives at /opt/voyagent/repo (symlink or clone).
#   - /opt/voyagent/.env.prod is filled in with real secrets.
#
# What this script does, in order:
#   1. cd into the repo and `git pull` (skipped with --no-pull).
#   2. Validate .env.prod — reject `change-me` placeholders.
#   3. `docker compose build` the stack at the current commit.
#   4. Run alembic migrations via the `migrate` profile.
#   5. `docker compose up -d --remove-orphans`.
#   6. Poll the edge /health endpoint for up to 120s.
#   7. Append a line to /opt/voyagent/deploy-history.log.
# -----------------------------------------------------------------------------

set -euo pipefail

TS() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(TS)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(TS)" "$*" >&2; exit 1; }

VOYAGENT_ROOT="${VOYAGENT_ROOT:-/opt/voyagent}"
REPO_DIR="${VOYAGENT_ROOT}/repo"
ENV_FILE="${VOYAGENT_ENV_FILE:-${VOYAGENT_ROOT}/.env.prod}"
HISTORY_LOG="${VOYAGENT_ROOT}/deploy-history.log"
COMPOSE_FILE="infra/deploy/compose.prod.yml"
TMP_FILES=()

cleanup() {
    for f in "${TMP_FILES[@]:-}"; do
        [ -n "$f" ] && rm -f "$f" 2>/dev/null || true
    done
}
trap cleanup EXIT
trap 'log "deploy aborted (line $LINENO)"' ERR

DO_PULL=1
DO_MIGRATE=1
COMPOSE_PROFILES_EXTRA=()

usage() {
    cat <<EOF
Usage: $0 [options]
  --no-pull        skip the 'git pull' step
  --no-migrate     skip the alembic migration step
  --with PROFILE   additional compose profile (future, portals); repeatable
  -h, --help       show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --no-pull)     DO_PULL=0; shift ;;
        --no-migrate)  DO_MIGRATE=0; shift ;;
        --with)        COMPOSE_PROFILES_EXTRA+=("$2"); shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

banner() {
    cat <<EOF
========================================================================
  Voyagent deploy  |  host=$(hostname)  |  root=${VOYAGENT_ROOT}
  repo:      ${REPO_DIR}
  env:       ${ENV_FILE}
  compose:   ${COMPOSE_FILE}
========================================================================
EOF
}

preflight() {
    [ -d "$REPO_DIR" ] || die "repo missing at $REPO_DIR — scp or git clone it first"
    [ -f "$REPO_DIR/$COMPOSE_FILE" ] || die "compose file not found at $REPO_DIR/$COMPOSE_FILE"
    [ -f "$ENV_FILE" ] || die ".env.prod missing at $ENV_FILE"

    local mode
    mode="$(stat -c '%a' "$ENV_FILE")"
    if [ "$mode" != "600" ]; then
        log "warning: $ENV_FILE mode=$mode (expected 600); fixing"
        chmod 600 "$ENV_FILE"
    fi

    command -v docker >/dev/null 2>&1 || die "docker not installed — run bootstrap.sh"

    # Compose detection — prefer the v2 plugin, fall back to the hyphenated
    # standalone (`docker-compose`) which is what many shared hosts still run.
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_BIN=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_BIN=(docker-compose)
        log "using standalone docker-compose: $(docker-compose --version 2>&1 | head -1)"
    else
        die "neither 'docker compose' plugin nor 'docker-compose' found"
    fi
}

validate_env() {
    local required=(POSTGRES_PASSWORD VOYAGENT_KMS_KEY)
    for key in "${required[@]}"; do
        local v
        v="$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | sed -e "s/^${key}=//")"
        if [ -z "$v" ]; then
            die "$key is empty in $ENV_FILE"
        fi
        if printf '%s' "$v" | grep -qi "change-me"; then
            die "$key still contains 'change-me' placeholder — fill in a real value"
        fi
    done
    log "env validated (required keys present, no placeholders)"
}

pull_repo() {
    if [ "$DO_PULL" -eq 0 ]; then
        log "skipping git pull (--no-pull)"
        return
    fi
    if [ ! -d "$REPO_DIR/.git" ]; then
        log "$REPO_DIR is not a git checkout — skipping pull"
        return
    fi
    log "git pull in $REPO_DIR"
    ( cd "$REPO_DIR" && git fetch --all --prune && git pull --ff-only )
}

resolve_version() {
    local sha="unknown"
    if [ -d "$REPO_DIR/.git" ]; then
        sha="$(cd "$REPO_DIR" && git rev-parse --short=12 HEAD)"
    fi
    export VOYAGENT_VERSION="${VOYAGENT_VERSION:-${sha}}"
    log "deploying version: ${VOYAGENT_VERSION}"
}

compose() {
    (
        cd "$REPO_DIR"
        # VOYAGENT_ENV_FILE is consumed by the compose file's per-service
        # `env_file:` key; --env-file only handles variable interpolation.
        # BuildKit is required for `--mount=type=cache` inside Dockerfiles.
        DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 \
        VOYAGENT_ENV_FILE="$ENV_FILE" "${COMPOSE_BIN[@]}" \
            -f "$COMPOSE_FILE" \
            --env-file "$ENV_FILE" \
            "$@"
    )
}

build_images() {
    log "building images"
    compose build --pull
}

run_migrations() {
    if [ "$DO_MIGRATE" -eq 0 ]; then
        log "skipping migrations (--no-migrate)"
        return
    fi
    log "running alembic migrations"
    compose --profile migrate run --rm alembic \
        alembic -c infra/alembic/alembic.ini upgrade head
}

start_stack() {
    local extra=()
    for p in "${COMPOSE_PROFILES_EXTRA[@]:-}"; do
        [ -n "$p" ] && extra+=(--profile "$p")
    done
    log "starting stack (profiles: default ${COMPOSE_PROFILES_EXTRA[*]:-})"
    compose "${extra[@]}" up -d --remove-orphans
}

wait_healthy() {
    local edge_port
    edge_port="$(grep -E '^VOYAGENT_EDGE_PORT=' "$ENV_FILE" | tail -n1 | sed -e 's/^VOYAGENT_EDGE_PORT=//')"
    edge_port="${edge_port:-8480}"
    local url="http://127.0.0.1:${edge_port}/health"

    log "waiting for ${url} (up to 120s)"
    local deadline=$(( $(date +%s) + 120 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            log "healthcheck OK"
            return 0
        fi
        sleep 3
    done
    compose ps || true
    die "stack failed to become healthy within 120s — inspect '${COMPOSE_BIN[*]} -f $COMPOSE_FILE logs'"
}

record_history() {
    local sha="${VOYAGENT_VERSION:-unknown}"
    local line
    line="$(TS) deploy version=${sha} profiles=${COMPOSE_PROFILES_EXTRA[*]:-default} user=${USER:-unknown}"
    if [ -w "$HISTORY_LOG" ] || [ -w "$(dirname "$HISTORY_LOG")" ]; then
        printf '%s\n' "$line" >> "$HISTORY_LOG" || true
    fi
}

summary() {
    local edge_port
    edge_port="$(grep -E '^VOYAGENT_EDGE_PORT=' "$ENV_FILE" | tail -n1 | sed -e 's/^VOYAGENT_EDGE_PORT=//')"
    edge_port="${edge_port:-8480}"
    printf '\n[deploy] OK  version=%s  edge=127.0.0.1:%s  env=%s\n\n' \
        "${VOYAGENT_VERSION}" "${edge_port}" "${ENV_FILE}"
}

main() {
    banner
    preflight
    validate_env
    pull_repo
    resolve_version
    build_images
    run_migrations
    start_stack
    wait_healthy
    record_history
    summary
}

main "$@"
