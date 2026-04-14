# voyagent-driver-tally

Voyagent reference driver for **Tally Prime** via the Tally Gateway Server
(XML over HTTP, default `localhost:9000`). Implements
`drivers._contracts.accounting.AccountingDriver`.

This is Voyagent's second reference driver and the canonical template for
desktop-bound accounting backends (Busy, Marg, older ERP stacks). For a
pure-REST reference, see `drivers/amadeus/`.

## What it implements

| Capability              | Level                       | Notes                                                                                     |
| ----------------------- | --------------------------- | ----------------------------------------------------------------------------------------- |
| `list_accounts`         | `full`                      | Uses the built-in `List of Ledgers` TDL collection with a `FETCH` over the used fields.    |
| `post_journal`          | `supported_via_xml_import`  | Builds an `IMPORTDATA` envelope with one `VOUCHER VCHTYPE="Journal" ACTION="Create"`.      |
| `create_invoice`        | `supported_via_xml_import`  | Same shape, `VCHTYPE="Sales"`. No inventory (`STOCKITEM`) support in v0.                   |
| `read_invoice`          | `not_supported`             | Tally has no stable external-id lookup; requires a UDF-based TDL report (future work).     |
| `read_account_balance`  | `partial`                   | V0 raises `CapabilityNotSupportedError`; the opening-balance case is stubbed for future.   |

## Desktop-bound

The manifest advertises `requires=["desktop_host", "tenant_credentials"]`.
The driver can only run on a host that can reach `localhost:9000` of a
running Tally Prime with the Gateway Server enabled. Cloud-only workers
must not schedule this driver.

## Setup

1. Install Tally Prime on the desktop host.
2. Enable the gateway: `F1 (Help) → Settings → Connectivity → Client/Server → Tally.ERP Server`, then set `Port = 9000`.
3. Open the company you want Voyagent to post into. **The company must be
   open at the time of each request** — Tally returns a gateway error
   ("Company ... not open") otherwise, which the driver maps to
   `ConflictError`.
4. (Optional, Tally Prime ~3.x+.) Enable HTTP basic auth on the gateway
   server and set `VOYAGENT_TALLY_BASIC_AUTH_USER` /
   `VOYAGENT_TALLY_BASIC_AUTH_PASSWORD` accordingly.

## Configuration

Environment variables, prefix `VOYAGENT_TALLY_`:

| Key                  | Default                 | Notes                                                         |
| -------------------- | ----------------------- | ------------------------------------------------------------- |
| `GATEWAY_URL`        | `http://localhost:9000` | Gateway base URL.                                             |
| `COMPANY_NAME`       | —                       | Required. Exact name from Tally's 'List of Companies'.        |
| `TIMEOUT_SECONDS`    | `30`                    | Per-request HTTP timeout.                                     |
| `MAX_RETRIES`        | `2`                     | Applied on `TransientError` / network errors.                 |
| `BASIC_AUTH_USER`    | —                       | Optional HTTP basic auth user.                                |
| `BASIC_AUTH_PASSWORD`| —                       | Optional basic auth password (held in `SecretStr`).           |

## The sign-convention landmine

Tally's `ISDEEMEDPOSITIVE` field is the opposite of the more common
accountant convention:

- `ISDEEMEDPOSITIVE=Yes` on a line means *"this amount behaves as a debit
  for the ledger's natural side"*, with the amount encoded as a
  **negative** value.
- `ISDEEMEDPOSITIVE=No` on a line is the **credit** half, with a
  **positive** amount.

The driver maps canonical `JournalLine.debit` to
`ISDEEMEDPOSITIVE=Yes` + negative amount, and canonical
`JournalLine.credit` to `ISDEEMEDPOSITIVE=No` + positive amount. This is
the widely-documented Tally convention for journal vouchers and matches
what most open-source Tally SDKs emit — but **it is not the only
convention that exists in the wild**. Some integrations flip the signs
for sales vouchers with tax lines, for example. **Verify against your
own chart of accounts before relying on automated posting** — run a
small test voucher, inspect it inside Tally, and compare the produced
T-account movements against expectation.

## Mapping ledger parent groups to `AccountType`

See `mapping._PARENT_TO_TYPE`. Assets-side, liabilities-side, equity,
income, and expense groups from a vanilla Tally chart are recognised by
name. Unknown parents fall through to `EXPENSE` with a `WARNING` log —
not silently. If your tenant has custom parent groups, extend
`_PARENT_TO_TYPE` rather than editing calling code.

## Extending to Zoho / Busy / QuickBooks Online

Use `drivers/tally/mapping.py` as the template for any new accounting
driver:

- Keep XML/JSON building in a `*_builder.py`, parsing in a
  `*_parser.py`. Never hand-concatenate wire formats.
- Write pure canonical↔vendor mappers; never do I/O in the mapper.
- Surface every failure mode through the standard `DriverError`
  hierarchy — the orchestrator classifies retries and approval
  escalation off this hierarchy.
- Declare desktop-only behaviour through `requires=["desktop_host"]` in
  the manifest. Be honest about partial capabilities; `partial` is a
  first-class level the orchestrator can degrade on.

## Known gaps

- `read_invoice` is unimplemented. A TDL report keyed off a UDF written
  during `create_invoice` would enable this.
- `read_account_balance` is unimplemented even for the opening-balance
  case; requires plumbing a canonical-id→Tally-ledger-name lookup. The
  driver already declares `partial` in its manifest — orchestrator can
  degrade.
- Inventory-mode Sales vouchers (`STOCKITEM`) are not supported.
  Tenants that run Tally in inventory mode will need a richer mapping.
- No multi-company support in a single driver instance — the Tally
  gateway binds to one company at a time. Run one driver per company.
- No ODBC transport (port 9000 ODBC interface) — only `http_xml`.
