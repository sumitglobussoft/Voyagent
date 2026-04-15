# Voyagent load tests

Basic Locust scenarios to catch HTTP/Postgres/auth-layer regressions.
We do **not** load-test the agent runtime itself — LLM cost and latency
jitter make that unproductive in CI.

## Install

Locust is not a project dependency. It's a runtime tool, install it
standalone:

```bash
uv tool install locust
```

Verify:

```bash
locust --version
```

## Run the 20-user smoke

```bash
VOYAGENT_BASE_URL=https://voyagent.globusdemos.com \
VOYAGENT_DEMO_EMAIL=demo@voyagent.globusdemos.com \
VOYAGENT_DEMO_PASSWORD=DemoPassword123! \
locust -f tests/load/locustfile.py \
  --users 20 --spawn-rate 2 --run-time 2m --headless \
  --host $VOYAGENT_BASE_URL
```

If the demo credentials are missing/invalid, the load user falls back to
signing up a fresh `load-<random>@mailinator.com` tenant so the run still
proceeds — you will just see different names in the stats.

## Expected baselines

See [`scenarios.md`](./scenarios.md) for the full rubric. The short
version: **p95 < 500 ms** for the 20-user smoke, and the locustfile
exits non-zero if that is exceeded.

## Results

Stash the locust HTML report under `tests/load/results/<date>-<scenario>/`
with the commit SHA in the directory name so we can build a regression
history over time.

## Why this lives outside CI

These scenarios hit the live demo deployment. Running them on every
PR would:

1. Pollute the demo tenant with load-test artifacts.
2. Make PR latency wildly dependent on demo-server weather.
3. Blow the CI minute budget.

Run them manually before a release, or wire them to a scheduled GitHub
Actions job (daily / weekly).
