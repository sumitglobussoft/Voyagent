"""Voyagent API entry point.

Wires FastAPI with:

* ``/health`` — liveness probe.
* ``/schemas/money`` — canonical-schema smoke test.
* ``/chat/*`` — session + SSE streaming surface for the agent runtime.

CORS origins are read from ``VOYAGENT_API_CORS_ORIGINS`` (comma-separated).
Defaults to ``http://localhost:3000`` for the Next.js dev server.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from schemas.canonical import Money

from voyagent_api import chat

logger = logging.getLogger(__name__)

_DEFAULT_CORS_ORIGINS = "http://localhost:3000"


def _parse_cors_origins() -> list[str]:
    raw = os.environ.get("VOYAGENT_API_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Voyagent API",
    version="0.0.0",
    description="Agentic travel OS — public HTTP + SSE API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(chat.router)


@app.on_event("startup")
async def _log_runtime_status() -> None:
    # Dev-friendly signal that the parallel runtime work is wired in.
    if chat.runtime_available():
        logger.info("voyagent_agent_runtime imported successfully")
    else:
        logger.warning(
            "voyagent_agent_runtime NOT available — /chat/* routes will return 503"
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
