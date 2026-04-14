# voyagent-driver-bsp-india

Voyagent driver for **IATA BSP India** — the Indian instance of IATA's
Billing and Settlement Plan. Implements
`drivers._contracts.bsp.BSPDriver` (partial; see matrix below).

## What BSP is, briefly

BSP is IATA's global settlement scheme: airlines bill participating
travel agents through a single statement per country and period,
instead of each agent reconciling with each airline bilaterally. Agents
download a **HAF (Host-to-Agent File)** — a fixed-position text file
defined by IATA RAM Resolution 812g — compare it against their internal
sales, raise ADMs/ACMs for discrepancies, and remit the net amount to
IATA by the settlement deadline.

BSP India runs a **fortnightly** settlement cycle. Other countries
differ: BSP UK is weekly, BSP UAE is fortnightly with different
weekday cut-offs, BSP Singapore is monthly, and so on. **Voyagent
models each country BSP as its own driver.** There is no shared "BSP"
driver — the file formats, portal endpoints, and memo workflows differ
enough that coupling them saves nothing and costs a lot.

## Capability matrix

| Capability                 | Support level     | Notes                                                                                       |
| -------------------------- | ----------------- | ------------------------------------------------------------------------------------------- |
| `fetch_statement`          | `full` / `not_supported` | `full` when `file_source_dir` is configured (local HAF drop). Without it the HTTP path is a scaffold that always raises. |
| `raise_adm`                | `not_supported`   | BSPlink ADM submission is a stateful web-form workflow; deferred to a later release.         |
| `raise_acm`                | `not_supported`   | Same as ADM.                                                                                 |
| `make_settlement_payment`  | `not_supported`   | Settlement payments use the tenant's bank rail. Route through a `BankDriver`.                |

The driver rejects any `country` other than `"IN"` with
`ValidationFailedError`; call the correct country's BSP driver instead.

## HAF record types supported in v0

| Code    | Meaning                             | Maps to                                    |
| ------- | ----------------------------------- | ------------------------------------------ |
| `BFH01` | File Header                         | `BSPReport.country/period/currency`        |
| `BKS24` | Agent Ticketing Record (sale)       | `BSPTransaction(kind=SALE)`                |
| `BKS39` | Refund Record                       | `BSPTransaction(kind=REFUND)`              |
| `BKS45` | Exchange / Reissue Record           | `BSPTransaction(kind=REFUND)` (see note)   |
| `BKS46` | Agency Debit Memo (ADM) Record      | `BSPTransaction(kind=ADM)`                 |
| `BKS47` | Agency Credit Memo (ACM) Record     | `BSPTransaction(kind=ACM)`                 |
| `BFT99` | File Trailer                        | record count + control total validation    |

Record codes outside this list are logged at `DEBUG` and skipped — the
file parses as long as its header and trailer are present.

Note on exchanges: `BKS45` is treated as a refund-shaped canonical
transaction in v0. A future pass can split exchanges out cleanly once
`BSPTransactionKind.EXCHANGE` exists; today the canonical enum does not
include one.

## Configuration

Environment variables, prefix `VOYAGENT_BSP_INDIA_`:

| Key                | Default                              | Notes                                                               |
| ------------------ | ------------------------------------ | ------------------------------------------------------------------- |
| `BSPLINK_BASE_URL` | `https://www.bsplink.iata.org`       | Scaffolded; HTTP path always raises in v0.                           |
| `AGENT_IATA_CODE`  | —                                    | Required. Tenant's IATA agency code.                                 |
| `USERNAME`         | —                                    | BSPlink username (used only once the HTTP path lands).              |
| `PASSWORD`         | —                                    | BSPlink password (held in `SecretStr`).                              |
| `FILE_SOURCE_DIR`  | —                                    | If set, HAF files are read from this directory instead of fetched.   |
| `TIMEOUT_SECONDS`  | `60`                                 | Per-request HTTP timeout (scaffolded HTTP path).                     |
| `MAX_RETRIES`      | `2`                                  | Retries on `TransientError`.                                         |

