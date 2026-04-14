"""Voyagent API entry point.

Minimal skeleton — wires FastAPI with a health check and a single canonical-schema
probe endpoint so the workspace import path (`schemas.canonical`) is exercised
from day one.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from schemas.canonical import Money

app = FastAPI(
    title="Voyagent API",
    version="0.0.0",
    description="Agentic travel OS — public HTTP + SSE API.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/schemas/money")
def money_schema() -> dict[str, Any]:
    """Return the JSON Schema for the canonical Money type.

    Used as a smoke test that the Pydantic -> OpenAPI -> TS contract pipeline
    can see the canonical models.
    """
    return Money.model_json_schema()


def cli() -> None:
    """Console-script entry point: run uvicorn on :8000 with reload."""
    import uvicorn

    uvicorn.run(
        "voyagent_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    cli()
