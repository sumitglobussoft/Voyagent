# @voyagent/core

Canonical Voyagent domain types for TypeScript. This package is the
TypeScript-side counterpart to `schemas/canonical/` (Pydantic v2) and
exists so that every TS client — web, desktop, mobile, the SDK, and the
chat UI — consumes the exact same shapes the Python runtime produces.

## Codegen pipeline

See `docs/STACK.md` → "The Pydantic → TS contract flow" for the authoritative
description. In short:

```
schemas/canonical/*.py          (Pydantic v2 — source of truth)
      │
      │  infra/scripts/export_schemas.py
      ▼
packages/core/schemas.json      (consolidated JSON Schema, not committed)
      │
      │  json-schema-to-typescript
      ▼
packages/core/src/generated.ts  (committed, CI-verified fresh)
      │
      ▼
packages/core/src/index.ts      (re-exports everything)
```

`schemas.json` is an intermediate artefact and is `.gitignore`d.
`generated.ts` is committed so diffs are reviewable and downstream packages
do not need the Python toolchain to build.

## Regenerate locally

```bash
# From the repo root (runs turbo → this package's codegen script)
pnpm codegen

# Or directly, if you want just this package
pnpm -C packages/core codegen
```

You need both `uv` (for the Python exporter) and `pnpm` (for the TS
compiler) on your PATH.

## CI drift check

The `codegen-drift` job in `.github/workflows/ci.yml` re-runs the pipeline
on every push and fails if `packages/core/src/generated.ts` changes. If you
see it fail, run `pnpm codegen` locally and commit the result.

## Consuming types

```ts
import type { Money, Passenger, Itinerary } from "@voyagent/core";
```

Everything re-exported from `generated.ts` is available from the package
root. No runtime code is shipped from this package today; it is pure types.
