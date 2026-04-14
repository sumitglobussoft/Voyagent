"""Curated IATA airline-designator allow-list for HAF validation.

The HAF parser uses this set as a sanity check: each ``BKS*`` record's
``airline_code`` must be (a) two ASCII uppercase alphanumerics and
(b) present in :data:`KNOWN_IATA_AIRLINE_CODES`. This guards against
column-misalignment bugs (a slice landing on narration whitespace will
fail the regex; a slice landing on a document-number digit pair will
fail the set membership).

**Scope.** This is *not* an exhaustive catalogue of every IATA carrier
code ever issued — that changes weekly and sourcing it is outside the
driver's remit. We curate the ~150 carriers most likely to appear on
an Indian BSP statement (domestic carriers, GCC/Asia heavy haulers,
the major European and North American flags, notable LCCs, and a few
cargo-heavy names). Add codes here as tenants flag false-positives;
don't try to be exhaustive.

Codes are uppercase ASCII. Numeric carriers (``0B``, ``2A``, ``9W``,
``6E``, ``5J``) are included because IATA assigns digit-prefixed
designators for many LCCs. Controlled-duplicate IATA codes (letters
reused after retirement) are folded in without versioning — this
allow-list is intentionally generous, not forensic.
"""

from __future__ import annotations

import re
from typing import Final

# Matches a plausible IATA 2-char carrier designator: uppercase letter or
# digit pair. The IATA standard also allows a trailing asterisk variant
# (controlled-duplicate marker) but those never appear in HAF records.
IATA_AIRLINE_CODE_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{2}$")


# --------------------------------------------------------------------- #
# Curated set                                                            #
# --------------------------------------------------------------------- #
# Grouped by geography for review ergonomics; the runtime treats the set
# as flat. If you add entries, keep the groupings alphabetical within.

_INDIA_AND_SUBCONTINENT: Final[frozenset[str]] = frozenset(
    {
        "AI",  # Air India
        "IX",  # Air India Express
        "6E",  # IndiGo
        "SG",  # SpiceJet
        "QP",  # Akasa Air
        "UK",  # Vistara (legacy, merging into AI)
        "I5",  # AirAsia India (legacy)
        "G8",  # GoAir / Go First (legacy)
        "S2",  # JetLite (legacy)
        "9W",  # Jet Airways (legacy)
        "2T",  # TruJet (legacy)
        "BG",  # Biman Bangladesh
        "BS",  # US-Bangla
        "UL",  # SriLankan Airlines
        "RA",  # Nepal Airlines
        "PK",  # Pakistan International
        "ER",  # Serene Air
        "PF",  # AirBlue
        "DV",  # Druk Air (Bhutan)
    }
)

_GULF_AND_MIDDLE_EAST: Final[frozenset[str]] = frozenset(
    {
        "EK",  # Emirates
        "EY",  # Etihad
        "QR",  # Qatar Airways
        "SV",  # Saudia
        "GF",  # Gulf Air
        "WY",  # Oman Air
        "KU",  # Kuwait Airways
        "RJ",  # Royal Jordanian
        "ME",  # Middle East Airlines
        "FZ",  # flydubai
        "G9",  # Air Arabia
        "XY",  # flynas
        "IY",  # Yemenia
        "LY",  # El Al
        "IR",  # Iran Air
        "TK",  # Turkish Airlines
        "PC",  # Pegasus
    }
)

_EAST_AND_SE_ASIA: Final[frozenset[str]] = frozenset(
    {
        "SQ",  # Singapore Airlines
        "TR",  # Scoot
        "MI",  # SilkAir (legacy, merged into SQ)
        "TG",  # Thai Airways
        "TW",  # Thai Smile (legacy)
        "FD",  # Thai AirAsia
        "VN",  # Vietnam Airlines
        "VJ",  # VietJet
        "MH",  # Malaysia Airlines
        "OD",  # Batik Air Malaysia
        "AK",  # AirAsia
        "D7",  # AirAsia X
        "GA",  # Garuda Indonesia
        "JT",  # Lion Air
        "QZ",  # Indonesia AirAsia
        "ID",  # Batik Air Indonesia
        "PR",  # Philippine Airlines
        "5J",  # Cebu Pacific
        "Z2",  # Philippines AirAsia
        "CX",  # Cathay Pacific
        "KA",  # Cathay Dragon (legacy)
        "HX",  # Hong Kong Airlines
        "UO",  # HK Express
        "CI",  # China Airlines
        "BR",  # EVA Air
        "B7",  # Uni Air
        "OZ",  # Asiana
        "KE",  # Korean Air
        "7C",  # Jeju Air
        "LJ",  # Jin Air
        "NH",  # ANA
        "JL",  # JAL
        "MM",  # Peach
        "BC",  # Skymark
        "CA",  # Air China
        "MU",  # China Eastern
        "CZ",  # China Southern
        "HU",  # Hainan
        "3U",  # Sichuan Airlines
        "FM",  # Shanghai Airlines
        "MF",  # Xiamen Airlines
        "SC",  # Shandong Airlines
        "KL",  # KLM (global, listed here for flow)
    }
)

