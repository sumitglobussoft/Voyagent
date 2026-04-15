# Voyagent real-Postgres integration tests

These tests exercise the Voyagent API against a **real Postgres** instance
rather than the `sqlite+aiosqlite` in-memory DB used by the default unit
suite. They exist to catch Postgres-specific behavior — JSONB typing,
server-side enum constraints, `ON CONFLICT` semantics, FK cascade ordering
— that SQLite cannot reproduce.

## Opt-in by design

The whole module is **skipped at pytest collection time** unless
`VOYAGENT_TEST_DB_URL` is set. A default `uv run pytest` will never try
to touch Postgres, so CI doesn't need a test DB unless you explicitly
schedule this suite.

## Start a local test Postgres

Cheapest way — Docker:

```bash
docker run --rm -d \
  --name voyagent-test-pg \
  -e POSTGRES_USER=voyagent_test \
  -e POSTGRES_PASSWORD=voyagent_test \
  -e POSTGRES_DB=voyagent_test \
  -p 5433:5432 \
  postgres:16-alpine
```

Or use any existing Postgres instance — the suite only needs a fresh,
empty database it can create tables in and then truncate at the end.

## Run

```bash
export VOYAGENT_TEST_DB_URL="postgresql+asyncpg://voyagent_test:voyagent_test@127.0.0.1:5433/voyagent_test"
uv run pytest tests/integration -v
```

## What happens

On fixture setup:
1. Connects to `VOYAGENT_TEST_DB_URL`.
2. Tries `alembic upgrade head` if `alembic.ini` is available; otherwise
   falls back to `Base.metadata.create_all` (same as the unit suite).
3. Installs the engine into `voyagent_api.db` for the duration of each
   test.

On teardown:
1. `TRUNCATE TABLE ... RESTART IDENTITY CASCADE` on every table in the
   public schema.
2. `engine.dispose()`.

## What the single round-trip test covers

`test_api_roundtrip.py::test_full_api_roundtrip` runs one long sequential
flow:

1. Sign-up + `/auth/me`
2. Create a chat session
3. Send a chat message (agent runtime mocked if possible)
4. Create an enquiry
5. Promote enquiry to a chat session
6. Query the audit log
7. Query `/reports/receivables`
8. Invite a teammate, accept the invite
9. Fetch tenant settings
10. Sign out

One test, sequential, touches every table and every JSONB write path.

## CI

These tests should run on a **schedule** (nightly or weekly), not on
every PR. The default PR pipeline continues to use the SQLite unit
suite, which is fast enough to run on every commit.
