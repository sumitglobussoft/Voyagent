#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Voyagent server-side test harness.
#
# Runs the full test matrix (py-unit, py-live, e2e) inside Docker against a
# running prod stack on the same host. Results are captured to
# /opt/voyagent/test-results/<stamp>/ as JUnit XML + JSON + (for e2e) HTML.
#
# Preconditions:
#   - infra/deploy/scripts/deploy.sh has been run and the stack is up
#     (this script verifies voyagent_nginx is running).
#   - /opt/voyagent/.env.prod exists with valid secrets.
#
# Usage:
#   sudo -u voyagent bash /opt/voyagent/repo/infra/deploy/scripts/run-tests-on-server.sh
#   ... --only py-unit        # run just one suite (py-unit|py-live|e2e|all)
#   ... --base-url URL        # override VOYAGENT_BASE_URL for live + e2e
#   ... --no-build            # skip the build step (retries)
#   ... --prune               # delete stamped result dirs older than 7 days
# -----------------------------------------------------------------------------

set -euo pipefail

TS()   { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log()  { printf '[%s] %s\n' "$(TS)" "$*"; }
die()  { printf '[%s] ERROR: %s\n' "$(TS)" "$*" >&2; exit 1; }

VOYAGENT_ROOT="${VOYAGENT_ROOT:-/opt/voyagent}"
REPO_DIR="${VOYAGENT_ROOT}/repo"
ENV_FILE="${VOYAGENT_ENV_FILE:-${VOYAGENT_ROOT}/.env.prod}"
RESULTS_ROOT="${VOYAGENT_ROOT}/test-results"
COMPOSE_FILE="infra/deploy/compose.tests.yml"

ONLY="all"
DO_BUILD=1
DO_PRUNE=0
BASE_URL_OVERRIDE=""

usage() {
    cat <<EOF
Usage: $0 [options]
  --only SUITE     one of: py-unit, py-live, e2e, all (default: all)
  --base-url URL   override VOYAGENT_BASE_URL for live + e2e suites
  --no-build       skip the 'docker compose build' step (retries)
  --prune          delete stamped result dirs older than 7 days
  -h, --help       show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --only)     ONLY="${2:?--only requires a value}"; shift 2 ;;
        --base-url) BASE_URL_OVERRIDE="${2:?--base-url requires a value}"; shift 2 ;;
        --no-build) DO_BUILD=0; shift ;;
        --prune)    DO_PRUNE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

case "$ONLY" in
    all|py-unit|py-live|e2e) ;;
    *) die "--only must be one of: py-unit py-live e2e all (got: $ONLY)" ;;
esac

trap 'die "run-tests aborted (line $LINENO)"' ERR

# -----------------------------------------------------------------------------
# Preflight
# -----------------------------------------------------------------------------
preflight() {
    [ -d "$REPO_DIR" ]                    || die "repo missing at $REPO_DIR"
    [ -f "$REPO_DIR/$COMPOSE_FILE" ]      || die "compose file not found at $REPO_DIR/$COMPOSE_FILE"
    [ -f "$ENV_FILE" ]                    || die ".env.prod missing at $ENV_FILE"
    command -v docker >/dev/null 2>&1     || die "docker not installed"

    # Compose detection — prefer v2 plugin, fall back to standalone v1.
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_BIN=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_BIN=(docker-compose)
        log "using standalone docker-compose: $(docker-compose --version 2>&1 | head -1)"
    else
        die "neither 'docker compose' plugin nor 'docker-compose' found"
    fi

    # The prod stack must be running — tests-py-live and tests-e2e attach
    # to the external `voyagent_net` network which compose.prod.yml owns.
    if ! docker ps --format '{{.Names}}' | grep -q '^voyagent_nginx$'; then
        die "voyagent_nginx is not running — run infra/deploy/scripts/deploy.sh first"
    fi
}

# -----------------------------------------------------------------------------
# Results directory management
# -----------------------------------------------------------------------------
prepare_results() {
    STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    STAMP_DIR="${RESULTS_ROOT}/${STAMP}"
    mkdir -p "$RESULTS_ROOT"
    mkdir -p "${RESULTS_ROOT}/py-unit" "${RESULTS_ROOT}/py-live" \
             "${RESULTS_ROOT}/e2e/playwright-report" \
             "${RESULTS_ROOT}/e2e/test-results"
    mkdir -p "${STAMP_DIR}/py-unit" "${STAMP_DIR}/py-live" "${STAMP_DIR}/e2e"
    chmod 755 "$STAMP_DIR" "${STAMP_DIR}/py-unit" "${STAMP_DIR}/py-live" "${STAMP_DIR}/e2e"
    log "results dir: ${STAMP_DIR}"
}

prune_old_results() {
    [ "$DO_PRUNE" -eq 1 ] || return 0
    [ -d "$RESULTS_ROOT" ] || return 0
    log "pruning stamped result dirs older than 7 days under ${RESULTS_ROOT}"
    # Only prune dirs matching the stamp pattern so we never nuke the
    # live mount dirs (py-unit, py-live, e2e).
    find "$RESULTS_ROOT" -mindepth 1 -maxdepth 1 -type d \
        -regex '.*/[0-9]\{8\}T[0-9]\{6\}Z$' \
        -mtime +7 -exec rm -rf {} + || true
}

