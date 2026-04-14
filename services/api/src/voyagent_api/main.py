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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas.canonical import Money

from voyagent_api import chat

logger = logging.getLogger(__name__)

_DEFAULT_CORS_ORIGINS = "http://localhost:3000"


def _db_url() -> str | None:
    return os.environ.get("VOYAGENT_DB_URL") or None


def _redis_url() -> str | None:
    return os.environ.get("VOYAGENT_REDIS_URL") or None


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

    # Persistence status: helpful on first boot to confirm env wiring. We
    # only log presence — actual connectivity is probed by /health/db and
    # /health/redis so startup is not blocked on infra races.
    if _db_url():
        logger.info("persistence: VOYAGENT_DB_URL configured — Postgres path active")
    else:
        logger.info(
            "persistence: VOYAGENT_DB_URL unset — using in-memory session + audit"
        )
    if _redis_url():
        logger.info("persistence: VOYAGENT_REDIS_URL configured — Redis offer cache")
    else:
        logger.info(
            "persistence: VOYAGENT_REDIS_URL unset — using in-memory offer cache"
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, Any]:
    """Probe the database with a ``SELECT 1``.

    Returns 503 when no ``VOYAGENT_DB_URL`` is configured so probes
    against a misconfigured deployment fail loudly.
    """
    url = _db_url()
    if not url:
        raise HTTPException(
            status_code=503, detail="VOYAGENT_DB_URL is not configured."
        )
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"sqlalchemy missing: {exc}")

    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            value = result.scalar_one()
        return {"status": "ok", "select_1": int(value)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("db healthcheck failed")
        raise HTTPException(status_code=503, detail=f"db unreachable: {exc}")
    finally:
        await engine.dispose()


@app.get("/health/redis")
async def health_redis() -> dict[str, Any]:
    """PING the Redis instance used by the offer cache."""
    url = _redis_url()
    if not url:
        raise HTTPException(
            status_code=503, detail="VOYAGENT_REDIS_URL is not configured."
        )
    try:
        import redis.asyncio as redis  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"redis missing: {exc}")

    client = redis.from_url(url, decode_responses=True)
    try:
        pong = await client.ping()
        return {"status": "ok", "ping": bool(pong)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("redis healthcheck failed")
        raise HTTPException(status_code=503, detail=f"redis unreachable: {exc}")
    finally:
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if callable(closer):
            try:
                await closer()
            except Exception:  # noqa: BLE001
                pass


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
