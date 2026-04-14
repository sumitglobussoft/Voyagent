# voyagent-browser-runner

A Playwright-based worker service that executes browser-automation jobs
on behalf of portal drivers (VFS Global, BLS International, embassy
portals, airline extranets). It is deliberately isolated from the agent
runtime so browser sessions can be pooled, retried, and restarted
without touching the rest of the system.

## When to use it

Voyagent prefers real APIs. Some systems — notably visa portals and a
few airline/supplier extranets — publish none. For those, the only
honest path is browser automation; this service is where that
automation lives.

If a vendor *does* have an API, integrate via a normal driver
(`drivers/<vendor>/`) and do not route through this service.

## Running locally

```bash
# Boot the worker loop (consumes VOYAGENT_BROWSER_* env vars).
uv run voyagent-browser-runner worker

# Ad-hoc: submit a single job for debugging.
uv run voyagent-browser-runner submit \
  --kind vfs.read_status \
  --tenant-id 018f1a2b-3c4d-7e5f-8abc-0123456789ab \
  --credentials-ref secrets://vfs/dev \
  --inputs '{"application_ref":"EX-001","destination_country":"GB"}'
```

The default `VOYAGENT_BROWSER_REDIS_URL` is `redis://localhost:6379/1`
(DB 1 to avoid colliding with the offer cache on DB 0). Bring Redis up
with `infra/docker/dev.yml`.

## Job lifecycle

```
driver ── BrowserRunnerClient.submit ─────────────► RedisJobQueue.enqueue
                                                           │
                                                           ▼
                                                    worker loop BLPOP
                                                           │
                                                           ▼
                                         deadline check / handler lookup
                                                           │
                                              BrowserPool.acquire(tenant)
                                                           │
                                                           ▼
                                               handler runs (vfs_in.py)
                                                           │
                                     ┌─────────────────────┼─────────────┐
                                     ▼                     ▼             ▼
                                 success              transient        permanent
                               JobResult              retry up to       JobResult
                                                      retry_limit        failed
                                                                           │
                                                                 capture_failure
                                                                  (screenshot + HTML)
                                                                           │
                                                                 put_result
                                                                           │
                               ┌───────────────────────────────────────────┘
                               ▼
                      RedisJobQueue.wait_for_result  (polled by driver)
```

Every failure — transient or permanent — runs `capture_failure`, which
writes a full-page screenshot + an HTML snapshot to the configured
artifact sink. The URIs are attached to the resulting `JobResult`; the
driver surfaces them on the `DriverError.vendor_ref` so ops has
something to look at.

## Session survival

`BrowserPool` keys contexts by `(tenant_id, handler_namespace)`. A VFS
login is expensive (and sometimes CAPTCHA-gated); re-using the context
across jobs for the same tenant avoids re-authenticating for every
step. Contexts idle for longer than
`VOYAGENT_BROWSER_CONTEXT_IDLE_EVICTION_SECONDS` (default 10 min) are
evicted.

Cross-tenant isolation is absolute — a context is never shared across
tenants.

## Adding a new portal

1. **Enumerate the kinds.** Add values to `JobKind` in `job.py` under a
   new namespace, e.g. `"bls.checklist_prepare"`.
2. **Write handlers.** Create `handlers/<portal>.py` exporting
   `async def handle_<kind>(ctx: HandlerContext) -> dict`. Use the
   primitives in `steps.py` — they give you masked logging and
   consistent failure artifacts for free.
3. **Register them.** Extend `_register_builtins()` in
   `handlers/__init__.py` to map each new kind to its handler.
4. **Supply a selector pack.** Place placeholders per the VFS pattern
   and let tenants override them via a per-destination dict. Real
   selectors are tenant configuration, not code — portals change
   layouts, and a production deployment ships a signed selector pack
   separately from the worker image.

## Artifact guarantee

If a handler raises *anything*, the worker:

1. Re-acquires the tenant's browser context,
2. Takes a full-page screenshot and captures `page.content()`,
3. Uploads both to the configured `ArtifactSink` under
   `<tenant_id>/<job_id>/failure-<exception>.{png,html}`,
4. Attaches the resulting URIs to the `JobResult.artifact_uris`.

Drivers must treat those URIs as opaque blobs — the driver layer does
not interpret bucket names or path structure.

## Disclaimer

Selectors and URLs in `handlers/vfs_in.py` are **placeholders**. They
are not real VFS endpoints. Every line starts with a `# PLACEHOLDER:`
comment so no reviewer mistakes them for a working integration.

Automating a portal that forbids automation is not this product's
intent. Voyagent supports tenant-initiated, supervised flows where the
tenant has a legitimate automation agreement (or is operating their
own portal, or is running against a sandbox). Enforcement of that
agreement is the tenant's responsibility; the runner does not attempt
CAPTCHA bypass, impersonation of a real browser beyond what Playwright
does out of the box, or evasion of rate limits. Deploy accordingly.
