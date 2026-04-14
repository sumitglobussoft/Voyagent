#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# release.sh — dev-machine helper that:
#   1. tags the current HEAD as vX.Y.Z (optional)
#   2. pushes to origin
#   3. SSHes into the Voyagent host and runs deploy.sh there
#
# Config precedence (highest first):
#   * CLI flags
#   * env vars already set in the shell
#   * local.env (gitignored; parsed key=value, not sourced)
#
# Required env/flags:
#   VOYAGENT_DEPLOY_HOST   (default: voyagent.globusdemos.com)
#   VOYAGENT_DEPLOY_USER   (default: empcloud-development)
#   VOYAGENT_DEPLOY_ROOT   (default: /opt/voyagent)
#   VOYAGENT_DEPLOY_PASS   (optional; if unset, sshpass is not used)
# -----------------------------------------------------------------------------

set -euo pipefail

TS() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(TS)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(TS)" "$*" >&2; exit 1; }

TMP_FILES=()
cleanup() {
    for f in "${TMP_FILES[@]:-}"; do
        [ -n "$f" ] && rm -f "$f" 2>/dev/null || true
    done
}
trap cleanup EXIT

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LOCAL_ENV="${REPO_ROOT}/local.env"

# ---- config --------------------------------------------------------------
parse_local_env() {
    # Parses simple KEY=VALUE pairs (comments + blank lines ok). We do not
    # `source` the file because it may contain shell-unfriendly values.
    [ -f "$LOCAL_ENV" ] || return 0
    while IFS= read -r line; do
        case "$line" in
            ''|\#*) continue ;;
        esac
        case "$line" in
            VOYAGENT_DEPLOY_HOST=*|VOYAGENT_DEPLOY_USER=*|VOYAGENT_DEPLOY_ROOT=*|VOYAGENT_DEPLOY_PASS=*)
                local k="${line%%=*}"
                local v="${line#*=}"
                # Strip surrounding quotes if present.
                v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
                if [ -z "${!k:-}" ]; then
                    export "$k=$v"
                fi
                ;;
        esac
    done < "$LOCAL_ENV"
}

parse_local_env

VOYAGENT_DEPLOY_HOST="${VOYAGENT_DEPLOY_HOST:-voyagent.globusdemos.com}"
VOYAGENT_DEPLOY_USER="${VOYAGENT_DEPLOY_USER:-empcloud-development}"
VOYAGENT_DEPLOY_ROOT="${VOYAGENT_DEPLOY_ROOT:-/opt/voyagent}"
VOYAGENT_DEPLOY_PASS="${VOYAGENT_DEPLOY_PASS:-}"

TAG=""
SKIP_TAG=0
SKIP_PUSH=0
EXTRA_DEPLOY_ARGS=()

usage() {
    cat <<EOF
Usage: $0 [options]
  --tag vX.Y.Z        create + push an annotated tag at HEAD before deploying
  --no-tag            skip tagging (default)
  --no-push           skip git push
  --deploy-arg ARG    forward an argument to remote deploy.sh (repeatable)
  -h, --help          this help

Env:
  VOYAGENT_DEPLOY_HOST  (default: voyagent.globusdemos.com)
  VOYAGENT_DEPLOY_USER  (default: empcloud-development)
  VOYAGENT_DEPLOY_ROOT  (default: /opt/voyagent)
  VOYAGENT_DEPLOY_PASS  optional; enables sshpass
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --tag)         TAG="$2"; SKIP_TAG=0; shift 2 ;;
        --no-tag)      SKIP_TAG=1; shift ;;
        --no-push)     SKIP_PUSH=1; shift ;;
        --deploy-arg)  EXTRA_DEPLOY_ARGS+=("$2"); shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[ -d "${REPO_ROOT}/.git" ] || die "not a git checkout: ${REPO_ROOT}"

# ---- git tag + push ------------------------------------------------------
if [ -n "$TAG" ] && [ "$SKIP_TAG" -eq 0 ]; then
    log "tagging HEAD as $TAG"
    ( cd "$REPO_ROOT" && git tag -a "$TAG" -m "voyagent release $TAG" )
fi

if [ "$SKIP_PUSH" -eq 0 ]; then
    log "git push"
    ( cd "$REPO_ROOT" && git push origin HEAD )
    if [ -n "$TAG" ] && [ "$SKIP_TAG" -eq 0 ]; then
        ( cd "$REPO_ROOT" && git push origin "$TAG" )
    fi
fi

# ---- remote deploy -------------------------------------------------------
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)

remote_cmd=$(printf 'bash %q/repo/infra/deploy/scripts/deploy.sh' "$VOYAGENT_DEPLOY_ROOT")
for a in "${EXTRA_DEPLOY_ARGS[@]:-}"; do
    [ -n "$a" ] && remote_cmd="$remote_cmd $(printf ' %q' "$a")"
done

log "remote deploy -> ${VOYAGENT_DEPLOY_USER}@${VOYAGENT_DEPLOY_HOST}"
log "  cmd: $remote_cmd"

if [ -n "$VOYAGENT_DEPLOY_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    PASS_FILE="$(mktemp)"
    TMP_FILES+=("$PASS_FILE")
    chmod 600 "$PASS_FILE"
    printf '%s\n' "$VOYAGENT_DEPLOY_PASS" > "$PASS_FILE"
    sshpass -f "$PASS_FILE" ssh "${SSH_OPTS[@]}" "${VOYAGENT_DEPLOY_USER}@${VOYAGENT_DEPLOY_HOST}" \
        "$remote_cmd"
else
    if [ -n "$VOYAGENT_DEPLOY_PASS" ]; then
        log "warning: VOYAGENT_DEPLOY_PASS set but sshpass not installed; falling back to interactive auth"
    fi
    ssh "${SSH_OPTS[@]}" "${VOYAGENT_DEPLOY_USER}@${VOYAGENT_DEPLOY_HOST}" "$remote_cmd"
fi

log "release complete"
