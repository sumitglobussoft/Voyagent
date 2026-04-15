"""Tests for ``GET /reports/trial-balance``.

Uses the same tmp-file aiosqlite fixture shape as ``test_approvals.py``
to avoid the aiosqlite + StaticPool + TestClient race that bites the
in-memory variant.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
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
from schemas.storage.ledger import (  # noqa: E402
    JournalEntryRow,
    LedgerAccountRow,
    LedgerAccountTypeEnum,
)

from voyagent_api import db as db_module  # noqa: E402
from voyagent_api import revocation  # noqa: E402
from voyagent_api.auth_inhouse.settings import get_auth_settings  # noqa: E402
from voyagent_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_db(tmp_path):
    db_path = tmp_path / "voyagent-trial-balance-test.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        future=True,
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


async def _insert_account(
    *,
    tenant_id: str,
    code: str,
    name: str,
    type_: LedgerAccountTypeEnum = LedgerAccountTypeEnum.ASSET,
) -> uuid.UUID:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = LedgerAccountRow(
            tenant_id=uuid.UUID(tenant_id),
            code=code,
            name=name,
            type=type_,
        )
        s.add(row)
        await s.commit()
        return row.id


async def _insert_line(
    *,
    tenant_id: str,
    account_id: uuid.UUID,
    debit: Decimal = Decimal("0.00"),
    credit: Decimal = Decimal("0.00"),
    posted_at: datetime | None = None,
    entry_id: uuid.UUID | None = None,
    line_no: int = 1,
) -> None:
    sm = db_module.get_sessionmaker()
    async with sm() as s:
        row = JournalEntryRow(
            entry_id=entry_id or uuid.uuid4(),
            line_no=line_no,
            tenant_id=uuid.UUID(tenant_id),
            account_id=account_id,
            debit=debit,
            credit=credit,
            posted_at=posted_at or datetime.now(timezone.utc),
        )
        s.add(row)
        await s.commit()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_trial_balance_unauth_returns_401(client: TestClient) -> None:
    r = client.get("/reports/trial-balance")
    assert r.status_code == 401


def test_trial_balance_empty_tenant_returns_zero_totals(
    client: TestClient,
) -> None:
    signup = _sign_up(
        client, email="alice@a.com", agency="Alice Travel"
    )
    access = signup["access_token"]
    r = client.get(
        "/reports/trial-balance",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == signup["user"]["tenant_id"]
    assert body["accounts"] == []
    assert body["total_debit"] == "0.00"
    assert body["total_credit"] == "0.00"
    assert body["in_balance"] is True


async def test_trial_balance_with_balanced_entries_totals_match(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tid = signup["user"]["tenant_id"]
    access = signup["access_token"]

    cash = await _insert_account(
        tenant_id=tid, code="1000", name="Cash",
        type_=LedgerAccountTypeEnum.ASSET,
    )
    ar = await _insert_account(
        tenant_id=tid, code="1200", name="Accounts Receivable",
        type_=LedgerAccountTypeEnum.ASSET,
    )
    rev = await _insert_account(
        tenant_id=tid, code="4000", name="Sales Revenue",
        type_=LedgerAccountTypeEnum.REVENUE,
    )

    # Entry 1: Dr Cash 100, Cr Revenue 100
    eid = uuid.uuid4()
    await _insert_line(
        tenant_id=tid, account_id=cash, debit=Decimal("100.00"),
        entry_id=eid, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("100.00"),
        entry_id=eid, line_no=2,
    )
    # Entry 2: Dr AR 50, Cr Revenue 50
    eid2 = uuid.uuid4()
    await _insert_line(
        tenant_id=tid, account_id=ar, debit=Decimal("50.00"),
        entry_id=eid2, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("50.00"),
        entry_id=eid2, line_no=2,
    )

    r = client.get(
        "/reports/trial-balance",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_debit"] == "150.00"
    assert body["total_credit"] == "150.00"
    assert body["in_balance"] is True
    codes = [a["code"] for a in body["accounts"]]
    assert codes == ["1000", "1200", "4000"]
    by_code = {a["code"]: a for a in body["accounts"]}
    assert by_code["1000"]["debit"] == "100.00"
    assert by_code["1000"]["credit"] == "0.00"
    assert by_code["1000"]["balance"] == "100.00"
    assert by_code["4000"]["credit"] == "150.00"
    assert by_code["4000"]["balance"] == "-150.00"


async def test_trial_balance_as_of_excludes_future_entries(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tid = signup["user"]["tenant_id"]
    access = signup["access_token"]

    cash = await _insert_account(
        tenant_id=tid, code="1000", name="Cash",
    )
    rev = await _insert_account(
        tenant_id=tid, code="4000", name="Revenue",
        type_=LedgerAccountTypeEnum.REVENUE,
    )
    # Included entry — dated 2026-05-01.
    eid1 = uuid.uuid4()
    early = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    await _insert_line(
        tenant_id=tid, account_id=cash, debit=Decimal("10.00"),
        posted_at=early, entry_id=eid1, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("10.00"),
        posted_at=early, entry_id=eid1, line_no=2,
    )
    # Excluded entry — dated 2026-06-01.
    eid2 = uuid.uuid4()
    late = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    await _insert_line(
        tenant_id=tid, account_id=cash, debit=Decimal("999.00"),
        posted_at=late, entry_id=eid2, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("999.00"),
        posted_at=late, entry_id=eid2, line_no=2,
    )

    r = client.get(
        "/reports/trial-balance?as_of=2026-05-15",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["as_of"] == "2026-05-15"
    assert body["total_debit"] == "10.00"
    assert body["total_credit"] == "10.00"


async def test_trial_balance_tenant_isolation(client: TestClient) -> None:
    a = _sign_up(client, email="alice@a.com", agency="A")
    b = _sign_up(client, email="bob@b.com", agency="B")
    a_tid = a["user"]["tenant_id"]
    b_tid = b["user"]["tenant_id"]

    a_cash = await _insert_account(tenant_id=a_tid, code="1000", name="Cash")
    a_rev = await _insert_account(
        tenant_id=a_tid, code="4000", name="Rev",
        type_=LedgerAccountTypeEnum.REVENUE,
    )
    b_cash = await _insert_account(tenant_id=b_tid, code="1000", name="Cash")
    b_rev = await _insert_account(
        tenant_id=b_tid, code="4000", name="Rev",
        type_=LedgerAccountTypeEnum.REVENUE,
    )

    eid = uuid.uuid4()
    await _insert_line(
        tenant_id=a_tid, account_id=a_cash, debit=Decimal("123.00"),
        entry_id=eid, line_no=1,
    )
    await _insert_line(
        tenant_id=a_tid, account_id=a_rev, credit=Decimal("123.00"),
        entry_id=eid, line_no=2,
    )
    eid2 = uuid.uuid4()
    await _insert_line(
        tenant_id=b_tid, account_id=b_cash, debit=Decimal("456.00"),
        entry_id=eid2, line_no=1,
    )
    await _insert_line(
        tenant_id=b_tid, account_id=b_rev, credit=Decimal("456.00"),
        entry_id=eid2, line_no=2,
    )

    r_a = client.get(
        "/reports/trial-balance",
        headers={"Authorization": f"Bearer {a['access_token']}"},
    )
    assert r_a.json()["total_debit"] == "123.00"
    r_b = client.get(
        "/reports/trial-balance",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert r_b.json()["total_debit"] == "456.00"


async def test_trial_balance_include_zero_flag(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tid = signup["user"]["tenant_id"]
    access = signup["access_token"]

    a1 = await _insert_account(tenant_id=tid, code="1000", name="Cash")
    await _insert_account(tenant_id=tid, code="1200", name="AR")
    await _insert_account(tenant_id=tid, code="2100", name="AP",
                          type_=LedgerAccountTypeEnum.LIABILITY)
    rev = await _insert_account(
        tenant_id=tid, code="4000", name="Rev",
        type_=LedgerAccountTypeEnum.REVENUE,
    )
    eid = uuid.uuid4()
    await _insert_line(
        tenant_id=tid, account_id=a1, debit=Decimal("10.00"),
        entry_id=eid, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("10.00"),
        entry_id=eid, line_no=2,
    )

    r0 = client.get(
        "/reports/trial-balance?include_zero=0",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r0.status_code == 200
    assert len(r0.json()["accounts"]) == 2  # only Cash + Rev

    r1 = client.get(
        "/reports/trial-balance?include_zero=1",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r1.status_code == 200
    assert len(r1.json()["accounts"]) == 4


async def test_trial_balance_ordered_by_account_code(
    client: TestClient,
) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tid = signup["user"]["tenant_id"]
    access = signup["access_token"]

    for code in ("3000", "1000", "2000"):
        await _insert_account(tenant_id=tid, code=code, name=f"X-{code}")

    r = client.get(
        "/reports/trial-balance?include_zero=1",
        headers={"Authorization": f"Bearer {access}"},
    )
    codes = [a["code"] for a in r.json()["accounts"]]
    assert codes == ["1000", "2000", "3000"]


async def test_trial_balance_decimal_precision(client: TestClient) -> None:
    signup = _sign_up(client, email="alice@a.com", agency="A")
    tid = signup["user"]["tenant_id"]
    access = signup["access_token"]

    cash = await _insert_account(tenant_id=tid, code="1000", name="Cash")
    rev = await _insert_account(
        tenant_id=tid, code="4000", name="Rev",
        type_=LedgerAccountTypeEnum.REVENUE,
    )
    eid = uuid.uuid4()
    await _insert_line(
        tenant_id=tid, account_id=cash, debit=Decimal("1234.56"),
        entry_id=eid, line_no=1,
    )
    await _insert_line(
        tenant_id=tid, account_id=rev, credit=Decimal("1234.56"),
        entry_id=eid, line_no=2,
    )
    r = client.get(
        "/reports/trial-balance",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = r.json()
    by_code = {a["code"]: a for a in body["accounts"]}
    assert by_code["1000"]["debit"] == "1234.56"
    assert by_code["4000"]["credit"] == "1234.56"
    assert body["total_debit"] == "1234.56"
    assert body["total_credit"] == "1234.56"
