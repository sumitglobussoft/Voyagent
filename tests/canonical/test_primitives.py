"""Tests for schemas.canonical.primitives.

Covers the invariants called out in docs/CANONICAL_MODEL.md and
docs/DECISIONS.md#d10: Money / TaxLine / Period / Address / Phone / ISO codes
/ EntityId.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from schemas.canonical import (
    Address,
    EntityId,
    Money,
    Period,
    Phone,
    TaxLine,
    TaxRegime,
)


# --------------------------------------------------------------------------- #
# Money                                                                       #
# --------------------------------------------------------------------------- #


class TestMoney:
    def test_money_rejects_float_amount(self) -> None:
        with pytest.raises(ValidationError):
            Money(amount=1234.56, currency="INR")

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1000", Decimal("1000")),
            ("1000.50", Decimal("1000.50")),
            (1000, Decimal("1000")),
            (0, Decimal("0")),
            ("-25.75", Decimal("-25.75")),
        ],
    )
    def test_money_coerces_str_and_int_to_decimal(self, raw: str | int, expected: Decimal) -> None:
        m = Money(amount=raw, currency="INR")
        assert m.amount == expected
        assert isinstance(m.amount, Decimal)

    def test_money_accepts_decimal_passthrough(self) -> None:
        d = Decimal("999.99")
        m = Money(amount=d, currency="USD")
        assert m.amount == d

    def test_money_addition_requires_same_currency(self) -> None:
        a = Money(amount=Decimal("100"), currency="INR")
        b = Money(amount=Decimal("50"), currency="USD")
        with pytest.raises(ValueError, match="different currencies"):
            _ = a + b

    def test_money_subtraction_requires_same_currency(self) -> None:
        a = Money(amount=Decimal("100"), currency="INR")
        b = Money(amount=Decimal("50"), currency="USD")
        with pytest.raises(ValueError, match="different currencies"):
            _ = a - b

    def test_money_addition_with_matching_currency(self) -> None:
        a = Money(amount=Decimal("100"), currency="INR")
        b = Money(amount=Decimal("50.25"), currency="INR")
        result = a + b
        assert result.amount == Decimal("150.25")
        assert result.currency == "INR"

    def test_money_subtraction_with_matching_currency(self) -> None:
        a = Money(amount=Decimal("100"), currency="INR")
        b = Money(amount=Decimal("30.50"), currency="INR")
        result = a - b
        assert result.amount == Decimal("69.50")
        assert result.currency == "INR"

    def test_money_negation_preserves_currency_and_flips_sign(self) -> None:
        a = Money(amount=Decimal("42.10"), currency="AED")
        neg = -a
        assert neg.amount == Decimal("-42.10")
        assert neg.currency == "AED"

    def test_money_negation_of_negative_becomes_positive(self) -> None:
        # Refunds are modeled with negative amounts; negating one returns a
        # positive, which is useful when constructing offset ledger lines.
        a = Money(amount=Decimal("-99.99"), currency="GBP")
        neg = -a
        assert neg.amount == Decimal("99.99")


# --------------------------------------------------------------------------- #
# TaxLine                                                                     #
# --------------------------------------------------------------------------- #


class TestTaxLine:
    def test_taxline_requires_taxable_and_tax_amount_to_share_currency(self) -> None:
        with pytest.raises(ValidationError, match="share a currency"):
            TaxLine(
                regime=TaxRegime.GST_INDIA,
                code="CGST",
                rate_bps=900,
                taxable_amount=Money(amount=Decimal("1000"), currency="INR"),
                tax_amount=Money(amount=Decimal("90"), currency="USD"),
            )

    def test_taxline_accepts_matching_currencies(self) -> None:
        line = TaxLine(
            regime=TaxRegime.GST_INDIA,
            code="CGST",
            rate_bps=900,
            taxable_amount=Money(amount=Decimal("1000"), currency="INR"),
            tax_amount=Money(amount=Decimal("90"), currency="INR"),
        )
        assert line.rate_bps == 900

    def test_taxline_rate_bps_zero_is_valid(self) -> None:
        # Zero-rated / out-of-scope items are common, e.g. TaxRegime.NONE.
        line = TaxLine(
            regime=TaxRegime.NONE,
            code="EXEMPT",
            rate_bps=0,
            taxable_amount=Money(amount=Decimal("500"), currency="INR"),
            tax_amount=Money(amount=Decimal("0"), currency="INR"),
        )
        assert line.rate_bps == 0

    def test_taxline_rate_bps_upper_bound(self) -> None:
        line = TaxLine(
            regime=TaxRegime.GST_INDIA,
            code="MAX",
            rate_bps=100_000,
            taxable_amount=Money(amount=Decimal("1"), currency="INR"),
            tax_amount=Money(amount=Decimal("1000"), currency="INR"),
        )
        assert line.rate_bps == 100_000

    @pytest.mark.parametrize("bad_rate", [-1, 100_001, 1_000_000])
    def test_taxline_rejects_rate_bps_outside_bounds(self, bad_rate: int) -> None:
        with pytest.raises(ValidationError):
            TaxLine(
                regime=TaxRegime.GST_INDIA,
                code="BAD",
                rate_bps=bad_rate,
                taxable_amount=Money(amount=Decimal("100"), currency="INR"),
                tax_amount=Money(amount=Decimal("10"), currency="INR"),
            )


# --------------------------------------------------------------------------- #
# Period                                                                      #
# --------------------------------------------------------------------------- #


class TestPeriod:
    def test_period_rejects_naive_start(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            Period(start=datetime(2026, 4, 14, 12, 0, 0))

    def test_period_rejects_naive_end(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            Period(
                start=datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 4, 15, 12, 0, 0),
            )

    def test_period_end_must_be_strictly_after_start(self) -> None:
        t = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError, match="strictly after"):
            Period(start=t, end=t)

    def test_period_end_before_start_raises(self) -> None:
        start = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 14, 11, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValidationError, match="strictly after"):
            Period(start=start, end=end)

    def test_period_accepts_utc_aware_datetimes(self) -> None:
        start = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 14, 13, 0, 0, tzinfo=timezone.utc)
        p = Period(start=start, end=end)
        assert p.start == start
        assert p.end == end

    def test_period_normalizes_non_utc_aware_datetimes_to_utc(self) -> None:
        # 12:00 in IST (+05:30) is 06:30 UTC. The validator must normalize.
        ist = timezone(timedelta(hours=5, minutes=30))
        start_ist = datetime(2026, 4, 14, 12, 0, 0, tzinfo=ist)
        end_ist = datetime(2026, 4, 14, 18, 0, 0, tzinfo=ist)
        p = Period(start=start_ist, end=end_ist)
        assert p.start.utcoffset() == timedelta(0)
        assert p.end is not None
        assert p.end.utcoffset() == timedelta(0)
        # Same instant, just expressed in UTC.
        assert p.start == start_ist
        assert p.end == end_ist

    def test_period_end_is_optional(self) -> None:
        start = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
        p = Period(start=start)
        assert p.end is None


# --------------------------------------------------------------------------- #
# Address                                                                     #
# --------------------------------------------------------------------------- #


class TestAddress:
    def test_address_accepts_valid_country_code(self) -> None:
        a = Address(country="IN", line1="42 MG Road", city="Bengaluru")
        assert a.country == "IN"

    @pytest.mark.parametrize("bad", ["in", "IND", "I", "1N", "i n"])
    def test_address_rejects_invalid_country_code(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            Address(country=bad, line1="x", city="y")

    def test_address_has_no_state_or_pincode_fields(self) -> None:
        # Globalization contract (D8): region/postal_code are the generic
        # forms. Explicit 'state' / 'pincode' attributes must not exist.
        assert "state" not in Address.model_fields
        assert "pincode" not in Address.model_fields
        assert "region" in Address.model_fields
        assert "postal_code" in Address.model_fields


# --------------------------------------------------------------------------- #
# Phone                                                                       #
# --------------------------------------------------------------------------- #


class TestPhone:
    @pytest.mark.parametrize(
        "good",
        [
            "+919876543210",
            "+14155552671",
            "+442071838750",
            "+971501234567",
        ],
    )
    def test_phone_accepts_valid_e164(self, good: str) -> None:
        p = Phone(e164=good)
        assert p.e164 == good

    @pytest.mark.parametrize(
        "bad",
        [
            "9876543210",       # missing '+'
            "+0123456789",      # leading 0 after '+'
            "+1",               # too short
            "+123456789012345678",  # too long (> 15 digits)
            "++919876543210",   # double '+'
            "+91 98765 43210",  # whitespace
            "+91-98765-43210",  # hyphens
        ],
    )
    def test_phone_rejects_non_e164(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            Phone(e164=bad)


# --------------------------------------------------------------------------- #
# EntityId                                                                    #
# --------------------------------------------------------------------------- #


class _EntityIdHolder(BaseModel):
    """Thin wrapper so we can exercise the EntityId pattern via Pydantic."""

    id: EntityId


class TestEntityId:
    @pytest.mark.parametrize(
        "good",
        [
            "018f1a2b-3c4d-7e5f-8abc-0123456789ab",
            "01900000-0000-7000-8000-000000000001",
            "01900000-0000-7000-9000-000000000004",
            "01900000-0000-7000-a000-000000000005",
            "01900000-0000-7000-b000-000000000006",
        ],
    )
    def test_entity_id_accepts_valid_uuidv7_shape(self, good: str) -> None:
        h = _EntityIdHolder(id=good)
        assert h.id == good

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "not-a-uuid",
            "018F1A2B-3C4D-7E5F-8ABC-0123456789AB",  # uppercase hex
            "018f1a2b-3c4d-4e5f-8abc-0123456789ab",  # version=4, not 7
            "018f1a2b-3c4d-7e5f-0abc-0123456789ab",  # variant nibble not 8/9/a/b
            "018f1a2b3c4d7e5f8abc0123456789ab",       # no hyphens
            "018f1a2b-3c4d-7e5f-8abc-0123456789ab-extra",
        ],
    )
    def test_entity_id_rejects_bad_shapes(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _EntityIdHolder(id=bad)
