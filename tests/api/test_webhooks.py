"""Clerk webhook tests.

We rely on the ``svix`` library to sign payloads the same way Clerk
does, then invoke the FastAPI handler through a test client that
points at a temporary SQLite database.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import asyncio as _asyncio_bootstrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from schemas.storage import Base


svix = pytest.importorskip("svix")


WEBHOOK_SECRET = "whsec_" + "a" * 40


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _sign_payload(payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    from svix.webhooks import Webhook

    import datetime as _dt

    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    wh = Webhook(WEBHOOK_SECRET)
    msg_id = f"msg_{uuid.uuid4().hex}"
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    timestamp = str(int(now.timestamp()))
    # ``sign`` accepts either a datetime or float unix-ts depending on
    # the svix Python version; the datetime form is the documented one.
    signature = wh.sign(msg_id, now, body)
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": signature,
        "content-type": "application/json",
    }
    return body, headers


@pytest.fixture
def _sqlite_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Create a file-backed aiosqlite URL and create tables.

    The webhook handler constructs its own engine inside the request
    (via ``create_async_engine``) so the DB must live on-disk — an
    in-memory SQLite would vanish between connections.
    """
    db_path = tmp_path_factory.mktemp("webhook") / "db.sqlite"
    url = f"sqlite+aiosqlite:///{str(db_path).replace(chr(92), '/')}"

    async def _init() -> None:
        engine = create_async_engine(
            url,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    _asyncio_bootstrap.run(_init())
    return url


@pytest.fixture
def client(_sqlite_url: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("VOYAGENT_CLERK_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("VOYAGENT_DB_URL", _sqlite_url)

    # Build an app with just the webhook router attached so we don't
    # depend on the full /chat stack for these tests.
    from voyagent_api import webhooks

    app = FastAPI()
    app.include_router(webhooks.router)
    return TestClient(app)


def _user_payload(event: str, external_id: str, org_id: str) -> dict[str, Any]:
    return {
        "type": event,
        "data": {
            "id": external_id,
            "first_name": "Alice",
            "last_name": "Example",
            "email_addresses": [
                {"email_address": "alice@example.test"}
            ],
            "organization_memberships": [
                {"organization": {"id": org_id}, "role": "org:member"}
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_user_created_upserts_row(client: TestClient, _sqlite_url: str) -> None:
    payload = _user_payload("user.created", "user_123", "org_abc")
    body, headers = _sign_payload(payload)
    response = client.post("/webhooks/clerk", content=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["event"] == "user.created"

    # Verify the row landed.
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _check() -> None:
        from schemas.storage import User

        engine = create_async_engine(_sqlite_url, future=True)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                rows = (
                    await db.execute(select(User).where(User.external_id == "user_123"))
                ).scalars().all()
            assert len(rows) == 1
            assert rows[0].display_name == "Alice Example"
            assert rows[0].email == "alice@example.test"
        finally:
            await engine.dispose()

    asyncio.run(_check())


def test_bad_signature_returns_400(client: TestClient) -> None:
    payload = _user_payload("user.created", "user_bad", "org_bad")
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "svix-id": "msg_nope",
        "svix-timestamp": "0",
        "svix-signature": "v1,deadbeef",
        "content-type": "application/json",
    }
    response = client.post("/webhooks/clerk", content=body, headers=headers)
    assert response.status_code == 400


def test_replay_is_idempotent(client: TestClient, _sqlite_url: str) -> None:
    payload = _user_payload("user.created", "user_replay", "org_replay")
    body, headers = _sign_payload(payload)

    r1 = client.post("/webhooks/clerk", content=body, headers=headers)
    assert r1.status_code == 200
    r2 = client.post("/webhooks/clerk", content=body, headers=headers)
    assert r2.status_code == 200

    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _check() -> None:
        from schemas.storage import User

        engine = create_async_engine(_sqlite_url, future=True)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                rows = (
                    await db.execute(
                        select(User).where(User.external_id == "user_replay")
                    )
                ).scalars().all()
            assert len(rows) == 1
        finally:
            await engine.dispose()

    asyncio.run(_check())


def test_user_deleted_is_soft_delete(client: TestClient, _sqlite_url: str) -> None:
    created = _user_payload("user.created", "user_del", "org_del")
    body, headers = _sign_payload(created)
    client.post("/webhooks/clerk", content=body, headers=headers)

    deleted = _user_payload("user.deleted", "user_del", "org_del")
    body2, headers2 = _sign_payload(deleted)
    r = client.post("/webhooks/clerk", content=body2, headers=headers2)
    assert r.status_code == 200

    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    async def _check() -> None:
        from schemas.storage import User

        engine = create_async_engine(_sqlite_url, future=True)
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                rows = (
                    await db.execute(
                        select(User).where(User.external_id == "user_del")
                    )
                ).scalars().all()
            # Row still present — soft delete.
            assert len(rows) == 1
        finally:
            await engine.dispose()

    asyncio.run(_check())


# Silence unused imports when svix symbols are not consumed directly.
_ = os
