#!/usr/bin/env bash
#
# verify-secrets.sh — read-only check that a voyagent env file is sane.
#
# Usage:
#   ./verify-secrets.sh                    # defaults to /opt/voyagent/.env.prod
#   ./verify-secrets.sh /path/to/.env.foo
#
# Exit codes:
#   0   — all required secrets are set and pass the rules below
#   1   — at least one problem (printed to stderr)
#   2   — usage error / file not found
#
# Rules:
#   - every REQUIRED var must be present and non-empty
#   - no REQUIRED var may equal an obvious placeholder (changeme, your-key-here,
#     xxx, TODO, PLACEHOLDER, REPLACE_ME)
#   - VOYAGENT_AUTH_SECRET length must be >= 32 characters
#   - VOYAGENT_DB_URL must parse as a URL with scheme + host + user + password
#   - VOYAGENT_REDIS_URL must parse as a URL with scheme + host
#   - VOYAGENT_METRICS_TOKEN length must be >= 16 characters

set -euo pipefail

ENV_FILE="${1:-/opt/voyagent/.env.prod}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "verify-secrets: file not found: $ENV_FILE" >&2
  exit 2
fi

# Prefer python3, fall back to python (macOS/Windows/alpine-slim friendliness).
PY_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    # Reject the Windows "App Installer" stub that prints a message and exits 9009.
    if "$candidate" -c 'import sys' >/dev/null 2>&1; then
      PY_BIN="$candidate"
      break
    fi
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "verify-secrets: python3/python not found on PATH" >&2
  exit 2
fi

"$PY_BIN" - "$ENV_FILE" <<'PY'
import os, sys, re
from urllib.parse import urlsplit

path = sys.argv[1]
required = [
    "VOYAGENT_AUTH_SECRET",
    "VOYAGENT_DB_URL",
    "VOYAGENT_REDIS_URL",
    "VOYAGENT_METRICS_TOKEN",
    "VOYAGENT_KMS_KEY",
]
placeholders = {
    "", "changeme", "change-me", "your-key-here", "xxx", "todo",
    "placeholder", "replace_me", "replaceme", "example", "secret",
}

env = {}
with open(path, encoding="utf-8") as f:
    for raw in f:
        line = raw.rstrip("\n")
        if not line or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

problems = []

for key in required:
    if key not in env:
        problems.append(f"{key}: MISSING from {path}")
        continue
    val = env[key]
    if not val:
        problems.append(f"{key}: empty")
        continue
    if val.lower() in placeholders:
        problems.append(f"{key}: looks like a placeholder ({val!r})")
        continue

if "VOYAGENT_AUTH_SECRET" in env and env["VOYAGENT_AUTH_SECRET"] and env["VOYAGENT_AUTH_SECRET"].lower() not in placeholders:
    if len(env["VOYAGENT_AUTH_SECRET"]) < 32:
        problems.append(
            f"VOYAGENT_AUTH_SECRET: too short "
            f"({len(env['VOYAGENT_AUTH_SECRET'])} < 32 chars)"
        )

if "VOYAGENT_METRICS_TOKEN" in env and env["VOYAGENT_METRICS_TOKEN"] and env["VOYAGENT_METRICS_TOKEN"].lower() not in placeholders:
    if len(env["VOYAGENT_METRICS_TOKEN"]) < 16:
        problems.append(
            f"VOYAGENT_METRICS_TOKEN: too short "
            f"({len(env['VOYAGENT_METRICS_TOKEN'])} < 16 chars)"
        )

def check_url(key, require_userinfo):
    val = env.get(key, "")
    if not val or val.lower() in placeholders:
        return
    try:
        p = urlsplit(val)
    except Exception as exc:
        problems.append(f"{key}: not a valid URL ({exc})")
        return
    if not p.scheme:
        problems.append(f"{key}: missing URL scheme")
    if not p.hostname:
        problems.append(f"{key}: missing hostname")
    if require_userinfo:
        if not p.username:
            problems.append(f"{key}: missing user in URL")
        if not p.password:
            problems.append(f"{key}: missing password in URL")

check_url("VOYAGENT_DB_URL", require_userinfo=True)
check_url("VOYAGENT_REDIS_URL", require_userinfo=False)

if problems:
    print(f"verify-secrets: {len(problems)} problem(s) in {path}:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    sys.exit(1)

print(f"verify-secrets: OK ({len(required)} secrets checked in {path})")
PY
