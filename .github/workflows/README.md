# CI / Release Workflows

This directory holds the GitHub Actions workflows for Voyagent. Each
workflow is documented below — what it does, what triggers it, and
what secrets or prerequisites it needs.

## `ci.yml` — Continuous Integration

Runs on every push to `main` and on every pull request. Python tests
(pytest) and lint (ruff). See `docs/CI.md` for the deselected test
notes.

## `desktop-release.yml` — Desktop (Tauri) release

Builds the Tauri shell for macOS (arm64 + x64 universal), Linux
(ubuntu-22.04), and Windows (windows-2022).

### Triggers

| Trigger | Behavior |
|---|---|
| `release: types: [published]` | Full matrix build, artifacts uploaded to the GitHub Release via `softprops/action-gh-release`. |
| `workflow_dispatch` | Full matrix build, artifacts uploaded as workflow artifacts only. Useful for smoke-testing a tag candidate without cutting a release. |
| `pull_request` (paths: `apps/desktop/**` or the workflow file itself) | **Dry-run job only.** Runs `tauri build` on all three OSes but does not upload or publish anything. This is the "test" for the workflow itself. |

### Matrix

- `macos-14` — universal binary via `--target universal-apple-darwin`; emits `.app.tar.gz` and `.dmg`
- `ubuntu-22.04` — installs `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`; emits `.AppImage` and `.deb`
- `windows-2022` — emits `.msi` (WiX) and `.exe` (NSIS)

### Signing

**Binaries are unsigned in v0.** Users will see:

- macOS: "app is from an unidentified developer" Gatekeeper warning. Right-click > Open to bypass once.
- Windows: SmartScreen "unknown publisher" warning. The `.msi`/`.exe` still install.
- Linux: no warnings — AppImage and `.deb` do not require signing for local install. Apt repos need GPG, which is out of scope here.

To enable production signing, add these repo secrets and uncomment the
`env:` block at the top of the `desktop-release` job:

| Secret | Purpose |
|---|---|
| `APPLE_CERTIFICATE` | Base64-encoded Developer ID Application `.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the `.p12` |
| `APPLE_ID` | Apple ID email for notarization |
| `APPLE_PASSWORD` | App-specific password for notarization |
| `APPLE_TEAM_ID` | Developer Team ID |
| `WINDOWS_CERTIFICATE` | Base64-encoded Authenticode `.pfx` |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password for the `.pfx` |
| `TAURI_SIGNING_PRIVATE_KEY` | Tauri updater signing private key (from `tauri signer generate`) |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Password for the above |

See `apps/desktop/README.md` for the full signing walkthrough.

## `mobile-release.yml` — Mobile (Expo + EAS) release

Kicks off an EAS build and publishes an OTA update.

### Triggers

| Trigger | Behavior |
|---|---|
| `workflow_dispatch` | Manual — user picks `platform` (ios/android/all), `profile` (development/preview/production), and `channel` (staging/production). |
| `release: types: [published]` | Production build + production OTA update. |

Why manual-first: EAS builds take 10–40 minutes and consume Expo credit.
OTA updates are cheaper but still gated so we don't ship half-tested JS
bundles to real users.

### Secrets

| Secret | Purpose |
|---|---|
| `EXPO_TOKEN` | Personal access token from https://expo.dev/accounts/&lt;you&gt;/settings/access-tokens — required by both jobs |

### PREREQUISITE — one-time human setup

**Before the first run**, a human must initialize the Expo project and
wire the project id into `apps/mobile/app.json`. From `apps/mobile/`:

```bash
pnpm dlx eas-cli@latest login
pnpm dlx eas-cli@latest init
```

`eas init` writes `expo.extra.eas.projectId` into `app.json`. The
current committed value is the placeholder `TODO-run-eas-init-in-apps-mobile`
— replace it and commit the result. Do the same for the `updates.url`
field, which becomes `https://u.expo.dev/<projectId>`.

### Dry-run / testing

The mobile workflow has no dry-run equivalent because an "EAS build
that doesn't publish" is still an EAS build and still consumes credit.
The closest equivalent is running `eas build --local` from a laptop,
which does not route through GitHub Actions at all. Local lint + the
vitest OCR suite run in the standard CI workflow.

## How dry-runs act as "tests" for workflows

Workflows cannot be unit-tested directly — they only run inside GitHub
Actions. The nearest equivalent is a job that exercises the same steps
on a safe trigger:

- **Desktop**: the `desktop-release-dry-run` job runs on every PR that
  touches `apps/desktop/**`. Success means the matrix is green and a
  future merge-to-main release tag won't fail in an unexpected way.
- **Mobile**: no dry-run (see above). The TS side is covered by
  `vitest` and the Python side by `pytest` in `ci.yml`; the workflow
  itself is validated by running it once end-to-end after `eas init`.

## Quick reference

```bash
# Manually kick a desktop release build (uses current HEAD):
gh workflow run desktop-release.yml

# Manually kick a mobile preview build for iOS only:
gh workflow run mobile-release.yml \
  -f platform=ios -f profile=preview -f channel=staging

# Cut a full release (desktop + mobile production):
gh release create v0.1.0 --generate-notes
```
