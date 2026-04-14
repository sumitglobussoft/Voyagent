"""Tests for schemas.canonical.identity.

Covers Passport date ordering, minimal gathering-phase Passenger construction,
and the SecretStr guarantee on NationalId.value.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable

import pytest
from pydantic import SecretStr, ValidationError

from schemas.canonical import (
    Gender,
    NationalId,
    NationalIdKind,
    Passenger,
    PassengerType,
    Passport,
)


# --------------------------------------------------------------------------- #
# Passport                                                                    #
# --------------------------------------------------------------------------- #


def _valid_passport_kwargs() -> dict:
    return dict(
        number="P1234567",
        issuing_country="IN",
        given_name="Asha",
        family_name="Rao",
        date_of_birth=date(1990, 5, 10),
        gender=Gender.FEMALE,
        issue_date=date(2020, 1, 1),
        expiry_date=date(2030, 1, 1),
    )


class TestPassport:
    def test_passport_expiry_must_be_after_issue(self) -> None:
        kwargs = _valid_passport_kwargs()
        kwargs["issue_date"] = date(2030, 1, 1)
        kwargs["expiry_date"] = date(2030, 1, 1)  # equal — not strictly after
        with pytest.raises(ValidationError, match="expiry_date must be after issue_date"):
            Passport(**kwargs)

    def test_passport_expiry_before_issue_raises(self) -> None:
        kwargs = _valid_passport_kwargs()
        kwargs["issue_date"] = date(2030, 1, 1)
        kwargs["expiry_date"] = date(2025, 1, 1)
        with pytest.raises(ValidationError, match="expiry_date must be after issue_date"):
            Passport(**kwargs)

    def test_passport_issue_must_be_after_date_of_birth(self) -> None:
        kwargs = _valid_passport_kwargs()
        kwargs["date_of_birth"] = date(2020, 1, 1)
        kwargs["issue_date"] = date(2020, 1, 1)  # equal — not strictly after
        kwargs["expiry_date"] = date(2030, 1, 1)
        with pytest.raises(ValidationError, match="issue_date must be after date_of_birth"):
            Passport(**kwargs)

    def test_passport_issue_before_dob_raises(self) -> None:
        kwargs = _valid_passport_kwargs()
        kwargs["date_of_birth"] = date(2020, 1, 1)
        kwargs["issue_date"] = date(2015, 1, 1)
        kwargs["expiry_date"] = date(2025, 1, 1)
        with pytest.raises(ValidationError, match="issue_date must be after date_of_birth"):
            Passport(**kwargs)

    def test_passport_with_ordered_dates_is_valid(self) -> None:
        p = Passport(**_valid_passport_kwargs())
        assert p.issuing_country == "IN"
        assert p.expiry_date > p.issue_date > p.date_of_birth

    def test_passport_number_is_stored_as_secretstr(self) -> None:
        # Not explicitly in D10, but worth pinning: passport numbers are PII.
        p = Passport(**_valid_passport_kwargs())
        assert isinstance(p.number, SecretStr)
        assert p.number.get_secret_value() == "P1234567"


# --------------------------------------------------------------------------- #
# Passenger                                                                   #
# --------------------------------------------------------------------------- #


class TestPassengerMinimalConstruction:
    def test_passenger_can_be_built_with_only_name_and_type_during_gathering(
        self,
        make_entity_id: Callable[[], str],
        utc_now: Callable[[], datetime],
    ) -> None:
        """A passenger may enter the system with only a name during
        EnquiryStatus.GATHERING — no passport, no DOB, no nationality yet."""
        now = utc_now()
        pax = Passenger(
            id=make_entity_id(),
            tenant_id=make_entity_id(),
            created_at=now,
            updated_at=now,
            type=PassengerType.ADULT,
            given_name="Asha",
            family_name="Rao",
        )
        assert pax.given_name == "Asha"
        assert pax.family_name == "Rao"
        assert pax.type is PassengerType.ADULT
        # All identity-carrying fields remain absent.
        assert pax.date_of_birth is None
        assert pax.gender is None
        assert pax.nationality is None
        assert pax.passport is None
        assert pax.national_ids == []
        assert pax.phones == []
        assert pax.emails == []
        assert pax.address is None


# --------------------------------------------------------------------------- #
# NationalId                                                                  #
# --------------------------------------------------------------------------- #


class TestNationalId:
    def test_national_id_value_is_stored_as_secretstr(self) -> None:
        nid = NationalId(
            country="IN",
            kind=NationalIdKind.AADHAAR,
            value="1234-5678-9012",
        )
        assert isinstance(nid.value, SecretStr)
        assert nid.value.get_secret_value() == "1234-5678-9012"

    def test_national_id_value_does_not_leak_in_repr(self) -> None:
        nid = NationalId(
            country="IN",
            kind=NationalIdKind.PAN,
            value="ABCDE1234F",
        )
        # SecretStr masks in repr/str — this is the whole point of wrapping.
        assert "ABCDE1234F" not in repr(nid)
        assert "ABCDE1234F" not in str(nid)
