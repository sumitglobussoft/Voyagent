#!/usr/bin/env bash
#
# test_verify_secrets.sh — assertions for infra/deploy/scripts/verify-secrets.sh
#
# Run: bash tests/infra/test_verify_secrets.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${REPO_ROOT}/infra/deploy/scripts/verify-secrets.sh"

PASS=0
FAIL=0
FAILED=()

assert_rc() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    printf '  ok   %s\n' "$name"
    PASS=$((PASS+1))
  else
    printf '  FAIL %s (expected rc=%s got rc=%s)\n' "$name" "$expected" "$actual"
    FAIL=$((FAIL+1))
    FAILED+=( "$name" )
  fi
}

if [[ ! -f "$SCRIPT" ]]; then
  echo "missing script: $SCRIPT" >&2
  exit 1
fi

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

GOOD="${TMPDIR_TEST}/good.env"
cat >"$GOOD" <<'EOF'
# voyagent prod env (test fixture)
VOYAGENT_AUTH_SECRET=abcdefghijklmnopqrstuvwxyz0123456789ABCDEF
VOYAGENT_DB_URL=postgresql://voyagent:s3cretPassword123@127.0.0.1:5432/voyagent
VOYAGENT_REDIS_URL=redis://:redispassword@127.0.0.1:6379/0
VOYAGENT_METRICS_TOKEN=metrics-token-long-enough-1234
VOYAGENT_KMS_KEY=kms-key-value-abcdef123456
EOF

bash "$SCRIPT" "$GOOD" >/dev/null 2>&1
assert_rc "all good -> exit 0" "0" "$?"

# Missing var
MISSING="${TMPDIR_TEST}/missing.env"
grep -v '^VOYAGENT_KMS_KEY' "$GOOD" > "$MISSING"
bash "$SCRIPT" "$MISSING" >/dev/null 2>&1
assert_rc "missing VOYAGENT_KMS_KEY -> exit 1" "1" "$?"

# Placeholder
PLACE="${TMPDIR_TEST}/place.env"
sed 's|^VOYAGENT_AUTH_SECRET=.*|VOYAGENT_AUTH_SECRET=changeme|' "$GOOD" > "$PLACE"
bash "$SCRIPT" "$PLACE" >/dev/null 2>&1
assert_rc "VOYAGENT_AUTH_SECRET=changeme -> exit 1" "1" "$?"

# Too short
SHORT="${TMPDIR_TEST}/short.env"
sed 's|^VOYAGENT_AUTH_SECRET=.*|VOYAGENT_AUTH_SECRET=short|' "$GOOD" > "$SHORT"
bash "$SCRIPT" "$SHORT" >/dev/null 2>&1
assert_rc "short VOYAGENT_AUTH_SECRET -> exit 1" "1" "$?"

# Empty value
EMPTY="${TMPDIR_TEST}/empty.env"
sed 's|^VOYAGENT_METRICS_TOKEN=.*|VOYAGENT_METRICS_TOKEN=|' "$GOOD" > "$EMPTY"
bash "$SCRIPT" "$EMPTY" >/dev/null 2>&1
assert_rc "empty VOYAGENT_METRICS_TOKEN -> exit 1" "1" "$?"

# Malformed DB URL (no password)
BADDB="${TMPDIR_TEST}/baddb.env"
sed 's|^VOYAGENT_DB_URL=.*|VOYAGENT_DB_URL=postgresql://voyagent@127.0.0.1:5432/voyagent|' "$GOOD" > "$BADDB"
bash "$SCRIPT" "$BADDB" >/dev/null 2>&1
assert_rc "VOYAGENT_DB_URL missing password -> exit 1" "1" "$?"

# File not found
bash "$SCRIPT" "${TMPDIR_TEST}/nope.env" >/dev/null 2>&1
assert_rc "nonexistent file -> exit 2" "2" "$?"

# Short metrics token
SHORTM="${TMPDIR_TEST}/shortm.env"
sed 's|^VOYAGENT_METRICS_TOKEN=.*|VOYAGENT_METRICS_TOKEN=abc|' "$GOOD" > "$SHORTM"
bash "$SCRIPT" "$SHORTM" >/dev/null 2>&1
assert_rc "short VOYAGENT_METRICS_TOKEN -> exit 1" "1" "$?"

echo
echo "== summary =="
printf 'passed: %d\n' "$PASS"
printf 'failed: %d\n' "$FAIL"
if (( FAIL > 0 )); then
  printf 'failed tests:\n'
  for n in "${FAILED[@]}"; do printf '  - %s\n' "$n"; done
  exit 1
fi
exit 0
