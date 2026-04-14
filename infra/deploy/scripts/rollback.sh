#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# rollback.sh — restore the previously deployed image tag.
#
# Reads /opt/voyagent/deploy-history.log, picks the second-most-recent
# `deploy` entry, and relaunches the stack with VOYAGENT_VERSION set to
# that tag. Images for that version must still be present locally (they
# normally are — we never prune aggressively).
# -----------------------------------------------------------------------------

set -euo pipefail

TS() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(TS)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(TS)" "$*" >&2; exit 1; }

trap 'log "rollback aborted (line $LINENO)"' ERR

VOYAGENT_ROOT="${VOYAGENT_ROOT:-/opt/voyagent}"
REPO_DIR="${VOYAGENT_ROOT}/repo"
ENV_FILE="${VOYAGENT_ENV_FILE:-${VOYAGENT_ROOT}/.env.prod}"
HISTORY_LOG="${VOYAGENT_ROOT}/deploy-history.log"
COMPOSE_FILE="infra/deploy/compose.prod.yml"

TARGET_VERSION="${1:-}"

banner() {
    cat <<EOF
========================================================================
  Voyagent rollback
  repo:      ${REPO_DIR}
  env:       ${ENV_FILE}
  history:   ${HISTORY_LOG}
========================================================================
EOF
}

resolve_target() {
    if [ -n "$TARGET_VERSION" ]; then
        log "rolling back to user-specified version: $TARGET_VERSION"
        return
    fi
    [ -f "$HISTORY_LOG" ] || die "no deploy history at $HISTORY_LOG — specify a version explicitly: $0 <version>"

    # Take the second-most-recent deploy entry.
    TARGET_VERSION="$(grep -E '^[0-9-]+T[0-9:Z]+ deploy version=' "$HISTORY_LOG" \
        | tail -n 2 | head -n 1 \
        | sed -E 's/.* version=([^ ]+).*/\1/')"

    [ -n "$TARGET_VERSION" ] || die "could not determine previous version from $HISTORY_LOG"
    log "resolved previous version: $TARGET_VERSION"
}

confirm_images() {
    local missing=0
    for img in voyagent-api voyagent-web voyagent-marketing; do
        if ! docker image inspect "${img}:${TARGET_VERSION}" >/dev/null 2>&1; then
            log "warning: image ${img}:${TARGET_VERSION} not found locally"
            missing=$((missing + 1))
        fi
    done
    if [ "$missing" -gt 0 ]; then
        die "$missing image(s) missing — rebuild from the matching commit before rolling back"
    fi
}

_compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

relaunch() {
    export VOYAGENT_VERSION="$TARGET_VERSION"
    local cc
    cc="$(_compose_cmd)"
    (
        cd "$REPO_DIR"
        $cc -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans
    )
    printf '%s rollback version=%s user=%s\n' "$(TS)" "$TARGET_VERSION" "${USER:-unknown}" >> "$HISTORY_LOG"
    log "rollback complete — running version=$TARGET_VERSION"
}

main() {
    banner
    [ -d "$REPO_DIR" ] || die "missing $REPO_DIR"
    [ -f "$ENV_FILE" ] || die "missing $ENV_FILE"
    resolve_target
    confirm_images
    relaunch
}

main "$@"
