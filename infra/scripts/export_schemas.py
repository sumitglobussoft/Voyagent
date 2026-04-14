"""Export Voyagent canonical Pydantic models to a consolidated JSON Schema.

Produces ``packages/core/schemas.json`` — a single JSON Schema document whose
``$defs`` section contains every BaseModel exported from
``schemas.canonical`` plus every enum referenced by those models (Pydantic v2
emits enums into ``$defs`` automatically when the model that uses them is
serialised).

The output is deterministic (sorted keys, LF newlines, trailing newline) so
that the CI "codegen-drift" check can diff-exit-code the generated TS file.

Usage::

    uv run python infra/scripts/export_schemas.py

No arguments. Exits non-zero on any error.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import schemas.canonical as canonical

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "packages" / "core" / "schemas.json"


def _collect_model_classes() -> list[type[BaseModel]]:
    """Return every BaseModel subclass exported from ``schemas.canonical``.

    Enums are skipped at this stage — they come along for free in the nested
    ``$defs`` Pydantic produces when a model referencing them is serialised.
    """
    exported = getattr(canonical, "__all__", None)
    names: list[str]
    if exported is None:
        names = [n for n in dir(canonical) if not n.startswith("_")]
    else:
        names = list(exported)

    models: list[type[BaseModel]] = []
    seen: set[str] = set()
    for name in names:
        obj = getattr(canonical, name, None)
        if obj is None:
            continue
        if not inspect.isclass(obj):
            continue
        if not issubclass(obj, BaseModel):
            continue
        if obj is BaseModel:
            continue
        if name in seen:
            continue
        seen.add(name)
        models.append(obj)
    return models


def _merge_def(
    defs: dict[str, Any],
    name: str,
    schema: dict[str, Any],
) -> None:
    """Merge a single ``$defs`` entry, failing loudly on genuine divergence."""
    existing = defs.get(name)
    if existing is None:
        defs[name] = schema
        return
    if existing == schema:
        return
    raise RuntimeError(
        f"Conflicting JSON Schema definitions for '{name}': "
        f"two non-identical schemas were produced by different models. "
        f"Review canonical models for a naming collision."
    )


def build_consolidated_schema() -> dict[str, Any]:
    models = _collect_model_classes()
    if not models:
        raise RuntimeError("No BaseModel subclasses found under schemas.canonical")

    defs: dict[str, Any] = {}

    for model in models:
        # ref_template ensures nested references land under the unified $defs.
        schema = model.model_json_schema(ref_template="#/$defs/{model}")

        # Pull out the model's own nested $defs (Pydantic puts siblings here)
        # so we can hoist them into the outer $defs.
        nested_defs = schema.pop("$defs", {}) or {}
        # Strip Pydantic's default top-level $schema (if any); we set our own.
        schema.pop("$schema", None)

        # The model's own schema goes in under its class name.
        _merge_def(defs, model.__name__, schema)

        for def_name, def_schema in nested_defs.items():
            # Nested schemas may themselves carry $schema keys; drop them.
            if isinstance(def_schema, dict):
                def_schema = {k: v for k, v in def_schema.items() if k != "$schema"}
            _merge_def(defs, def_name, def_schema)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "VoyagentCanonical",
        "description": "Consolidated JSON Schema for Voyagent canonical domain model.",
        "$defs": defs,
    }


def write_schema(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    # Force LF line endings regardless of host OS so CI diff-check is stable.
    path.write_bytes(text.encode("utf-8"))


def main() -> int:
    try:
        doc = build_consolidated_schema()
        write_schema(doc, OUTPUT_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"export_schemas: {exc}", file=sys.stderr)
        return 1
    rel = OUTPUT_PATH.relative_to(REPO_ROOT)
    print(f"export_schemas: wrote {rel} ({len(doc['$defs'])} definitions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