_EUROPE: Final[frozenset[str]] = frozenset(
    {
        "BA",  # British Airways
        "VS",  # Virgin Atlantic
        "AF",  # Air France
        "LH",  # Lufthansa
        "LX",  # Swiss
        "OS",  # Austrian
        "SN",  # Brussels
        "KM",  # Air Malta
        "IB",  # Iberia
        "UX",  # Air Europa
        "AY",  # Finnair
        "SK",  # SAS
        "AZ",  # ITA Airways
        "TP",  # TAP Portugal
        "LO",  # LOT Polish
        "OK",  # Czech Airlines
        "RO",  # TAROM
        "JU",  # Air Serbia
        "OU",  # Croatia Airlines
        "A3",  # Aegean
        "SU",  # Aeroflot
        "S7",  # S7 Airlines
        "U6",  # Ural Airlines
        "FI",  # Icelandair
        "DY",  # Norwegian
        "D8",  # Norwegian Air International
        "BT",  # airBaltic
        "EI",  # Aer Lingus
        "FR",  # Ryanair
        "U2",  # easyJet
        "W6",  # Wizz Air
        "HV",  # Transavia
        "VY",  # Vueling
        "EW",  # Eurowings
    }
)

_AMERICAS: Final[frozenset[str]] = frozenset(
    {
        "AA",  # American
        "DL",  # Delta
        "UA",  # United
        "AS",  # Alaska
        "B6",  # JetBlue
        "WN",  # Southwest
        "F9",  # Frontier
        "NK",  # Spirit
        "HA",  # Hawaiian
        "AC",  # Air Canada
        "WS",  # WestJet
        "TS",  # Air Transat
        "AM",  # Aeromexico
        "Y4",  # Volaris
        "VB",  # Viva Aerobus
        "CM",  # Copa
        "LA",  # LATAM
        "AR",  # Aerolineas Argentinas
        "G3",  # Gol
        "AD",  # Azul
        "AV",  # Avianca
        "H2",  # Sky Airline
        "JA",  # JetSMART
        "P5",  # Wingo
        "4M",  # LATAM Argentina (legacy)
    }
)

_AFRICA: Final[frozenset[str]] = frozenset(
    {
        "ET",  # Ethiopian
        "KQ",  # Kenya Airways
        "SA",  # South African Airways
        "MS",  # EgyptAir
        "AT",  # Royal Air Maroc
        "TU",  # Tunisair
        "AH",  # Air Algerie
        "MK",  # Air Mauritius
        "TM",  # LAM Mozambique
        "WB",  # RwandAir
        "UR",  # Uganda Airlines
        "PW",  # Precision Air
    }
)

_OCEANIA: Final[frozenset[str]] = frozenset(
    {
        "QF",  # Qantas
        "JQ",  # Jetstar
        "VA",  # Virgin Australia
        "NZ",  # Air New Zealand
        "FJ",  # Fiji Airways
    }
)

_CARGO_AND_MISC: Final[frozenset[str]] = frozenset(
    {
        "FX",  # FedEx
        "5X",  # UPS
        "5Y",  # Atlas Air
        "GG",  # Air Cargo Carriers
        "CV",  # Cargolux
        "LD",  # Air Hong Kong
        "RU",  # AirBridgeCargo (legacy)
        "K4",  # Kalitta Air
        "7L",  # Aircompany SCAT (misc)
    }
)


KNOWN_IATA_AIRLINE_CODES: Final[frozenset[str]] = (
    _INDIA_AND_SUBCONTINENT
    | _GULF_AND_MIDDLE_EAST
    | _EAST_AND_SE_ASIA
    | _EUROPE
    | _AMERICAS
    | _AFRICA
    | _OCEANIA
    | _CARGO_AND_MISC
)


def is_known_iata_airline(code: str) -> bool:
    """Return ``True`` if ``code`` matches the IATA pattern and is in the allow-list."""
    if not IATA_AIRLINE_CODE_RE.match(code):
        return False
    return code in KNOWN_IATA_AIRLINE_CODES


__all__ = [
    "IATA_AIRLINE_CODE_RE",
    "KNOWN_IATA_AIRLINE_CODES",
    "is_known_iata_airline",
]
