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
  identity. The API derives both from the JWT; these are only used as
  props by the chat component in local dev.

Vite inlines any `VITE_*` variable at build time. Rust-side secrets must
not be put here; put them in Tauri's runtime config instead.

## Tabs

The shell today has three tabs:

- **Chat** — live. Mounts `<ChatWindow>` from `@voyagent/chat` against a
  `VoyagentClient` built from the environment.
- **Reports** — placeholder. Will surface Tally-backed receivables,
  payables, and itinerary summaries once the local Tally sidecar ships.
- **Settings** — placeholder. Preferences, driver configuration, and
  account management land here.

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

The desktop shell uses Voyagent's in-house cookie/JWT auth. Desktop has
no HttpOnly cookies, so the access + refresh tokens live in a secure
local JSON blob written by the Rust side.

- `src/auth/VoyagentAuthClient.ts` — typed client over
  `/api/auth/sign-up`, `/api/auth/sign-in`, `/api/auth/me`,
  `/api/auth/refresh`, `/api/auth/sign-out`. Exposes `getAccessToken()`
  which transparently refreshes using the stored refresh token when the
  access JWT is close to expiry or rejected with 401.
- `src/auth/tokenStore.ts` — typed wrapper over the Rust-side
  `voyagent_store_session` / `voyagent_load_session` /
  `voyagent_clear_session` commands, which persist the session blob
  under the app's local data directory (permissions tightened to 0600
  on POSIX; ACL-protected AppData\\Local on Windows).
- `src/auth/AuthProvider.tsx` — React context; rehydrates the stored
  session on mount and exposes `getToken`, `signIn`, `signUp`,
  `signOut`.
- `src/auth/SignInScreen.tsx` — plain email/password form, with a
  toggle to the sign-up variant (email, password, full name, agency
  name).

`src/sdk.ts` builds the `VoyagentClient` with an `authToken` getter
that pulls a fresh JWT via `VoyagentAuthClient.getAccessToken()` on
every API call.

Environment — copy `.env.example` to `.env` and set
`VITE_VOYAGENT_API_URL` to the Voyagent FastAPI base URL.

## Production build

### Icons

The bundler reads `bundle.icon` in `tauri.conf.json`. Generate the full
set from a 1024×1024 master PNG:

```bash
pnpm tauri icon path/to/voyagent-1024.png
```

See `src-tauri/icons/README.md` for the expected filenames.

### Code signing

macOS and Windows signing are stubbed in `tauri.conf.json` under
`bundle.macOS` / `bundle.windows`. Populate them in CI — do NOT commit
signing certificates. The expected env vars consumed by `tauri build`
are:

- `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`,
  `APPLE_PASSWORD`, `APPLE_TEAM_ID` — macOS signing + notarisation.
- `WINDOWS_CERTIFICATE` (base64 PFX), `WINDOWS_CERTIFICATE_PASSWORD` —
  Windows Authenticode.

### Auto-updater

`tauri-plugin-updater` is registered in `src-tauri/src/main.rs`; the
TS surface is `src/Updater.tsx`, which calls the `check_for_updates`
command on mount (throttled once per 24 h). Before shipping:

1. Generate a signing key pair:
   ```bash
   pnpm tauri signer generate -w ~/.tauri/voyagent-updater.key
   ```
2. Paste the public key into `plugins.updater.pubkey` in
   `tauri.conf.json`.
3. Expose the private key to CI as `TAURI_SIGNING_PRIVATE_KEY` +
   `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.
4. Host a `latest.json` manifest at the configured endpoint; the
   build step emits `*.sig` files CI concatenates into the manifest.

## Known limitations

- No biometric unlock gate before reading the stored session token.
- No Tally or GDS driver yet; `local_driver_invoke` is a stub.
- Icon bundle (`src-tauri/icons/`) placeholder — run
  `pnpm tauri icon <path-to-png>` once brand art lands.
- Code-signing certificates must be provisioned out of band.
- Updater manifest endpoint + signer key pair are human-owned steps.

## Scripts

- `pnpm --filter @voyagent/desktop dev` — Vite only, no Tauri window
- `pnpm --filter @voyagent/desktop build` — Vite production build
- `pnpm --filter @voyagent/desktop tauri dev` — full desktop dev loop
- `pnpm --filter @voyagent/desktop tauri build` — ship a binary
- `pnpm --filter @voyagent/desktop lint` — `tsc --noEmit`
- `pnpm --filter @voyagent/desktop clean` — wipe `dist/` and Rust target
