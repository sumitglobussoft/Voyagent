"""Tests for chat session DELETE + PATCH (rename).

These routes talk directly to the ``sessions`` / ``messages`` /
``pending_approvals`` tables so we do not need the agent runtime
stub — fixture style mirrors ``tests/api/test_approvals.py`` (file
SQLite + sign-up for token minting).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)
os.environ.setdefault("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base  # noqa: E402
from schemas.storage.session import (  # noqa: E402
    ActorKindEnum,
    ApprovalStatusEnum,
    MessageRow,
    PendingApprovalRow,
    SessionRow,
)

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    db_path = tmp_path / "voyagent-chat-crud-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False)
    db_module.set_engine_for_test(engine, sm)

    get_auth_settings.cache_clear()
    revocation.set_revocation_list_for_test(revocation.NullRevocationList())

    yield

    db_module.set_engine_for_test(None)
    revocation.set_revocation_list_for_test(None)
    await engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_PASSWORD = "Sup3rSecretValue!"


def _sign_up(client: TestClient, *, email: str, agency: str) -> dict:
    body = {
        "email": email,
        "password": _PASSWORD,
        "full_name": f"User {email}",
        "agency_name": agency,
    }
    r = client.post("/auth/sign-up", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _insert_session(tenant_id: str, *, title: str | None = None) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = SessionRow(
            tenant_id=uuid.UUID(tenant_id),
            actor_id=None,
            actor_kind=ActorKindEnum.HUMAN,
            title=title,
        )
        s.add(row)
        await s.commit()
        return row.id


async def _insert_message(session_id: uuid.UUID, *, sequence: int = 0) -> None:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        s.add(
            MessageRow(
                session_id=session_id,
                role="user",
                content=[{"type": "text", "text": "hello"}],
                sequence=sequence,
                created_at=datetime.now(timezone.utc),
            )
        )
        await s.commit()


async def _insert_approval(session_id: uuid.UUID, *, approval_id: str) -> None:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        now = datetime.now(timezone.utc)
        s.add(
            PendingApprovalRow(
                id=approval_id,
                session_id=session_id,
                tool_name="issue_ticket",
                summary="Issue ticket",
                turn_id="t1",
                requested_at=now,
                expires_at=now + timedelta(minutes=15),
                status=ApprovalStatusEnum.PENDING,
            )
        )
        await s.commit()


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #


def test_delete_requires_auth(client: TestClient) -> None:
    r = client.delete(f"/chat/sessions/{uuid.uuid4()}")
    assert r.status_code == 401


def test_patch_requires_auth(client: TestClient) -> None:
    r = client.patch(
        f"/chat/sessions/{uuid.uuid4()}", json={"title": "Renamed"}
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# DELETE                                                                      #
# --------------------------------------------------------------------------- #


async def test_delete_session_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    sid = await _insert_session(signup["user"]["tenant_id"], title="Old")
    token = signup["access_token"]

    r = client.delete(
        f"/chat/sessions/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, r.text

    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(
                select(SessionRow).where(SessionRow.id == sid)
            )
        ).scalar_one_or_none()
        assert row is None


async def test_delete_cascades_messages_and_approvals(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    sid = await _insert_session(signup["user"]["tenant_id"])
    await _insert_message(sid, sequence=0)
    await _insert_message(sid, sequence=1)
    await _insert_approval(sid, approval_id="ap-cascade")

    r = client.delete(
        f"/chat/sessions/{sid}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 204

    sm = db_module.get_sessionmaker()
    async with sm() as s:
        msgs = int(
            (
                await s.execute(
                    select(func.count()).select_from(MessageRow).where(
                        MessageRow.session_id == sid
                    )
                )
            ).scalar_one()
            or 0
        )
        aps = int(
            (
                await s.execute(
                    select(func.count()).select_from(PendingApprovalRow).where(
                        PendingApprovalRow.session_id == sid
                    )
                )
            ).scalar_one()
            or 0
        )
        assert msgs == 0
        assert aps == 0


async def test_delete_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid = await _insert_session(a["user"]["tenant_id"])

    r = client.delete(
        f"/chat/sessions/{sid}",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404

    # The row is untouched.
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(
                select(SessionRow).where(SessionRow.id == sid)
            )
        ).scalar_one_or_none()
        assert row is not None


def test_delete_unknown_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.delete(
        f"/chat/sessions/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# PATCH (rename)                                                              #
# --------------------------------------------------------------------------- #


async def test_patch_title_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    sid = await _insert_session(signup["user"]["tenant_id"], title="Old")

    r = client.patch(
        f"/chat/sessions/{sid}",
        json={"title": "Brand new title"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Brand new title"
    assert body["session_id"] == str(sid)

    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalar_one()
        assert row.title == "Brand new title"


def test_patch_empty_title_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        f"/chat/sessions/{uuid.uuid4()}",
        json={"title": ""},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


async def test_patch_whitespace_only_title_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    sid = await _insert_session(signup["user"]["tenant_id"])
    r = client.patch(
        f"/chat/sessions/{sid}",
        json={"title": "     "},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


def test_patch_title_too_long_422(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        f"/chat/sessions/{uuid.uuid4()}",
        json={"title": "x" * 201},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 422


async def test_patch_cross_tenant_returns_404(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    sid = await _insert_session(a["user"]["tenant_id"], title="A-owned")

    r = client.patch(
        f"/chat/sessions/{sid}",
        json={"title": "Hijack"},
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r.status_code == 404

    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalar_one()
        assert row.title == "A-owned"


def test_patch_unknown_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    r = client.patch(
        f"/chat/sessions/{uuid.uuid4()}",
        json={"title": "Does not exist"},
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 404
