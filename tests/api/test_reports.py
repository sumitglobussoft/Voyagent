"""Tests for the read-only /reports/* endpoints.

Mirrors the fixture style used in ``tests/api/test_auth_inhouse.py`` —
fresh in-memory SQLite, real FastAPI ``TestClient``, in-house auth
tokens minted via the sign-up endpoint so the principal dependency
validates end-to-end.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

os.environ.setdefault(
    "VOYAGENT_AUTH_SECRET", "test-secret-for-voyagent-tests-32+bytes!"
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from schemas.storage import Base  # noqa: E402
from schemas.storage.invoice import (  # noqa: E402
    BillRow,
    BillStatusEnum,
    InvoiceRow,
    InvoiceStatusEnum,
)
from schemas.storage.session import (  # noqa: E402
    ActorKindEnum,
    MessageRow,
    SessionRow,
)

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
async def _fresh_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
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


async def _insert_session(tenant_id: str) -> uuid.UUID:
    """Insert a SessionRow for ``tenant_id`` and return its id."""
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = SessionRow(
            tenant_id=uuid.UUID(tenant_id),
            actor_id=None,
            actor_kind=ActorKindEnum.HUMAN,
        )
        s.add(row)
        await s.flush()
        sid = row.id
        # messages — include one structured "flight" block the report
        # scraper should pick up, plus noise.
        s.add(
            MessageRow(
                id=uuid.uuid4(),
                session_id=sid,
                role="assistant",
                sequence=1,
                created_at=datetime.now(timezone.utc),
                content=[
                    {"type": "text", "text": "hello"},
                    {
                        "type": "tool_result",
                        "data": {
                            "kind": "flight",
                            "value": {
                                "pnr": "ABC123",
                                "origin": "DEL",
                                "dest": "DXB",
                                "depart": "2026-05-01T09:00:00Z",
                                "carrier": "EK",
                            },
                        },
                    },
                    {
                        "type": "tool_result",
                        "data": {
                            "kind": "passenger",
                            "value": {
                                "full_name": "Alice Example",
                                "passport_number": "P1234567",
                            },
                        },
                    },
                ],
            )
        )
        await s.commit()
        return sid


# --------------------------------------------------------------------------- #
# Unauthenticated access                                                      #
# --------------------------------------------------------------------------- #


def test_receivables_requires_auth(client: TestClient) -> None:
    r = client.get("/reports/receivables?from=2026-01-01&to=2026-01-31")
    assert r.status_code == 401


def test_payables_requires_auth(client: TestClient) -> None:
    r = client.get("/reports/payables?from=2026-01-01&to=2026-01-31")
    assert r.status_code == 401


def test_itinerary_requires_auth(client: TestClient) -> None:
    r = client.get(f"/reports/itinerary?session_id={uuid.uuid4()}")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Happy-path receivables / payables                                           #
# --------------------------------------------------------------------------- #


def test_receivables_returns_empty_shape(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=2026-01-01&to=2026-01-31",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == signup["user"]["tenant_id"]
    assert body["period"] == {"from": "2026-01-01", "to": "2026-01-31"}
    assert body["total_outstanding"] == {"amount": "0.00", "currency": "INR"}
    buckets = {b["bucket"]: b for b in body["aging_buckets"]}
    assert set(buckets) == {"0-30", "31-60", "61-90", "90+"}
    for b in buckets.values():
        assert b["count"] == 0
        assert b["amount"]["amount"] == "0.00"
    assert body["top_debtors"] == []


def test_payables_returns_empty_shape(client: TestClient) -> None:
    signup = _sign_up(client, email="bob@example.com", agency="Bob Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/payables?from=2026-01-01&to=2026-03-31",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == {"from": "2026-01-01", "to": "2026-03-31"}
    assert len(body["aging_buckets"]) == 4
    assert body["top_creditors"] == []


def test_invalid_date_range_rejects_with_422(client: TestClient) -> None:
    signup = _sign_up(client, email="carol@example.com", agency="Carol Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=2026-05-01&to=2026-04-01",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 422


def test_malformed_date_rejects_with_422(client: TestClient) -> None:
    signup = _sign_up(client, email="dave@example.com", agency="Dave Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/receivables?from=not-a-date&to=2026-04-01",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Receivables / payables — real data                                          #
# --------------------------------------------------------------------------- #


async def _insert_invoice(
    *,
    tenant_id: str,
    number: str,
    party_name: str,
    issue_date: date,
    due_date: date,
    total_amount: Decimal,
    currency: str = "INR",
    amount_paid: Decimal = Decimal("0.00"),
    status: InvoiceStatusEnum = InvoiceStatusEnum.ISSUED,
) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = InvoiceRow(
            tenant_id=uuid.UUID(tenant_id),
            number=number,
            party_name=party_name,
            issue_date=issue_date,
            due_date=due_date,
            total_amount=total_amount,
            currency=currency,
            amount_paid=amount_paid,
            status=status,
        )
        s.add(row)
        await s.commit()
        return row.id


async def _insert_bill(
    *,
    tenant_id: str,
    number: str,
    vendor_reference: str,
    party_name: str,
    issue_date: date,
    due_date: date,
    total_amount: Decimal,
    currency: str = "INR",
    amount_paid: Decimal = Decimal("0.00"),
    status: BillStatusEnum = BillStatusEnum.RECEIVED,
) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = BillRow(
            tenant_id=uuid.UUID(tenant_id),
            number=number,
            vendor_reference=vendor_reference,
            party_name=party_name,
            issue_date=issue_date,
            due_date=due_date,
            total_amount=total_amount,
            currency=currency,
            amount_paid=amount_paid,
            status=status,
        )
        s.add(row)
        await s.commit()
        return row.id


async def test_receivables_real_data_tenant_isolation(
    client: TestClient,
) -> None:
    a = _sign_up(client, email="alice@a.com", agency="Tenant A")
    b = _sign_up(client, email="bob@b.com", agency="Tenant B")

    today = datetime.now(timezone.utc).date()

    # Tenant A: one 15 days past due (0-30 bucket), one 45 days (31-60).
    await _insert_invoice(
        tenant_id=a["user"]["tenant_id"],
        number="A-001",
        party_name="Acme Corp",
        issue_date=today - timedelta(days=20),
        due_date=today - timedelta(days=15),
        total_amount=Decimal("1000.00"),
    )
    await _insert_invoice(
        tenant_id=a["user"]["tenant_id"],
        number="A-002",
        party_name="Beta LLC",
        issue_date=today - timedelta(days=50),
        due_date=today - timedelta(days=45),
        total_amount=Decimal("500.50"),
    )
    # Tenant B owns its own invoice — Tenant A must not see it.
    await _insert_invoice(
        tenant_id=b["user"]["tenant_id"],
        number="B-001",
        party_name="Gamma Inc",
        issue_date=today - timedelta(days=5),
        due_date=today + timedelta(days=10),
        total_amount=Decimal("9999.99"),
    )

    window_from = (today - timedelta(days=90)).isoformat()
    window_to = (today + timedelta(days=1)).isoformat()

    r_a = client.get(
        f"/reports/receivables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    )
    assert r_a.status_code == 200, r_a.text
    body = r_a.json()
    buckets = {b["bucket"]: b for b in body["aging_buckets"]}
    assert buckets["0-30"]["count"] == 1
    assert buckets["0-30"]["amount"]["amount"] == "1000.00"
    assert buckets["0-30"]["amount"]["currency"] == "INR"
    assert buckets["31-60"]["count"] == 1
    assert buckets["31-60"]["amount"]["amount"] == "500.50"
    assert buckets["61-90"]["count"] == 0
    assert buckets["90+"]["count"] == 0
    assert body["total_outstanding"]["amount"] == "1500.50"
    # top_debtors populated, ordered by outstanding desc
    assert body["top_debtors"][0]["name"] == "Acme Corp"
    assert body["top_debtors"][0]["amount"]["amount"] == "1000.00"

    # Tenant B sees only its own invoice — not Tenant A's.
    r_b = client.get(
        f"/reports/receivables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    body_b = r_b.json()
    assert r_b.status_code == 200
    b_buckets = {x["bucket"]: x for x in body_b["aging_buckets"]}
    # Gamma Inc's invoice isn't yet due — goes to 0-30 bucket.
    assert b_buckets["0-30"]["count"] == 1
    assert b_buckets["0-30"]["amount"]["amount"] == "9999.99"
    # No Tenant A leakage:
    assert b_buckets["31-60"]["count"] == 0


async def test_payables_real_data_tenant_isolation(
    client: TestClient,
) -> None:
    a = _sign_up(client, email="alice@a.com", agency="Tenant A")
    b = _sign_up(client, email="bob@b.com", agency="Tenant B")

    today = datetime.now(timezone.utc).date()

    await _insert_bill(
        tenant_id=a["user"]["tenant_id"],
        number="BILL-A-001",
        vendor_reference="BSP-A-001",
        party_name="IATA BSP India",
        issue_date=today - timedelta(days=20),
        due_date=today - timedelta(days=15),
        total_amount=Decimal("2000.00"),
    )
    await _insert_bill(
        tenant_id=a["user"]["tenant_id"],
        number="BILL-A-002",
        vendor_reference="HB-A-002",
        party_name="Hotelbeds",
        issue_date=today - timedelta(days=50),
        due_date=today - timedelta(days=45),
        total_amount=Decimal("750.00"),
        status=BillStatusEnum.SCHEDULED,
    )
    await _insert_bill(
        tenant_id=b["user"]["tenant_id"],
        number="BILL-B-001",
        vendor_reference="BSP-B-001",
        party_name="IATA BSP India",
        issue_date=today - timedelta(days=5),
        due_date=today + timedelta(days=10),
        total_amount=Decimal("1234.56"),
    )

    window_from = (today - timedelta(days=90)).isoformat()
    window_to = (today + timedelta(days=1)).isoformat()

    r_a = client.get(
        f"/reports/payables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    )
    assert r_a.status_code == 200, r_a.text
    body = r_a.json()
    buckets = {b["bucket"]: b for b in body["aging_buckets"]}
    assert buckets["0-30"]["count"] == 1
    assert buckets["0-30"]["amount"]["amount"] == "2000.00"
    assert buckets["31-60"]["count"] == 1
    assert buckets["31-60"]["amount"]["amount"] == "750.00"
    assert body["total_outstanding"]["amount"] == "2750.00"
    assert body["top_creditors"][0]["name"] == "IATA BSP India"
    # Tenant A must not see Tenant B's creditors list.
    assert all(
        c["amount"]["amount"] != "1234.56" for c in body["top_creditors"]
    )

    r_b = client.get(
        f"/reports/payables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    body_b = r_b.json()
    assert r_b.status_code == 200
    b_buckets = {x["bucket"]: x for x in body_b["aging_buckets"]}
    assert b_buckets["0-30"]["count"] == 1
    assert b_buckets["31-60"]["count"] == 0


async def test_receivables_excludes_void_invoices(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    today = datetime.now(timezone.utc).date()

    await _insert_invoice(
        tenant_id=signup["user"]["tenant_id"],
        number="INV-1",
        party_name="Acme",
        issue_date=today - timedelta(days=10),
        due_date=today - timedelta(days=5),
        total_amount=Decimal("100.00"),
        status=InvoiceStatusEnum.VOID,
    )
    await _insert_invoice(
        tenant_id=signup["user"]["tenant_id"],
        number="INV-2",
        party_name="Acme",
        issue_date=today - timedelta(days=10),
        due_date=today - timedelta(days=5),
        total_amount=Decimal("200.00"),
        status=InvoiceStatusEnum.PAID,
    )
    await _insert_invoice(
        tenant_id=signup["user"]["tenant_id"],
        number="INV-3",
        party_name="Acme",
        issue_date=today - timedelta(days=10),
        due_date=today - timedelta(days=5),
        total_amount=Decimal("300.00"),
        status=InvoiceStatusEnum.ISSUED,
    )

    window_from = (today - timedelta(days=30)).isoformat()
    window_to = today.isoformat()
    r = client.get(
        f"/reports/receivables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    # Only the ISSUED invoice (300.00) counts.
    assert body["total_outstanding"]["amount"] == "300.00"
    buckets = {b["bucket"]: b for b in body["aging_buckets"]}
    total_count = sum(b["count"] for b in buckets.values())
    assert total_count == 1


async def test_receivables_respects_date_window(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="Tenant A")
    today = datetime.now(timezone.utc).date()

    # Inside window
    await _insert_invoice(
        tenant_id=signup["user"]["tenant_id"],
        number="IN-WINDOW",
        party_name="Acme",
        issue_date=today - timedelta(days=10),
        due_date=today - timedelta(days=5),
        total_amount=Decimal("100.00"),
    )
    # Outside window — issued too long ago
    await _insert_invoice(
        tenant_id=signup["user"]["tenant_id"],
        number="OUT-OF-WINDOW",
        party_name="Acme",
        issue_date=today - timedelta(days=200),
        due_date=today - timedelta(days=195),
        total_amount=Decimal("999.99"),
    )

    window_from = (today - timedelta(days=30)).isoformat()
    window_to = today.isoformat()
    r = client.get(
        f"/reports/receivables?from={window_from}&to={window_to}",
        headers={"Authorization": f"Bearer {signup['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_outstanding"]["amount"] == "100.00"


# --------------------------------------------------------------------------- #
# Itinerary — happy path + tenant isolation                                   #
# --------------------------------------------------------------------------- #


async def test_itinerary_happy_path(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    tenant_id = signup["user"]["tenant_id"]

    sid = await _insert_session(tenant_id)

    r = client.get(
        f"/reports/itinerary?session_id={sid}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == tenant_id
    assert body["session_id"] == str(sid)
    assert body["total_cost"] == {"amount": "0.00", "currency": "INR"}
    assert body["hotels"] == []
    assert body["visas"] == []
    assert len(body["flights"]) == 1
    assert body["flights"][0]["pnr"] == "ABC123"
    assert body["flights"][0]["origin"] == "DEL"
    assert len(body["passengers"]) == 1
    assert body["passengers"][0]["full_name"] == "Alice Example"


async def test_itinerary_tenant_isolation(client: TestClient) -> None:
    # Tenant A owns a session.
    a = _sign_up(client, email="alice@a.com", agency="Tenant A")
    a_tenant_id = a["user"]["tenant_id"]
    a_sid = await _insert_session(a_tenant_id)

    # Tenant B has a different token.
    b = _sign_up(client, email="bob@b.com", agency="Tenant B")
    b_access = b["access_token"]

    # Tenant B asks for Tenant A's session -> 404, not 403.
    r = client.get(
        f"/reports/itinerary?session_id={a_sid}",
        headers={"Authorization": f"Bearer {b_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "session_not_found"


def test_itinerary_missing_session_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        f"/reports/itinerary?session_id={uuid.uuid4()}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404


def test_itinerary_invalid_session_id_returns_404(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@example.com", agency="Example Travel")
    access = signup["access_token"]
    r = client.get(
        "/reports/itinerary?session_id=not-a-uuid",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404
