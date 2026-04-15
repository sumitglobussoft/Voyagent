"""Tests for GET /audit/export.csv."""

from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)
os.environ.setdefault("VOYAGENT_AUTH_SKIP_EMAIL_VERIFICATION", "true")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from schemas.storage import Base  # noqa: E402
from schemas.storage.audit import AuditEventRow, AuditStatusEnum  # noqa: E402
from schemas.storage.session import ActorKindEnum  # noqa: E402

from voyagent_api import audit as audit_module  # noqa: E402
from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _insert_audit(
    *,
    tenant_id: uuid.UUID,
    tool: str = "issue_ticket",
    actor_id: uuid.UUID | None = None,
    actor_kind: ActorKindEnum = ActorKindEnum.HUMAN,
    status: AuditStatusEnum = AuditStatusEnum.SUCCEEDED,
    started_at: datetime | None = None,
    inputs: dict | None = None,
) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as db:
        row = AuditEventRow(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_kind=actor_kind,
            tool=tool,
            inputs=inputs or {},
            outputs={},
            entity_refs={},
            started_at=started_at or datetime.now(timezone.utc),
            status=status,
        )
        db.add(row)
        await db.commit()
        return row.id


def _parse_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _mint_non_admin_token(
    *, user_id: str, tenant_id: str, email: str, role: str = "agent"
) -> str:
    from voyagent_api.auth_inhouse.tokens import issue_access_token

    token, _exp, _jti = issue_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        email=email,
        role=role,
    )
    return token


# --------------------------------------------------------------------------- #
# Auth / RBAC                                                                 #
# --------------------------------------------------------------------------- #


def test_export_requires_auth(client: TestClient) -> None:
    r = client.get("/audit/export.csv")
    assert r.status_code == 401


def test_export_non_admin_forbidden(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    token = _mint_non_admin_token(
        user_id=signup["user"]["id"],
        tenant_id=signup["user"]["tenant_id"],
        email="alice@a.com",
        role="agent",
    )
    r = client.get("/audit/export.csv", headers=_auth(token))
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden_role"


# --------------------------------------------------------------------------- #
# Happy path + headers                                                        #
# --------------------------------------------------------------------------- #


async def test_export_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(signup["user"]["tenant_id"])

    await _insert_audit(
        tenant_id=tenant_a, tool="issue_ticket", inputs={"pnr": "ABC"}
    )
    await _insert_audit(
        tenant_id=tenant_a, tool="auth.verify", inputs={"method": "GET"}
    )
    await _insert_audit(tenant_id=tenant_a, tool="hold_fare")

    r = client.get(
        "/audit/export.csv",
        headers=_auth(signup["access_token"]),
    )
    assert r.status_code == 200, r.text
    ctype = r.headers["content-type"]
    assert "text/csv" in ctype
    cd = r.headers["content-disposition"]
    assert "attachment" in cd
    assert "voyagent-audit-" in cd
    assert ".csv" in cd

    rows = _parse_csv(r.text)
    assert len(rows) == 3
    # Columns present and correct.
    assert set(rows[0].keys()) == {
        "created_at",
        "kind",
        "actor_kind",
        "actor_id",
        "actor_email",
        "status",
        "summary",
        "payload_json",
    }
    kinds = {r["kind"] for r in rows}
    assert kinds == {"issue_ticket", "auth.verify", "hold_fare"}


async def test_export_payload_json_round_trip(client: TestClient) -> None:
    import json

    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(signup["user"]["tenant_id"])
    await _insert_audit(
        tenant_id=tenant_a,
        tool="issue_ticket",
        inputs={"pnr": "XYZ", "amount": "1234.50"},
    )

    r = client.get(
        "/audit/export.csv",
        headers=_auth(signup["access_token"]),
    )
    assert r.status_code == 200
    rows = _parse_csv(r.text)
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"])
    assert payload["inputs"] == {"pnr": "XYZ", "amount": "1234.50"}


# --------------------------------------------------------------------------- #
# Tenant isolation                                                            #
# --------------------------------------------------------------------------- #


async def test_export_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])
    tenant_b = uuid.UUID(b["user"]["tenant_id"])

    await _insert_audit(tenant_id=tenant_a, tool="a_thing")
    await _insert_audit(tenant_id=tenant_a, tool="a_thing_2")
    await _insert_audit(tenant_id=tenant_b, tool="b_thing")

    r_a = client.get(
        "/audit/export.csv",
        headers=_auth(a["access_token"]),
    )
    rows_a = _parse_csv(r_a.text)
    kinds_a = {r["kind"] for r in rows_a}
    assert kinds_a == {"a_thing", "a_thing_2"}
    assert "b_thing" not in kinds_a


# --------------------------------------------------------------------------- #
# Kind filter                                                                 #
# --------------------------------------------------------------------------- #


async def test_export_kind_filter(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])
    await _insert_audit(tenant_id=tenant_a, tool="approval.granted")
    await _insert_audit(tenant_id=tenant_a, tool="approval.granted")
    await _insert_audit(tenant_id=tenant_a, tool="approval.rejected")
    await _insert_audit(tenant_id=tenant_a, tool="issue_ticket")

    r = client.get(
        "/audit/export.csv?kind=approval.granted",
        headers=_auth(a["access_token"]),
    )
    assert r.status_code == 200
    rows = _parse_csv(r.text)
    assert len(rows) == 2
    assert all(r["kind"] == "approval.granted" for r in rows)


# --------------------------------------------------------------------------- #
# Date filter                                                                 #
# --------------------------------------------------------------------------- #


async def test_export_date_filter(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(a["user"]["tenant_id"])

    base = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    await _insert_audit(
        tenant_id=tenant_a, tool="early", started_at=base - timedelta(days=5)
    )
    await _insert_audit(
        tenant_id=tenant_a, tool="inside", started_at=base
    )
    await _insert_audit(
        tenant_id=tenant_a, tool="late", started_at=base + timedelta(days=5)
    )

    r = client.get(
        "/audit/export.csv?from=2026-04-08&to=2026-04-12",
        headers=_auth(a["access_token"]),
    )
    rows = _parse_csv(r.text)
    assert len(rows) == 1
    assert rows[0]["kind"] == "inside"


# --------------------------------------------------------------------------- #
# Row cap                                                                     #
# --------------------------------------------------------------------------- #


def test_export_row_limit_constant_exists() -> None:
    # The limit exists as a module constant so ops can bump it without
    # code changes scattered everywhere.
    assert isinstance(audit_module.AUDIT_CSV_EXPORT_MAX_ROWS, int)
    assert audit_module.AUDIT_CSV_EXPORT_MAX_ROWS >= 1


async def test_export_too_large_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tenant_a = uuid.UUID(signup["user"]["tenant_id"])

    # Lower the cap so we can trigger the guard with just a handful of
    # rows. The cap is referenced by the route via the module attr,
    # so monkeypatching it is enough.
    monkeypatch.setattr(audit_module, "AUDIT_CSV_EXPORT_MAX_ROWS", 2)

    for i in range(3):
        await _insert_audit(tenant_id=tenant_a, tool=f"t{i}")

    r = client.get(
        "/audit/export.csv",
        headers=_auth(signup["access_token"]),
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "export_too_large"
