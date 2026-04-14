# voyagent-driver-vfs

Reference implementation of `VisaPortalDriver` for VFS Global portals.
This is the **template** for every portal-based driver that ships on
top of `services/browser_runner/` — BLS International, embassy-direct
portals, airline extranets, and so on.

## What it is

A very thin adapter. Canonical method calls translate to
`BrowserRunnerClient.submit(...)` with the matching `JobKind`; the
runner does the actual Playwright work on a pooled browser context;
the returned `JobResult` maps back into canonical Voyagent types or
into a `DriverError` subclass via `errors.map_vfs_error`.

The driver carries **no Playwright code**. That is deliberate — the
runner owns the browser lifecycle so multiple portal drivers can share
one browser pool, one retry policy, and one artifact sink.

## Capability matrix

All capabilities are `"partial"` in the manifest. The reasons:

| Capability           | Why partial                                                                 |
| -------------------- | --------------------------------------------------------------------------- |
| `prepare_checklist`  | Scraped selectors vary by destination & category; tenant must supply a pack |
| `fill_form`          | Field IDs on VFS forms differ per country; driver trusts caller's selectors |
| `upload_document`    | Document is expected to be on the worker's local FS; materialisation TBD    |
| `book_appointment`   | Non-idempotent; VFS may return nearest-after-window rather than inside      |
| `read_status`        | Status text mapping is best-effort; unknown strings map to `IN_PROCESS`     |

When a tenant ships a real selector pack and negotiates automation
terms with VFS, individual capabilities can graduate to `"full"` on a
per-destination basis. The manifest exposes a `selector_pack_version`
hint in `tenant_config_schema` for that future.

## Selector overrides

Placeholder selectors live in
`services/browser_runner/src/voyagent_browser_runner/handlers/vfs_in.py`
(`_DEFAULT_SELECTORS`). A tenant-specific pack merges on top per
destination country via `SELECTOR_OVERRIDES[country_code]`. v0 leaves
the override mechanism as a module-level dict; v1 will load overrides
from the tenant configuration store at driver-construction time.

## Credentials

The driver never sees the raw username/password. It forwards
`config.credentials_ref` — an opaque string — to every job. The
worker's `CredentialResolver` is responsible for turning that
reference into concrete credentials inside the handler. The reference
travels through Redis in plain text and **must not be the secret
itself**; treat it like a cache key (e.g.
`secrets://vfs/<tenant_id>/default`).

## Error mapping

`errors.map_vfs_error` branches on substrings in the runner's error
string. It recognises:

* `client_timeout` / `job_timeout` / `deadline_exceeded` → `UpstreamTimeoutError`
* `captcha` → `PermanentError` (must be solved by a human)
* `login` / `auth` / `password` → `AuthenticationError`
* `no_slot` / `unavailable` → `ConflictError`
* `not found` / `404` → `NotFoundError`
* `validation` / `invalid` / `required` → `ValidationFailedError`
* `transient_retry` / `network` / `temporar` → `TransientError`
* anything else → `PermanentError`

Artifact URIs from the runner are attached to `vendor_ref` so ops can
pull up the screenshot + HTML snapshot directly from the exception.

## Integration status

The driver is registered by `build_default_registry()` in the agent
runtime when `VOYAGENT_VFS_USERNAME` is set or when a browser runner
is reachable. The `ticketing_visa` domain agent does **not** yet call
into it — a later pass adds the tool surface. For now the driver is
wired but dormant; this is intentional, and matches the phasing called
out in `docs/ARCHITECTURE.md` §Layer 2.

## Using from tests

```python
from drivers.vfs import VFSConfig, VFSDriver
from voyagent_browser_runner import BrowserRunnerClient, InMemoryJobQueue

queue = InMemoryJobQueue()
client = BrowserRunnerClient(queue)
driver = VFSDriver(client, VFSConfig())
```

A co-located `Worker` that pulls from the same `InMemoryJobQueue`
completes the round-trip — see `tests/drivers/vfs/test_driver.py` for
the full fixture shape.
