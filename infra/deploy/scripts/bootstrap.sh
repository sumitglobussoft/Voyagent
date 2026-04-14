#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Voyagent host bootstrap — idempotent, Debian/Ubuntu.
#
# End state when this script exits 0:
#   - Docker Engine (>=24) + compose plugin installed
#   - /opt/voyagent exists, owned by the `voyagent` system user
#   - $SUDO_USER (or $USER) is in the `docker` group
#   - A skeleton /opt/voyagent/.env.prod is in place (mode 0600) if missing
#
# Run as root or with sudo. Re-runs are safe — the script detects existing
# state and narrates what it chose to do.
# -----------------------------------------------------------------------------

set -euo pipefail

# shellcheck disable=SC2034
SCRIPT_NAME="bootstrap.sh"
TS() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(TS)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(TS)" "$*" >&2; exit 1; }

trap 'log "bootstrap aborted (line $LINENO)"' ERR

VOYAGENT_ROOT="/opt/voyagent"
VOYAGENT_USER="voyagent"
MIN_DOCKER_MAJOR=24

banner() {
    cat <<'EOF'
========================================================================
  Voyagent host bootstrap
  - installs/validates Docker + compose plugin
  - creates /opt/voyagent and the `voyagent` system user
  - leaves the host ready for scripts/deploy.sh
========================================================================
EOF
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "must be run as root (try: sudo $0)"
    fi
}

detect_os() {
    if [ ! -r /etc/os-release ]; then
        die "cannot read /etc/os-release — unsupported OS"
    fi
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        debian|ubuntu) : ;;
        *) die "unsupported distro '${ID:-unknown}' (this script targets Debian/Ubuntu)" ;;
    esac
    log "detected distro: ${PRETTY_NAME:-unknown}"
}

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        local have
        have="$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'unknown')"
        log "docker already present (server ${have}); leaving it alone"

        local major
        major="$(printf '%s' "$have" | cut -d. -f1)"
        if [[ "$major" =~ ^[0-9]+$ ]] && [ "$major" -lt "$MIN_DOCKER_MAJOR" ]; then
            die "docker ${have} is older than required ${MIN_DOCKER_MAJOR}.x — upgrade manually then re-run"
        fi
    else
        log "installing docker + compose plugin via apt"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y docker.io docker-compose-plugin
    fi

    if ! docker compose version >/dev/null 2>&1; then
        log "compose plugin missing — installing"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y docker-compose-plugin
    fi
    log "compose: $(docker compose version --short 2>/dev/null || echo unknown)"

    systemctl enable --now docker >/dev/null 2>&1 || true
}

ensure_user() {
    if id "$VOYAGENT_USER" >/dev/null 2>&1; then
        log "user '$VOYAGENT_USER' already exists"
    else
        log "creating system user '$VOYAGENT_USER'"
        useradd --system --create-home --shell /usr/sbin/nologin "$VOYAGENT_USER"
    fi

    local invoking="${SUDO_USER:-${USER:-}}"
    if [ -n "$invoking" ] && [ "$invoking" != "root" ]; then
        if ! id -nG "$invoking" | tr ' ' '\n' | grep -qx docker; then
            log "adding '$invoking' to docker group (re-login required for effect)"
            usermod -aG docker "$invoking"
        else
            log "'$invoking' already in docker group"
        fi
    fi
}

ensure_dirs() {
    if [ ! -d "$VOYAGENT_ROOT" ]; then
        log "creating $VOYAGENT_ROOT"
        mkdir -p "$VOYAGENT_ROOT"
    fi
    chown "$VOYAGENT_USER:$VOYAGENT_USER" "$VOYAGENT_ROOT"
    chmod 0755 "$VOYAGENT_ROOT"

    local env_file="$VOYAGENT_ROOT/.env.prod"
    if [ ! -f "$env_file" ]; then
        log "creating empty $env_file (mode 0600) — fill it in before deploy"
        install -m 0600 /dev/null "$env_file"
        chown "$VOYAGENT_USER:$VOYAGENT_USER" "$env_file"
    else
        log "$env_file already exists — leaving untouched"
        chmod 0600 "$env_file"
    fi

    local log_file="$VOYAGENT_ROOT/deploy-history.log"
    if [ ! -f "$log_file" ]; then
        install -m 0644 /dev/null "$log_file"
        chown "$VOYAGENT_USER:$VOYAGENT_USER" "$log_file"
    fi
}

summary() {
    cat <<EOF

[bootstrap] complete.
  - docker:   $(docker --version 2>/dev/null || echo missing)
  - compose:  $(docker compose version --short 2>/dev/null || echo missing)
  - dir:      $VOYAGENT_ROOT ($(stat -c '%U:%G mode=%a' "$VOYAGENT_ROOT"))
  - env file: $VOYAGENT_ROOT/.env.prod (chmod 0600)

Next steps:
  1. scp the repo to $VOYAGENT_ROOT/repo  (or git clone it there).
  2. Populate $VOYAGENT_ROOT/.env.prod from infra/deploy/.env.prod.example.
  3. Run: sudo -u $VOYAGENT_USER bash $VOYAGENT_ROOT/repo/infra/deploy/scripts/deploy.sh
EOF
}

main() {
    banner
    require_root
    detect_os
    install_docker
    ensure_user
    ensure_dirs
    summary
}

main "$@"
