"""Tests for schemas.canonical.lifecycle.

Covers Enquiry's loose `requirements` dict, Document sha256 pattern, and
AuditEvent's default status.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest
from pydantic import ValidationError

from schemas.canonical import (
    ActorKind,
    AuditEvent,
    AuditStatus,
    Document,
    DocumentKind,
    Enquiry,
    EnquiryDomain,
    EnquiryStatus,
)


# --------------------------------------------------------------------------- #
# Enquiry                                                                     #
# --------------------------------------------------------------------------- #


class TestEnquiry:
    def test_enquiry_accepts_loose_requirements_dict(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        """`requirements` is deliberately dict[str, Any] at v0 so drivers and
        agents can evolve without schema churn. This test pins that."""
        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        enq = Enquiry(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            created_at=now,
            updated_at=now,
            client_id=make_entity_id(),
            domain=EnquiryDomain.TICKETING,
            requirements={
                "origin": "BLR",
                "destination": "DXB",
                "pax": {"adult": 2, "child": 1},
                "preferred_airlines": ["AI", "EK"],
                "notes": "window seats",
                "budget_inr": 120000,
            },
        )
        assert enq.status is EnquiryStatus.NEW
        assert enq.requirements["origin"] == "BLR"
        assert enq.requirements["pax"] == {"adult": 2, "child": 1}
        assert enq.requirements["preferred_airlines"] == ["AI", "EK"]

    def test_enquiry_requirements_defaults_to_empty_dict(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        enq = Enquiry(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            created_at=now,
            updated_at=now,
            client_id=make_entity_id(),
            domain=EnquiryDomain.MIXED,
        )
        assert enq.requirements == {}


# --------------------------------------------------------------------------- #
# Document                                                                   #
# --------------------------------------------------------------------------- #


def _document_kwargs(make_entity_id: Callable[[], str], sha256: str) -> dict:
    now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    return dict(
        id=make_entity_id(),
        tenant_id=make_entity_id(),
        created_at=now,
        updated_at=now,
        kind=DocumentKind.PASSPORT_SCAN,
        filename="passport.pdf",
        content_type="application/pdf",
        size_bytes=102400,
        storage_uri="s3://voyagent-docs/tenant-a/doc-1",
        sha256=sha256,
        uploaded_by=make_entity_id(),
    )


class TestDocument:
    def test_document_accepts_valid_sha256(self, make_entity_id: Callable[[], str]) -> None:
        good = "a" * 64
        doc = Document(**_document_kwargs(make_entity_id, good))
        assert doc.sha256 == good

    def test_document_accepts_mixed_hex_sha256(self, make_entity_id: Callable[[], str]) -> None:
        good = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        doc = Document(**_document_kwargs(make_entity_id, good))
        assert doc.sha256 == good

    @pytest.mark.parametrize(
        "bad_hash",
        [
            "",                                                              # empty
            "a" * 63,                                                        # too short
            "a" * 65,                                                        # too long
            "A" * 64,                                                        # uppercase hex
            "g" * 64,                                                        # non-hex char
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85",  # 63 chars
        ],
    )
    def test_document_rejects_bad_sha256(
        self, make_entity_id: Callable[[], str], bad_hash: str
    ) -> None:
        with pytest.raises(ValidationError):
            Document(**_document_kwargs(make_entity_id, bad_hash))


# --------------------------------------------------------------------------- #
# AuditEvent                                                                  #
# --------------------------------------------------------------------------- #


class TestAuditEvent:
    def test_audit_event_default_status_is_started(
        self, make_entity_id: Callable[[], str]
    ) -> None:
        event = AuditEvent(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            actor_id=make_entity_id(),
            actor_kind=ActorKind.AGENT,
            tool="issue_ticket",
            started_at=datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert event.status is AuditStatus.STARTED