## File drop convention

With `FILE_SOURCE_DIR=/var/voyagent/bsp_india/`, the driver looks for:

```
HAF_<AGENT_IATA>_<YYYYMMDD>_<YYYYMMDD>.txt
```

If the exact name isn't present it falls back to any file whose name
contains both period dates. Use this when your ops stack drops HAF
files via SFTP or email into a shared directory.

## Reconciliation rules (`reconcile_bsp_against_tickets`)

Matching is deterministic — no LLM. For each `BSPTransaction` of kind
`SALE`:

1. Normalise ticket numbers to `(airline_code, last-10-digits)`.
   This collapses `176-1234567890`, `1761234567890`, and a bare
   `1234567890` + airline into one key.
2. Look up a Voyagent `Ticket` by that key.
3. Compare amounts; within ±`AMOUNT_TOLERANCE` (INR 1 by default) is
   `MATCHED`, otherwise `DISCREPANCY` with a signed `delta = external
   - internal`.
4. Currency mismatch downgrades the match to `TENTATIVE` — operators
   must resolve FX posture before accepting.

`UNMATCHED_EXTERNAL` catches transactions BSP billed that Voyagent has
no record of (often off-platform sales). `UNMATCHED_INTERNAL` catches
Voyagent tickets that BSP has not billed this period (usually a
fortnight-cut-off timing issue).

### Known limitations

- **Refunds and exchanges are not auto-matched.** `BKS39` and `BKS45`
  rows always surface as `UNMATCHED_EXTERNAL` in v0 so an accountant
  reviews them manually. A v1 pass will link them to the original
  ticket via `original_ticket_number`.
- **ADM/ACM memos** also surface as `UNMATCHED_EXTERNAL` pending
  review.
- **No fuzzy matching.** `TENTATIVE` is reserved for currency
  mismatches today; a fuzzy name/date matcher is a v1 concern.
- **AMOUNT_TOLERANCE** is a flat ±1 unit of the statement currency.
  Chart-of-accounts-level tolerances (per airline, per route) are
  not configurable yet.

## Settlement cycles differ per country

Voyagent treats the settlement cycle as BSP-driver-local state:

- **India** — fortnightly (two periods per month; exact cut-offs on
  IATA's published calendar).
- **UK** — weekly.
- **UAE** — fortnightly, different weekdays than India.
- **Singapore** — monthly.
- **US (ARC, not BSP)** — weekly but separate plan entirely.

The `Period` on every call is the agent's choice; the driver does not
enforce cycle boundaries — HAF files themselves encode the true period
in their header, and the report reflects what the file says.

## Adding a new BSP driver

Mirror this package's layout for `drivers/bsp_uae`, `drivers/bsp_uk`,
etc.:

- Keep the country-scoped constant (`_SUPPORTED_COUNTRY = "AE"`, etc.)
  and reject any other country argument with `ValidationFailedError`.
- Author a country-specific `haf_parser.py` + `haf_records.py` — BSP's
  fixed-position formats vary per country even though they share a
  common IATA base.
- Write the mapper against the same canonical types (`BSPReport`,
  `BSPTransaction`) so the orchestrator can route
  `fetch_statement` + `reconcile_bsp` uniformly across tenants.
- Declare capabilities honestly in the manifest — `partial`,
  `not_supported`, and driver-defined tags like
  `supported_via_sftp_drop` are all first-class in the orchestrator.
- **Do not** try to share code at the driver level. Reuse happens at
  the canonical model and the reconciliation mapper, not at the HAF
  parser.

## Known gaps (v0)

- No ADM / ACM submission.
- No direct BSPlink HTTP download (scaffolded).
- No FX / multi-currency HAF handling — BSP India is single-currency
  (INR) today, so this is safe, but a future pass is needed if IATA
  changes that.
- No partial reconciliation over long periods — one HAF file per call.
- No file signature / checksum verification beyond the BFT99 control
  total (not currently compared against the sum of parsed lines).
