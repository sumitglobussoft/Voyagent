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

## Tabs

Three tabs ship today, all intentionally thin:

- **Reports** (`app/index.tsx`) — a placeholder. v1 will pull receivables,
  payables, and itinerary summaries from the Voyagent API.
- **Chat** (`app/chat.tsx`) — a placeholder. `@voyagent/chat` is
  web-first (Tailwind + DOM primitives) and needs an RN adaptation
  before it renders here. In the meantime the screen points users at
  desktop pairing.
- **Pair** (`app/desktop-pair.tsx`) — a placeholder. Eventually scans a
  QR code from the desktop shell to establish a remote-control channel.

## Why chat is a placeholder

The shared `@voyagent/chat` components currently depend on the DOM and
Tailwind utility classes. Porting them to React Native means swapping
`<div>` for `<View>`, Tailwind for Tamagui tokens (see `docs/STACK.md`),
and replacing the SSE implementation with one that uses RN's fetch +
polyfills. That's a distinct workstream — it's intentionally out of scope
for this skeleton.

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

- No real chat rendering — `@voyagent/chat` needs RN adaptation first.
- No real pairing — QR scanner stubbed.
- Icon / splash PNGs not generated.

## Scripts

- `pnpm --filter @voyagent/mobile start` — Expo dev server
- `pnpm --filter @voyagent/mobile android` — open Android emulator
- `pnpm --filter @voyagent/mobile ios` — open iOS simulator
- `pnpm --filter @voyagent/mobile lint` — `tsc --noEmit`
- `pnpm --filter @voyagent/mobile clean` — wipe `.expo/` and `dist/`
