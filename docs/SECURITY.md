# Security

Security posture for the Voyagent in-house auth subsystem. This document
covers the three pillars added by the "auth hardening pack":

1. Password strength enforcement
2. TOTP two-factor authentication
3. API keys for headless access

## Password strength

Passwords are validated by `auth_inhouse.passwords.validate_password_strength`
before the hasher ever sees them. The rules are deterministic and
hand-rolled — no zxcvbn, no external wordlists.

| Rule | Error code |
| --- | --- |
| Blank / whitespace-only | `password_blank` |
| Shorter than 10 characters | `password_too_short` |
| Longer than 128 characters | `password_too_long` |
| No letter | `password_no_letter` |
| No digit | `password_no_digit` |
| In the hard-coded common-password blocklist | `password_common` |

`sign_up` calls this validator and surfaces the failure as
`400 password_too_weak` with the specific code in the response body.
The validator is also wired into `reset_password` (follow-up — the
parallel team-onboarding agent owns that function, so the wire-up
lands in merge review).

Hashing stays on argon2id via `argon2-cffi` with cost parameters from
`AuthSettings`. `needs_rehash` detects hashes minted under older cost
params so rotation is a no-op data migration.

## TOTP two-factor authentication

TOTP (RFC 6238, 6-digit codes, 30-second window) is supported as an
optional second factor per user. The flow:

1. `POST /auth/totp/setup` (authenticated) — mints a fresh base32
   secret, stores it on `users.totp_secret`, returns
   `{secret, otpauth_url}`. The `otpauth_url` is formatted as
   `otpauth://totp/Voyagent:<email>?secret=<secret>&issuer=Voyagent`
   so the client can render a QR directly.
2. `POST /auth/totp/verify` — authenticated user submits a 6-digit
   code. Server verifies via `pyotp.TOTP(secret).verify(code,
   valid_window=1)` and flips `users.totp_enabled=True` on success.
   Re-verifying an already-enabled user is an idempotent no-op.
3. `POST /auth/totp/disable` — requires BOTH the user's password AND
   a current TOTP code so a compromised session can't disable 2FA.
   Clears the secret and flips `totp_enabled=False`.

Sign-in with 2FA on:

* `POST /auth/sign-in` behaves unchanged for users without 2FA.
* For users with `totp_enabled=True`, the `/auth/sign-in` step is
  expected (post-merge) to return `401 totp_required` instead of
  issuing tokens. The client then reposts to
  `POST /auth/sign-in-totp` with `{email, password, totp_code}` to
  receive the normal `AuthResponse`.

### TOTP secret storage — current v0 limitation

The `users.totp_secret` column holds the base32-encoded plaintext.
**This is a v0 trade-off.** The follow-up plan is to wrap the secret
with `schemas.storage.crypto.FernetEnvKMS` using `VOYAGENT_KMS_KEY`
(envelope encryption on write, decrypt-on-verify). There is a
prominent `TODO(security)` in both `schemas/storage/user.py` and
`auth_inhouse/totp.py` pointing at this ticket.

Operational implications until the follow-up lands:

* A full database dump leaks every TOTP seed. Treat the `users` table
  backups as top-secret.
* The threat model assumes attackers do not have read access to the
  database. Combined with argon2id password hashes, even a read-only
  dump is insufficient to forge a full login without the password.
* Rotation: users can always re-run `POST /auth/totp/setup` to mint
  a fresh secret and re-verify.

## API keys (headless access)

API keys let scripts, CI jobs, and external integrations authenticate
without going through the interactive sign-in flow.

### Key format

```
vy_<prefix>_<body>
```

* `prefix` — 8 urlsafe characters, stored plaintext on the row,
  displayed in the UI, and used as the O(1) index for lookup.
* `body` — 32 urlsafe characters, never stored in any form.
* The full string's SHA-256 hex digest (64 chars) is stored as
  `key_hash` with a unique constraint.

### Storage shape

Table `api_keys` (schema: `schemas/storage/api_key.py`):

| Column | Notes |
| --- | --- |
| `id` | UUIDv7 primary key |
| `tenant_id` | FK into `tenants`, cascaded on delete |
| `created_by_user_id` | FK into `users`, the principal attributed to the key |
| `name` | Human label shown in the UI ("CI deploy key") |
| `prefix` | First 8 chars, O(1) lookup index |
| `key_hash` | SHA-256 hex of the full plaintext, unique |
| `scopes` | v0 supports only `"full"` |
| `expires_at` | Optional, nullable |
| `revoked_at` | Soft-revoke timestamp |
| `last_used_at` | Updated on every successful verification |

Combined index `ix_api_keys_tenant_revoked` on `(tenant_id,
revoked_at)` keeps listing of active keys fast.

### Routes

* `POST /auth/api-keys` — body `{name, expires_in_days?}`. Mints a new
  key and returns the full plaintext **exactly once** alongside a
  warning string. After this response the plaintext is unrecoverable.
* `GET /auth/api-keys` — lists every key for the caller's tenant.
  Returns metadata only; plaintext is never surfaced.
* `POST /auth/api-keys/{id}/revoke` — soft-revokes (sets
  `revoked_at = now()`). Subsequent requests with the key are
  rejected as `401`.

### Verification path

`auth_inhouse/api_keys.get_principal_from_api_key_or_jwt` is a
fallback-chained FastAPI dependency:

1. If the `Authorization: Bearer` token starts with `vy_`, route
   through `resolve_api_key`: parse, look up by prefix,
   constant-time compare the SHA-256 hash, check `revoked_at IS NULL`
   and `expires_at IS NULL OR expires_at > now()`, update
   `last_used_at`, synthesise an `AuthenticatedPrincipal` whose
   `jti` is `apikey:<uuid>` so logs attribute actions back to a key.
2. Otherwise fall through to the existing JWT verification in
   `auth_inhouse/deps.py`.

The existing `get_current_principal` dependency is **unchanged** —
the new combined dependency is opt-in per route to avoid racing the
team-onboarding work.

### Tenant isolation

`list_api_keys_for_tenant` and `revoke_api_key` both scope by
`tenant_id`, so tenant A cannot see or revoke tenant B's keys. The
test suite pins this invariant.
