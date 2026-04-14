# @voyagent/desktop

Voyagent's desktop shell — a Tauri 2 application with a Vite + React
frontend. This is the heavy client that hosts drivers that need local
OS access (Tally ODBC, GDS terminals, smart-card readers, thermal
printers).

## Prerequisites

- Node 20+
- pnpm 9+
- Rust toolchain (`rustup`, `cargo`) — Tauri compiles a native binary
- Platform build deps per Tauri's [prerequisites guide](https://tauri.app/start/prerequisites/):
  - Windows: Microsoft Visual Studio C++ Build Tools + WebView2 (usually preinstalled)
  - macOS: Xcode Command Line Tools
  - Linux: `webkit2gtk`, `libgtk-3`, `libayatana-appindicator3`, `librsvg2`

## Running

From the repo root:

```bash
# Install workspace deps (once)
pnpm install

# Start the desktop shell (Vite + Tauri dev window)
pnpm --filter @voyagent/desktop tauri dev
```

`tauri dev` boots Vite on http://localhost:5173 and opens a native window
that loads it. Hot reload works for the React side; changes to Rust
trigger an incremental `cargo build`.

To build a shippable binary:

```bash
pnpm --filter @voyagent/desktop tauri build
```

Artifacts land in `src-tauri/target/release/bundle/`.

## Environment

Copy `.env.example` to `.env` and adjust:

- `VITE_VOYAGENT_API_URL` — the Voyagent FastAPI backend.
- `VITE_VOYAGENT_TENANT_ID`, `VITE_VOYAGENT_ACTOR_ID` — dev-time session
  identity. These go away once Clerk auth is wired in (see below).

Vite inlines any `VITE_*` variable at build time. Rust-side secrets must
not be put here; put them in Tauri's runtime config instead.

## Tabs

The shell today has three tabs:

- **Chat** — live. Mounts `<ChatWindow>` from `@voyagent/chat` against a
  `VoyagentClient` built from the environment.
- **Reports** — placeholder. Will surface Tally-backed receivables,
  payables, and itinerary summaries once the local Tally sidecar ships.
- **Settings** — placeholder. Preferences, driver configuration, and
  account management land here alongside Clerk auth.

## Local driver bridge

Files:

- `src/local-driver-bridge.ts` — TS wrapper over Tauri's `invoke()`.
- `src-tauri/src/commands/local_driver.rs` — the `local_driver_invoke`
  command (v0 stub).

The bridge is the single seam through which the web layer reaches into
OS-resident drivers. In v0 the Rust side returns
`{ status: "not_wired_yet", ... }` so we can exercise the full call path
without any real driver wiring. In v1 it dispatches on `driver` and
delegates to per-driver modules — Tally XML-over-HTTP is the first
consumer.

When the cloud runtime emits a tool call targeting a "local" driver,
the chat stream will include a directive the shell routes through this
bridge, so that local drivers run inside Tauri rather than in the cloud
runtime. Keep this boundary clean — do not import Tauri APIs from inside
`@voyagent/chat` or `@voyagent/sdk`.

## Auth

Not wired yet. A concurrent agent is landing Clerk integration for the
web app first; the desktop shell will follow with `@clerk/clerk-react`
plus a Tauri deep-link handler for the OAuth redirect. Until then the
shell boots with a dev tenant and actor from the environment (see
`src/sdk.ts`).

## Known limitations

- No auto-update (Tauri updater plugin not configured).
- No code signing — release bundles will trigger OS Gatekeeper /
  SmartScreen warnings.
- No Tally or GDS driver yet; `local_driver_invoke` is a stub.
- Icon bundle (`src-tauri/icons/`) not generated — `tauri build` will
  complain until you run `pnpm tauri icon <path-to-png>`.

## Scripts

- `pnpm --filter @voyagent/desktop dev` — Vite only, no Tauri window
- `pnpm --filter @voyagent/desktop build` — Vite production build
- `pnpm --filter @voyagent/desktop tauri dev` — full desktop dev loop
- `pnpm --filter @voyagent/desktop tauri build` — ship a binary
- `pnpm --filter @voyagent/desktop lint` — `tsc --noEmit`
- `pnpm --filter @voyagent/desktop clean` — wipe `dist/` and Rust target
