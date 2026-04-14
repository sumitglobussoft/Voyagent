"""Tests for :mod:`schemas.canonical.airports`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from schemas.canonical import (
    IATA_TIMEZONE,
    apply_airport_timezone,
    resolve_airport_tz,
)


# --------------------------------------------------------------------------- #
# resolve_airport_tz                                                          #
# --------------------------------------------------------------------------- #


class TestResolveAirportTz:
    def test_bom_resolves_to_asia_kolkata(self) -> None:
        assert resolve_airport_tz("BOM") == "Asia/Kolkata"

    def test_case_insensitive(self) -> None:
        assert resolve_airport_tz("bom") == "Asia/Kolkata"
        assert resolve_airport_tz(" BoM ") == "Asia/Kolkata"

    def test_unknown_airport_returns_none(self) -> None:
        assert resolve_airport_tz("xyz") is None
        assert resolve_airport_tz("") is None

    def test_overrides_take_precedence(self) -> None:
        # Pretend an ops team has pinned BOM to a different zone for
        # testing. The override wins over the bundled registry.
        assert (
            resolve_airport_tz("BOM", overrides={"BOM": "UTC"}) == "UTC"
        )

    def test_overrides_add_new_codes(self) -> None:
        assert resolve_airport_tz("ABC") is None
        assert (
            resolve_airport_tz("ABC", overrides={"ABC": "Europe/Paris"})
            == "Europe/Paris"
        )

    def test_registry_hub_coverage(self) -> None:
        # A sanity sweep that the curated registry hasn't drifted on the
        # hubs that Voyagent sees daily.
        hubs = {
            "BOM": "Asia/Kolkata",
            "DEL": "Asia/Kolkata",
            "DXB": "Asia/Dubai",
            "DOH": "Asia/Qatar",
            "LHR": "Europe/London",
            "CDG": "Europe/Paris",
            "FRA": "Europe/Berlin",
            "JFK": "America/New_York",
            "LAX": "America/Los_Angeles",
            "SIN": "Asia/Singapore",
            "HKG": "Asia/Hong_Kong",
            "NRT": "Asia/Tokyo",
            "SYD": "Australia/Sydney",
            "JNB": "Africa/Johannesburg",
        }
        for code, expected in hubs.items():
            assert IATA_TIMEZONE[code] == expected


# --------------------------------------------------------------------------- #
# apply_airport_timezone                                                      #
# --------------------------------------------------------------------------- #


class TestApplyAirportTimezone:
    def test_bom_wall_time_converts_to_utc(self) -> None:
        # 14:30 IST on 2026-04-14 is 09:00 UTC.
        local = datetime(2026, 4, 14, 14, 30)
        got = apply_airport_timezone("BOM", local)
        assert got.utcoffset() == timedelta(0)
        assert got == datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc)

    def test_dxb_wall_time_converts_to_utc(self) -> None:
        # 15:45 GST on 2026-04-14 is 11:45 UTC (GST is UTC+4, no DST).
        local = datetime(2026, 4, 14, 15, 45)
        got = apply_airport_timezone("DXB", local)
        assert got == datetime(2026, 4, 14, 11, 45, tzinfo=timezone.utc)

    def test_dst_boundary_london(self) -> None:
        # London: BST (UTC+1) starts last Sunday of March; 2026-04-14 is BST.
        local = datetime(2026, 4, 14, 10, 0)
        got = apply_airport_timezone("LHR", local)
        assert got == datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc)

    def test_tz_aware_input_raises(self) -> None:
        aware = datetime(2026, 4, 14, 14, 30, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="naive datetime"):
            apply_airport_timezone("BOM", aware)

    def test_unknown_airport_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown IATA"):
            apply_airport_timezone("XYZ", datetime(2026, 4, 14, 10, 0))
