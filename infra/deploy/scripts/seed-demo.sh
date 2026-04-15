#!/usr/bin/env bash
# One-shot seeder for the demo tenant. Idempotent — re-running is safe.
#
# This script is RUN MANUALLY from the deploy host, not from the
# deploy pipeline. It exists so an operator can bring up a fresh demo
# tenant after creating the demo user via the normal sign-up flow.
#
# Usage (on the deploy host):
#     sudo /opt/voyagent/repo/infra/deploy/scripts/seed-demo.sh
#     sudo /opt/voyagent/repo/infra/deploy/scripts/seed-demo.sh --dry-run
set -euo pipefail
cd /opt/voyagent/repo
set -a
. /opt/voyagent/.env.prod
set +a
.venv/bin/python tools/seed_demo.py "$@"
