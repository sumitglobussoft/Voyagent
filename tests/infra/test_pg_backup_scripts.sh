#!/usr/bin/env bash
#
# test_pg_backup_scripts.sh — plain-shell assertions for the pg-backup
# family. No bats dependency. Run from the repo root:
#
#   bash tests/infra/test_pg_backup_scripts.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="${REPO_ROOT}/infra/deploy/scripts"

PASS=0
FAIL=0
FAILED_NAMES=()

assert() {
  local name="$1" cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    printf '  ok   %s\n' "$name"
    PASS=$((PASS+1))
  else
    printf '  FAIL %s\n' "$name"
    FAIL=$((FAIL+1))
    FAILED_NAMES+=( "$name" )
  fi
}

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    printf '  ok   %s\n' "$name"
    PASS=$((PASS+1))
  else
    printf '  FAIL %s (expected %q got %q)\n' "$name" "$expected" "$actual"
    FAIL=$((FAIL+1))
    FAILED_NAMES+=( "$name" )
  fi
}

echo "== pg-backup scripts =="

assert "pg-backup.sh exists" \
  "test -f ${SCRIPTS}/pg-backup.sh"

assert "pg-backup-offsite.sh exists" \
  "test -f ${SCRIPTS}/pg-backup-offsite.sh"

assert "pg-restore.sh exists" \
  "test -f ${SCRIPTS}/pg-restore.sh"

# On Windows filesystems the executable bit is meaningless; on Linux we care.
# Check the shebang instead — that's a portable "is this a shell script" test.
assert "pg-backup-offsite.sh has bash shebang" \
  "head -1 ${SCRIPTS}/pg-backup-offsite.sh | grep -q '^#!.*bash'"

assert "pg-restore.sh has bash shebang" \
  "head -1 ${SCRIPTS}/pg-restore.sh | grep -q '^#!.*bash'"

assert "pg-backup-offsite.sh uses set -euo pipefail" \
  "grep -q 'set -euo pipefail' ${SCRIPTS}/pg-backup-offsite.sh"

assert "pg-restore.sh uses set -euo pipefail" \
  "grep -q 'set -euo pipefail' ${SCRIPTS}/pg-restore.sh"

echo
echo "== pg-backup-offsite.sh opt-in behavior =="

# When the opt-in env file is missing the script must exit 0 (no-op).
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

MISSING_ENV="${TMPDIR_TEST}/nope.env"
VOYAGENT_OFFSITE_ENV_FILE="$MISSING_ENV" \
  VOYAGENT_BACKUP_DIR="$TMPDIR_TEST" \
  VOYAGENT_PG_BACKUP_SCRIPT="/bin/true" \
  bash "${SCRIPTS}/pg-backup-offsite.sh" >/dev/null 2>&1
RC=$?
assert_eq "exit 0 when opt-in file is missing" "0" "$RC"

# With opt-in file present but no rclone, --dry-run should still succeed
# enough to get past the rclone check (we fake rclone on PATH).
FAKE_BIN="${TMPDIR_TEST}/bin"
mkdir -p "$FAKE_BIN"
cat >"$FAKE_BIN/rclone" <<'FAKE'
#!/usr/bin/env bash
# record invocation
echo "rclone $*" >> "${FAKE_RCLONE_LOG:-/dev/null}"
exit 0
FAKE
chmod +x "$FAKE_BIN/rclone"

cat >"${TMPDIR_TEST}/off.env" <<EOF
VOYAGENT_BACKUP_REMOTE=test-remote
VOYAGENT_BACKUP_BUCKET=test-bucket
VOYAGENT_BACKUP_PREFIX=voyagent/
EOF

# Create a fake dump file so the "newest dump" lookup succeeds.
touch "${TMPDIR_TEST}/voyagent-20260101T000000Z.dump"

FAKE_RCLONE_LOG="${TMPDIR_TEST}/rclone.log" \
PATH="${FAKE_BIN}:${PATH}" \
VOYAGENT_OFFSITE_ENV_FILE="${TMPDIR_TEST}/off.env" \
VOYAGENT_BACKUP_DIR="$TMPDIR_TEST" \
VOYAGENT_PG_BACKUP_SCRIPT="/bin/true" \
  bash "${SCRIPTS}/pg-backup-offsite.sh" --dry-run >/dev/null 2>&1
RC=$?
assert_eq "--dry-run exits 0 with fake rclone" "0" "$RC"

# And critically, a dry-run must NOT have called a real rclone copy without
# --dry-run. We check the log for --dry-run presence.
if [[ -f "${TMPDIR_TEST}/rclone.log" ]]; then
  assert "dry-run passes --dry-run to rclone" \
    "grep -q -- '--dry-run' ${TMPDIR_TEST}/rclone.log"
else
  printf '  FAIL dry-run rclone log missing\n'
  FAIL=$((FAIL+1))
  FAILED_NAMES+=( "dry-run rclone log missing" )
fi

echo
echo "== pg-restore.sh confirmation gate =="

# Piping a bad phrase must cause non-zero exit. We have to pass a dump path
# that exists so we get past the usage/file checks and hit the prompt.
FAKE_DUMP="${TMPDIR_TEST}/fake.dump"
touch "$FAKE_DUMP"
echo "NOT THE RIGHT STRING" | bash "${SCRIPTS}/pg-restore.sh" "$FAKE_DUMP" >/dev/null 2>&1
RC=$?
if [[ "$RC" -ne 0 ]]; then
  printf '  ok   pg-restore.sh rejects wrong confirmation\n'
  PASS=$((PASS+1))
else
  printf '  FAIL pg-restore.sh accepted wrong confirmation (rc=%s)\n' "$RC"
  FAIL=$((FAIL+1))
  FAILED_NAMES+=( "pg-restore.sh rejects wrong confirmation" )
fi

# Usage error: no arg
bash "${SCRIPTS}/pg-restore.sh" </dev/null >/dev/null 2>&1
RC=$?
assert_eq "pg-restore.sh no-arg exits 2" "2" "$RC"

# Missing file: exit 2
bash "${SCRIPTS}/pg-restore.sh" "${TMPDIR_TEST}/does-not-exist.dump" </dev/null >/dev/null 2>&1
RC=$?
assert_eq "pg-restore.sh missing file exits 2" "2" "$RC"

echo
echo "== systemd units =="
assert "offsite service exists" \
  "test -f ${REPO_ROOT}/infra/deploy/systemd/voyagent-pg-backup-offsite.service"
assert "offsite timer exists" \
  "test -f ${REPO_ROOT}/infra/deploy/systemd/voyagent-pg-backup-offsite.timer"
assert "offsite timer schedules after local backup" \
  "grep -q '03:30' ${REPO_ROOT}/infra/deploy/systemd/voyagent-pg-backup-offsite.timer"

echo
echo "== summary =="
printf 'passed: %d\n' "$PASS"
printf 'failed: %d\n' "$FAIL"
if (( FAIL > 0 )); then
  printf 'failed tests:\n'
  for n in "${FAILED_NAMES[@]}"; do printf '  - %s\n' "$n"; done
  exit 1
fi
exit 0
