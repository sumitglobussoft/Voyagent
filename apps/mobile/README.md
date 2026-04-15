# @voyagent/mobile

Voyagent's mobile app — an Expo + React Native skeleton. The mobile
surface is intentionally lightweight: **reports** for travel agents on
the go, and **remote-control relay** for a signed-in Voyagent desktop
session. Heavy workflows stay on the desktop.

## Prerequisites

- Node 20+
- pnpm 9+
- Expo CLI is invoked via `pnpm exec expo` — no global install required.
- For device testing: Expo Go on your phone, or Android Studio / Xcode
  simulators if you want to run a dev client.

## Running

From the repo root:

```bash
pnpm install
pnpm --filter @voyagent/mobile start
```

That prints a QR code. Scan it with Expo Go (same Wi-Fi network), or
press `a` / `i` in the terminal to launch an Android / iOS simulator.

## Running on a device

First-time setup, from the repo root:

```bash
# Install the full workspace (mobile pulls @voyagent/{core,sdk,chat}).
pnpm install

# The mobile app consumes built type declarations from the workspace
# packages, so build them once:
pnpm --filter @voyagent/core --filter @voyagent/sdk --filter @voyagent/chat run build

# Optional: type-check the mobile app.
pnpm --filter @voyagent/mobile lint
```

Create `apps/mobile/.env` from `.env.example`. The only variable that
matters day-to-day is `EXPO_PUBLIC_VOYAGENT_API_URL`. The default
fallback in `lib/sdk.ts` / `lib/auth.tsx` is `http://localhost:8000`,
which a phone on a different network can't reach.

- Local FastAPI on your laptop (phone on same Wi-Fi): set it to
  `http://<your-laptop-lan-ip>:8000`.
- Live demo environment: set it to `https://voyagent.globusdemos.com`.

Launch the Expo dev server:

```bash
pnpm --filter @voyagent/mobile start
# then:
#   - scan the QR with Expo Go (iOS) or the Expo Go app (Android), OR
#   - press `i` to open the iOS simulator (requires Xcode on macOS), OR
#   - press `a` to open an Android emulator (requires Android Studio).
```

Demo account for the live API:

- email: `demo@voyagent.globusdemos.com`
- password: `DemoPassword123!`

What works end-to-end against the live demo API today:

- Sign-up / sign-in via `/api/auth/*` (cookie-free, stored in SecureStore).
- Session hydration on app launch with pre-emptive JWT refresh.
- Chat tab (`@voyagent/chat`'s RN build, streaming via the SDK).
- Sign-out clears the token store.

What is still stubbed:

- Reports tab (`app/index.tsx`) — placeholder copy.
- Desktop pair tab (`app/desktop-pair.tsx`) — QR scanner not wired.

### Known limitations / gotchas

- `expo-secure-store` only works on a real device or simulator — **not**
  in `expo start --web`. The Expo web bundle will throw on auth
  hydration; don't use the web target for smoke-testing mobile auth.
- Icon / splash PNGs are not committed (see Assets below). Expo falls
  back to placeholders during `expo start`, which is fine for dev; a
  real `eas build` needs actual assets.
- iOS production builds will need `ios.bundleIdentifier` to match an
  Apple Developer Team & signing profile in `eas.json` — not yet
  configured here.
- No `eas.json` is committed; `eas build` is out of scope for the
  current skeleton.

## Tabs

Three tabs ship today, all intentionally thin:

- **Reports** (`app/index.tsx`) — a placeholder. v1 will pull receivables,
  payables, and itinerary summaries from the Voyagent API.
- **Chat** (`app/chat.tsx`) — renders `@voyagent/chat`'s React Native
  build. Metro's platform-extension resolution picks `ChatWindow.native.tsx`
  via the `react-native` conditional export in the package's `exports`
  map; DOM/Tailwind never load on the device.
- **Pair** (`app/desktop-pair.tsx`) — a placeholder. Eventually scans a
  QR code from the desktop shell to establish a remote-control channel.

## Desktop pairing

The mobile app's core value proposition is relaying desktop sessions.
The flow will be:

1. The desktop shell shows a short-lived QR code.
2. The phone scans it; the Voyagent backend establishes a relay channel.
3. Approvals, streaming tokens, and status changes sync down to the
   phone; responses flow back up.

This isn't implemented yet; the Pair tab is a visual placeholder.

## Assets

`app.json` references `./assets/icon.png`, `./assets/splash.png`, and
`./assets/adaptive-icon.png`. These PNGs are **not** committed — generate
them when you stand the app up for a real build:

```bash
pnpm --filter @voyagent/mobile exec expo install expo-asset
# then drop icon.png (1024x1024) and splash.png into apps/mobile/assets/
```

Expo will fall back to its own placeholder art if the files are missing
during `expo start`, which is fine for skeleton iteration.

## Environment

`EXPO_PUBLIC_VOYAGENT_API_URL`, `EXPO_PUBLIC_VOYAGENT_TENANT_ID`, and
`EXPO_PUBLIC_VOYAGENT_ACTOR_ID` are read by `lib/sdk.ts`. See
`.env.example`.

## Auth

Cookie-free: mobile can't share HttpOnly cookies with the web app, so
`lib/auth.tsx` persists the access token, refresh token, and cached user
in `expo-secure-store` (iOS Keychain / Android Keystore) and talks to
`/api/auth/sign-up`, `/api/auth/sign-in`, `/api/auth/me`,
`/api/auth/refresh`, and `/api/auth/sign-out` directly. The SDK pulls a
fresh access token via `VoyagentAuth.getAccessToken()` on every request,
which decodes the JWT `exp` and refreshes pre-emptively when within 30s.

## Known limitations

- No real pairing — QR scanner stubbed.
- Reports tab is a placeholder.
- Icon / splash PNGs not generated.
- Not validated on a real device yet (no `eas build` run).

## Scripts

- `pnpm --filter @voyagent/mobile start` — Expo dev server
- `pnpm --filter @voyagent/mobile android` — open Android emulator
- `pnpm --filter @voyagent/mobile ios` — open iOS simulator
- `pnpm --filter @voyagent/mobile lint` — `tsc --noEmit`
- `pnpm --filter @voyagent/mobile clean` — wipe `.expo/` and `dist/`