# -----------------------------------------------------------------------------
# Compose helpers
# -----------------------------------------------------------------------------
compose() {
    (
        cd "$REPO_DIR"
        VOYAGENT_ENV_FILE="$ENV_FILE" "${COMPOSE_BIN[@]}" \
            -f "$COMPOSE_FILE" \
            --env-file "$ENV_FILE" \
            "$@"
    )
}

build_images() {
    [ "$DO_BUILD" -eq 1 ] || { log "skipping build (--no-build)"; return; }
    log "building test images (tests-py-unit, tests-e2e)"
    # tests-py-live reuses the tests-py-unit image — don't build twice.
    compose build tests-py-unit tests-e2e
}

# -----------------------------------------------------------------------------
# Suite runners — each sets a named exit code, never aborts the pipeline.
# -----------------------------------------------------------------------------
RC_PY_UNIT="skip"
RC_PY_LIVE="skip"
RC_E2E="skip"

run_suite() {
    local profile="$1"
    local service="$2"
    local host_src="$3"    # where compose mount put the results
    local stamp_dst="$4"   # where to symlink them for this run

    local env_extra=()
    if [ -n "$BASE_URL_OVERRIDE" ]; then
        env_extra=(-e "VOYAGENT_BASE_URL=${BASE_URL_OVERRIDE}")
    fi

    log "---- running ${service} (profile=${profile}) ----"
    set +e
    compose --profile "$profile" run --rm "${env_extra[@]}" "$service"
    local rc=$?
    set -e
    log "${service} exit=${rc}"

    # Snapshot the host-mounted results into the stamped dir so every
    # run has a durable record even though the mount dirs get
    # overwritten on the next run. Use cp -a (not mv) so the mount
    # stays intact for the compose volume.
    if [ -d "$host_src" ]; then
        cp -a "$host_src/." "$stamp_dst/" 2>/dev/null || true
    fi

    printf '%s' "$rc"
}

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
fmt_status() {
    local rc="$1"
    case "$rc" in
        skip) printf 'SKIP' ;;
        0)    printf 'PASS' ;;
        *)    printf 'FAIL' ;;
    esac
}

print_summary() {
    printf '\n'
    printf '========================================================================\n'
    printf '  Voyagent test run  |  stamp=%s\n' "$STAMP"
    printf '========================================================================\n'
    printf '  %-10s %-6s %-5s %s\n' "Suite" "Status" "Exit" "Reports"
    printf '  %-10s %-6s %-5s %s\n' "py-unit" "$(fmt_status "$RC_PY_UNIT")" "$RC_PY_UNIT" "${STAMP_DIR}/py-unit/junit.xml"
    printf '  %-10s %-6s %-5s %s\n' "py-live" "$(fmt_status "$RC_PY_LIVE")" "$RC_PY_LIVE" "${STAMP_DIR}/py-live/junit.xml"
    printf '  %-10s %-6s %-5s %s\n' "e2e"     "$(fmt_status "$RC_E2E")"     "$RC_E2E"     "${STAMP_DIR}/e2e/test-results/junit.xml (html: playwright-report/)"
    printf '========================================================================\n\n'
}

max_rc() {
    local top=0 v
    for v in "$@"; do
        case "$v" in
            skip|"") continue ;;
            *) [ "$v" -gt "$top" ] && top="$v" ;;
        esac
    done
    printf '%s' "$top"
}

banner() {
    cat <<EOF
========================================================================
  Voyagent test harness  |  host=$(hostname)  |  root=${VOYAGENT_ROOT}
  repo:    ${REPO_DIR}
  env:     ${ENV_FILE}
  compose: ${COMPOSE_FILE}
  only:    ${ONLY}
  build:   $([ "$DO_BUILD" -eq 1 ] && echo yes || echo no)
EOF
    [ -n "$BASE_URL_OVERRIDE" ] && printf '  baseURL: %s\n' "$BASE_URL_OVERRIDE"
    printf '========================================================================\n'
}

main() {
    banner
    preflight
    prune_old_results
    prepare_results
    build_images

    if [ "$ONLY" = "all" ] || [ "$ONLY" = "py-unit" ]; then
        RC_PY_UNIT="$(run_suite tests-unit tests-py-unit \
            "${RESULTS_ROOT}/py-unit" "${STAMP_DIR}/py-unit")"
    fi

    if [ "$ONLY" = "all" ] || [ "$ONLY" = "py-live" ]; then
        RC_PY_LIVE="$(run_suite tests-live tests-py-live \
            "${RESULTS_ROOT}/py-live" "${STAMP_DIR}/py-live")"
    fi

    if [ "$ONLY" = "all" ] || [ "$ONLY" = "e2e" ]; then
        RC_E2E="$(run_suite tests-e2e tests-e2e \
            "${RESULTS_ROOT}/e2e" "${STAMP_DIR}/e2e")"
    fi

    print_summary

    local final
    final="$(max_rc "$RC_PY_UNIT" "$RC_PY_LIVE" "$RC_E2E")"
    exit "$final"
}

main "$@"
