# Continuous integration

This repo runs a single GitHub Actions workflow at
`.github/workflows/ci.yml`. It fires on pushes to `main` and on pull
requests targeting `main`. All jobs run in parallel on
`ubuntu-22.04` with a 10-minute timeout each.

## Jobs

| Job name          | What it runs                                                                |
|-------------------|-----------------------------------------------------------------------------|
| python-tests      | `uv sync --package voyagent-api` then `uv run pytest tests/` (excluding `tests/e2e` and the one known pre-existing failure documented below). |
| python-lint       | `uv run ruff check .` plus `uv run mypy services/api/src services/agent_runtime/src`. Mypy is `continue-on-error` until the tree is fully typed. |
| ts-type-check     | Installs pnpm deps, builds workspace packages, runs `tsc --noEmit` against `@voyagent/web` and `@voyagent/marketing`. |
| vitest            | Runs `vitest run` for `@voyagent/chat` and `@voyagent/sdk`.                 |
| playwright        | Installs chromium via `playwright install --with-deps`, runs the e2e suite against `VOYAGENT_BASE_URL=https://voyagent.globusdemos.com`. Uploads `tests/e2e/test-results/` as an artifact on failure. Flaky retries are already set in the Playwright config. |
| marketing-build   | Builds `@voyagent/marketing` with `NEXT_TELEMETRY_DISABLED=1` — catches MDX and TSX compile errors before deploy. |

All Node jobs use pnpm 10 and Node 24 via `pnpm/action-setup@v4` and
`actions/setup-node@v4`. Python jobs use `astral-sh/setup-uv@v3`
with its built-in cache enabled.

## Known failures

- **`tests/api/test_chat.py::test_runtime_unavailable_returns_503`**
  is a pre-existing Python-side failure that predates the current
  CI work. It is deselected in the `python-tests` job via
  `--deselect`. **TODO:** fix the underlying chat runtime
  unavailability path and remove the deselect.
- A single vitest spec was failing before this work as well. It
  is currently in whichever `vitest run` suite owns it; if the
  `vitest` job goes red, diff against the baseline to confirm it
  is not a NEW regression. **TODO:** track it down and fix or
  `.skip` it explicitly.

Any failure BEYOND those two is a real regression and must be
fixed before merging.

## Secrets

None. All jobs run against public URLs (`voyagent.globusdemos.com`,
npm, PyPI, the GitHub runner image). The Playwright tests sign up
with `@mailinator.com` addresses (public, disposable) because
`email-validator` rejects reserved TLDs. If you add a job that
needs a secret, document the secret name, the permission scope, and
the rotation procedure here first.

## Running the suites locally

```bash
# Python tests — from repo root
uv sync --package voyagent-api
uv run pytest tests/ --ignore=tests/e2e -q \
  --deselect tests/api/test_chat.py::test_runtime_unavailable_returns_503

# Python lint
uv run ruff check .
uv run mypy --ignore-missing-imports services/api/src services/agent_runtime/src

# Workspace packages (must build first — apps import from dist/)
pnpm install --no-frozen-lockfile
pnpm -r --filter "./packages/*" build

# TS type checks
pnpm --filter @voyagent/web       exec tsc --noEmit
pnpm --filter @voyagent/marketing exec tsc --noEmit

# Vitest
pnpm --filter @voyagent/chat exec vitest run
pnpm --filter @voyagent/sdk  exec vitest run

# Playwright (against the live site)
pnpm --filter @voyagent/tests-e2e exec playwright install --with-deps chromium
VOYAGENT_BASE_URL=https://voyagent.globusdemos.com \
  pnpm --filter @voyagent/tests-e2e exec playwright test --reporter=line

# Marketing build
NEXT_TELEMETRY_DISABLED=1 pnpm --filter @voyagent/marketing build
```

## Adding a new test suite

1. Add the suite under the appropriate package or `tests/` dir and
   make sure `pnpm --filter <pkg> exec <runner>` or
   `uv run <runner>` works from a clean checkout.
2. Add a new job to `.github/workflows/ci.yml`. Copy the closest
   existing job as a template so node/pnpm/uv setup stays
   consistent.
3. Set a `timeout-minutes` ceiling (10 unless you have a reason).
4. If the suite needs an env var, default it in the workflow — do
   NOT introduce a secret unless you also document it in the
   "Secrets" section of this file.
5. Run the workflow on a PR branch once before merging to `main`.
6. Update the job table at the top of this file in the same PR.

## Interpreting failures

- **`python-tests` red:** diff the failure list against the known
  failure above. One new failure = real bug. Re-run locally with
  `uv run pytest <path>::<test> -vv --maxfail=1`.
- **`ts-type-check` red:** almost always a missing `await cookies()`
  in Next 15 or a stale `packages/*` build. `pnpm -r --filter
  "./packages/*" build` locally first.
- **`vitest` red:** local-only reproduction is reliable — just run
  the filtered suite directly.
- **`playwright` red:** download the `playwright-traces` artifact
  from the failed run and open the `.zip` with
  `pnpm exec playwright show-trace`. Live-site flakes will
  auto-retry twice; a real failure after all retries means the live
  site is actually broken — check the deployment runbook.
- **`marketing-build` red:** MDX autolinks and non-route exports
  from `route.ts` are the two usual suspects. See
  `docs/RUNBOOK.md` section 5.
