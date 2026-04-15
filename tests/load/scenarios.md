# Voyagent load-test scenarios

These scenarios are intentionally shallow — the goal is to catch regressions
in the HTTP + Postgres + auth layers, not to benchmark the LLM.

## Scenario A — 20-user smoke

**Purpose:** quick regression check that can run on any feature branch.

```bash
locust -f tests/load/locustfile.py \
  --users 20 --spawn-rate 2 --run-time 2m --headless \
  --host https://voyagent.globusdemos.com
```

**Expected baseline (chrome-desktop hitting voyagent.globusdemos.com):**

| Metric              | Target      |
| ------------------- | ----------- |
| p50 latency (reads) | < 150 ms    |
| p95 latency (reads) | < 500 ms    |
| p99 latency (reads) | < 1 s       |
| Error rate          | < 0.5 %     |
| 429s (rate-limit)   | 0           |

`locustfile.py` asserts p95 < 500 ms at shutdown, so this budget is
enforced automatically — if it regresses, the run exits non-zero.

## Scenario B — 100-user baseline

**Purpose:** what we expect under normal production load for a mid-sized
agency tenant (5 concurrent power-users × ~20 agencies).

```bash
locust -f tests/load/locustfile.py \
  --users 100 --spawn-rate 5 --run-time 10m --headless \
  --host https://voyagent.globusdemos.com
```

**Expected baseline:**

| Metric              | Target      |
| ------------------- | ----------- |
| p50 latency         | < 200 ms    |
| p95 latency         | < 900 ms    |
| p99 latency         | < 2 s       |
| Error rate          | < 1 %       |
| 429s                | Acceptable, but should recover to 0 within the run window |

Run this across **multiple locust workers** on one box
(`locust --processes 4`) so a single Python GIL doesn't become the
bottleneck and hide real server-side limits.

## What to watch

During the run:

* **p50 / p95 / p99** — the headline latency numbers.
* **Error rate** — separate 4xx from 5xx. 429s are expected under burst;
  5xx are always a real bug.
* **Rate-limit-exceeded count** — how often the slowapi limiter fires.
* **Database connection pool** — watch `services/api` logs for
  `QueuePool limit ... overflow` warnings.

## Known bottlenecks (as of v0)

* **Single-process FastAPI** — the production deployment runs one uvicorn
  worker. Bumping to `--workers 4` should give ~4× headroom.
* **Single agent-runtime instance** — chat message throughput is gated by
  the one agent-runtime sidecar process. Not exercised by the default
  locust tasks (we skip chat message POSTs on purpose).
* **Audit log writes** — every authed write hits the audit table. Under
  sustained write load the audit insert becomes the hot path.
* **JWT verify on every request** — no session cache. Each request
  decodes + verifies the bearer token.

## Where to send results

Stash the locust HTML report under `tests/load/results/<date>-<scenario>/`
and cross-reference the commit SHA in the filename. We want a history of
these numbers — not just the latest snapshot.
