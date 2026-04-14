# Voyagent Alembic migrations

Schema authoring lives in `schemas/storage/`. This directory only holds
Alembic's version files and config; every DDL change should start as a
SQLAlchemy model update and end as a reviewed migration here.

## Applying migrations

```bash
export VOYAGENT_DB_URL="postgresql+asyncpg://voyagent:voyagent@localhost:5432/voyagent"
uv run alembic -c infra/alembic/alembic.ini upgrade head
```

`VOYAGENT_DB_URL` must use the `postgresql+asyncpg://` scheme because
`env.py` runs migrations through an async engine. For the dev stack in
`infra/docker/dev.yml`, the local URL is:

```
postgresql+asyncpg://voyagent:voyagent@localhost:5432/voyagent
```

## Autogenerating a new revision

After editing a model in `schemas/storage/`:

```bash
uv run alembic -c infra/alembic/alembic.ini revision \
    --autogenerate -m "add foo column to bar"
```

**Review the generated file before committing.** Alembic autogenerate
does not faithfully capture:

- `server_default` values (`now()`, `'{}'::jsonb`, enum defaults);
- CHECK constraints;
- Custom types like our portable `UUIDType`;
- ENUM type lifecycle on Postgres — new enum values and ENUM DROPs must
  be hand-written.

Treat autogenerate as a starting point, not the final answer.

## Offline / dry-run

```bash
uv run alembic -c infra/alembic/alembic.ini upgrade head --sql > upgrade.sql
```

Useful for PR review or handing DDL to a DBA.

## Rolling back

```bash
uv run alembic -c infra/alembic/alembic.ini downgrade -1
```

`0001_initial.py` knows how to drop every table + ENUM it created, but
rolling back past `0001` on a populated database will lose data — do it
only in disposable dev environments.
