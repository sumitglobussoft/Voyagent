"""Airport timezone registry — v0.

Canonical mapping from IATA airport code to IANA timezone name. Used by
drivers (Amadeus, future GDS drivers) that receive local wall times
without an offset and need to convert them to UTC on the way to
:class:`FlightSegment`.

Why curated and not derived from OpenFlights
--------------------------------------------
OpenFlights is the go-to public dataset for airport metadata, but it is
CC-BY-SA — importing it as a data source would leak into the license
surface of the whole project. For v0 we keep a hand-curated list of the
~300 airports Voyagent is realistically going to see in its first year.
The list is deliberately auditable: one entry per line, grouped by
region, with no programmatic derivation.

Audit notes
-----------
* Values are IANA zones (e.g. ``"Asia/Kolkata"``), never POSIX
  abbreviations (``"IST"``) — abbreviations are ambiguous.
* When a country has multiple zones (USA, Russia, Australia, Brazil,
  Canada, Indonesia, Mexico), each airport is pinned to the zone of its
  physical location, not the country's "default".
* If you add an entry, verify it against ``zoneinfo.available_timezones()``
  — a typo here silently returns UTC at runtime.

Scope limits
------------
Roughly 300 airports covered. General-aviation fields, tiny regional
airstrips, and seasonal/charter airports are intentionally absent. A
call with an unknown IATA returns ``None`` from :func:`resolve_airport_tz`
and the caller decides how to degrade (the Amadeus driver falls back to
UTC with a WARNING log breadcrumb).
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# --------------------------------------------------------------------------- #
# The curated registry.                                                       #
#                                                                             #
# Grouped by region for human auditability. Keep entries sorted by IATA       #
# within each region so diff review stays readable.                           #
# --------------------------------------------------------------------------- #

IATA_TIMEZONE: dict[str, str] = {
    # --------------------------------------------------------------- #
    # India (IST, Asia/Kolkata)                                       #
    # --------------------------------------------------------------- #
    "AMD": "Asia/Kolkata",  # Ahmedabad
    "ATQ": "Asia/Kolkata",  # Amritsar
    "BBI": "Asia/Kolkata",  # Bhubaneswar
    "BLR": "Asia/Kolkata",  # Bengaluru (Kempegowda)
    "BOM": "Asia/Kolkata",  # Mumbai (Chhatrapati Shivaji)
    "CCU": "Asia/Kolkata",  # Kolkata
    "COK": "Asia/Kolkata",  # Kochi
    "DEL": "Asia/Kolkata",  # Delhi (Indira Gandhi)
    "GAU": "Asia/Kolkata",  # Guwahati
    "GOI": "Asia/Kolkata",  # Goa (Dabolim)
    "HYD": "Asia/Kolkata",  # Hyderabad
    "IDR": "Asia/Kolkata",  # Indore
    "IXB": "Asia/Kolkata",  # Bagdogra
    "IXC": "Asia/Kolkata",  # Chandigarh
    "IXM": "Asia/Kolkata",  # Madurai
    "IXR": "Asia/Kolkata",  # Ranchi
    "IXZ": "Asia/Kolkata",  # Port Blair
    "JAI": "Asia/Kolkata",  # Jaipur
    "LKO": "Asia/Kolkata",  # Lucknow
    "MAA": "Asia/Kolkata",  # Chennai
    "NAG": "Asia/Kolkata",  # Nagpur
    "PAT": "Asia/Kolkata",  # Patna
    "PNQ": "Asia/Kolkata",  # Pune
    "STV": "Asia/Kolkata",  # Surat
    "TRV": "Asia/Kolkata",  # Trivandrum
    "VGA": "Asia/Kolkata",  # Vijayawada
    "VNS": "Asia/Kolkata",  # Varanasi
    "VTZ": "Asia/Kolkata",  # Visakhapatnam

    # --------------------------------------------------------------- #
    # Nepal / Sri Lanka / Bhutan / Bangladesh / Pakistan / Afghanistan #
    # --------------------------------------------------------------- #
    "CMB": "Asia/Colombo",        # Colombo
    "DAC": "Asia/Dhaka",          # Dhaka
    "ISB": "Asia/Karachi",        # Islamabad
    "KBL": "Asia/Kabul",          # Kabul
    "KHI": "Asia/Karachi",        # Karachi
    "KTM": "Asia/Kathmandu",      # Kathmandu
    "LHE": "Asia/Karachi",        # Lahore
    "MLE": "Indian/Maldives",     # Malé
    "PBH": "Asia/Thimphu",        # Paro

    # --------------------------------------------------------------- #
    # Gulf / Middle East                                              #
    # --------------------------------------------------------------- #
    "AMM": "Asia/Amman",          # Amman (Queen Alia)
    "AUH": "Asia/Dubai",          # Abu Dhabi
    "BAH": "Asia/Bahrain",        # Bahrain
    "BEY": "Asia/Beirut",         # Beirut
    "DMM": "Asia/Riyadh",         # Dammam
    "DOH": "Asia/Qatar",          # Doha (Hamad)
    "DWC": "Asia/Dubai",          # Dubai World Central
    "DXB": "Asia/Dubai",          # Dubai International
    "IKA": "Asia/Tehran",         # Tehran (Imam Khomeini)
    "JED": "Asia/Riyadh",         # Jeddah
    "KWI": "Asia/Kuwait",         # Kuwait
    "MCT": "Asia/Muscat",         # Muscat
    "MED": "Asia/Riyadh",         # Madinah
    "RUH": "Asia/Riyadh",         # Riyadh
    "SHJ": "Asia/Dubai",          # Sharjah
    "TLV": "Asia/Jerusalem",      # Tel Aviv (Ben Gurion)

    # --------------------------------------------------------------- #
    # Turkey / Caucasus / Central Asia                                #
    # --------------------------------------------------------------- #
    "ALA": "Asia/Almaty",         # Almaty
    "ASB": "Asia/Ashgabat",       # Ashgabat
    "AYT": "Europe/Istanbul",     # Antalya
    "BAK": "Asia/Baku",           # Baku (Heydar Aliyev, GYD)
    "EVN": "Asia/Yerevan",        # Yerevan
    "GYD": "Asia/Baku",           # Baku (Heydar Aliyev)
    "IST": "Europe/Istanbul",     # Istanbul
    "NQZ": "Asia/Almaty",         # Astana (Nursultan Nazarbayev)
    "SAW": "Europe/Istanbul",     # Istanbul Sabiha Gökçen
    "TAS": "Asia/Tashkent",       # Tashkent
    "TBS": "Asia/Tbilisi",        # Tbilisi

    # --------------------------------------------------------------- #
    # Europe — UK / Ireland                                           #
    # --------------------------------------------------------------- #
    "BFS": "Europe/London",       # Belfast International
    "BHX": "Europe/London",       # Birmingham
    "DUB": "Europe/Dublin",       # Dublin
    "EDI": "Europe/London",       # Edinburgh
    "GLA": "Europe/London",       # Glasgow
    "LCY": "Europe/London",       # London City
    "LGW": "Europe/London",       # London Gatwick
    "LHR": "Europe/London",       # London Heathrow
    "LTN": "Europe/London",       # London Luton
    "MAN": "Europe/London",       # Manchester
    "SNN": "Europe/Dublin",       # Shannon
    "STN": "Europe/London",       # London Stansted

    # --------------------------------------------------------------- #
    # Europe — Continental (Schengen + near neighbours)               #
    # --------------------------------------------------------------- #
    "AMS": "Europe/Amsterdam",    # Amsterdam
    "ARN": "Europe/Stockholm",    # Stockholm Arlanda
    "ATH": "Europe/Athens",       # Athens
    "BCN": "Europe/Madrid",       # Barcelona
    "BEG": "Europe/Belgrade",     # Belgrade
    "BER": "Europe/Berlin",       # Berlin Brandenburg
    "BRU": "Europe/Brussels",     # Brussels
    "BUD": "Europe/Budapest",     # Budapest
    "CDG": "Europe/Paris",        # Paris Charles de Gaulle
    "CPH": "Europe/Copenhagen",   # Copenhagen
    "DUS": "Europe/Berlin",       # Düsseldorf
    "FCO": "Europe/Rome",         # Rome Fiumicino
    "FRA": "Europe/Berlin",       # Frankfurt
    "GVA": "Europe/Zurich",       # Geneva
    "HAM": "Europe/Berlin",       # Hamburg
    "HEL": "Europe/Helsinki",     # Helsinki
    "KEF": "Atlantic/Reykjavik",  # Reykjavík Keflavík
    "LIS": "Europe/Lisbon",       # Lisbon
    "LUX": "Europe/Luxembourg",   # Luxembourg
    "MAD": "Europe/Madrid",       # Madrid
    "MLA": "Europe/Malta",        # Malta
    "MRS": "Europe/Paris",        # Marseille
    "MUC": "Europe/Berlin",       # Munich
    "MXP": "Europe/Rome",         # Milan Malpensa
    "NCE": "Europe/Paris",        # Nice
    "ORY": "Europe/Paris",        # Paris Orly
    "OSL": "Europe/Oslo",         # Oslo
    "OTP": "Europe/Bucharest",    # Bucharest
    "PMI": "Europe/Madrid",       # Palma de Mallorca
    "PRG": "Europe/Prague",       # Prague
    "RIX": "Europe/Riga",         # Riga
    "SOF": "Europe/Sofia",        # Sofia
    "SVO": "Europe/Moscow",       # Moscow Sheremetyevo
    "TLL": "Europe/Tallinn",      # Tallinn
    "VCE": "Europe/Rome",         # Venice
    "VIE": "Europe/Vienna",       # Vienna
    "VKO": "Europe/Moscow",       # Moscow Vnukovo
    "VNO": "Europe/Vilnius",      # Vilnius
    "WAW": "Europe/Warsaw",       # Warsaw Chopin
    "ZAG": "Europe/Zagreb",       # Zagreb
    "ZRH": "Europe/Zurich",       # Zurich

    # --------------------------------------------------------------- #
    # Russia (selected majors)                                        #
    # --------------------------------------------------------------- #
    "DME": "Europe/Moscow",       # Moscow Domodedovo
    "LED": "Europe/Moscow",       # St Petersburg

    # --------------------------------------------------------------- #
    # North America — USA                                             #
    # --------------------------------------------------------------- #
    "ANC": "America/Anchorage",   # Anchorage
    "ATL": "America/New_York",    # Atlanta
    "AUS": "America/Chicago",     # Austin
    "BNA": "America/Chicago",     # Nashville
    "BOS": "America/New_York",    # Boston
    "BWI": "America/New_York",    # Baltimore
    "CLT": "America/New_York",    # Charlotte
    "DCA": "America/New_York",    # Washington Reagan
    "DEN": "America/Denver",      # Denver
    "DFW": "America/Chicago",     # Dallas/Fort Worth
    "DTW": "America/Detroit",     # Detroit
    "EWR": "America/New_York",    # Newark
    "FLL": "America/New_York",    # Fort Lauderdale
    "HNL": "Pacific/Honolulu",    # Honolulu
    "HOU": "America/Chicago",     # Houston Hobby
    "IAD": "America/New_York",    # Washington Dulles
    "IAH": "America/Chicago",     # Houston Intercontinental
    "IND": "America/Indiana/Indianapolis",  # Indianapolis
    "JFK": "America/New_York",    # New York JFK
    "LAS": "America/Los_Angeles", # Las Vegas
    "LAX": "America/Los_Angeles", # Los Angeles
    "LGA": "America/New_York",    # New York LaGuardia
    "MCO": "America/New_York",    # Orlando
    "MDW": "America/Chicago",     # Chicago Midway
    "MIA": "America/New_York",    # Miami
    "MSP": "America/Chicago",     # Minneapolis/St. Paul
    "MSY": "America/Chicago",     # New Orleans
    "OAK": "America/Los_Angeles", # Oakland
    "ORD": "America/Chicago",     # Chicago O'Hare
    "PDX": "America/Los_Angeles", # Portland OR
    "PHL": "America/New_York",    # Philadelphia
    "PHX": "America/Phoenix",     # Phoenix (no DST)
    "RDU": "America/New_York",    # Raleigh-Durham
    "SAN": "America/Los_Angeles", # San Diego
    "SEA": "America/Los_Angeles", # Seattle
    "SFO": "America/Los_Angeles", # San Francisco
    "SJC": "America/Los_Angeles", # San Jose
    "SLC": "America/Denver",      # Salt Lake City
    "STL": "America/Chicago",     # St. Louis
    "TPA": "America/New_York",    # Tampa

    # --------------------------------------------------------------- #
    # North America — Canada                                          #
    # --------------------------------------------------------------- #
    "YEG": "America/Edmonton",    # Edmonton
    "YHZ": "America/Halifax",     # Halifax
    "YOW": "America/Toronto",     # Ottawa
    "YQB": "America/Toronto",     # Québec City
    "YUL": "America/Toronto",     # Montréal
    "YVR": "America/Vancouver",   # Vancouver
    "YWG": "America/Winnipeg",    # Winnipeg
    "YYC": "America/Edmonton",    # Calgary
    "YYZ": "America/Toronto",     # Toronto Pearson

    # --------------------------------------------------------------- #
    # North America — Mexico                                          #
    # --------------------------------------------------------------- #
    "CUN": "America/Cancun",      # Cancún (no DST)
    "GDL": "America/Mexico_City", # Guadalajara
    "MEX": "America/Mexico_City", # Mexico City
    "MTY": "America/Monterrey",   # Monterrey
    "SJD": "America/Mazatlan",    # Los Cabos
    "TIJ": "America/Tijuana",     # Tijuana

    # --------------------------------------------------------------- #
    # Latin America & Caribbean                                       #
    # --------------------------------------------------------------- #
    "BOG": "America/Bogota",      # Bogotá
    "CCS": "America/Caracas",     # Caracas
    "EZE": "America/Argentina/Buenos_Aires",  # Buenos Aires Ezeiza
    "GIG": "America/Sao_Paulo",   # Rio de Janeiro Galeão
    "GRU": "America/Sao_Paulo",   # São Paulo Guarulhos
    "HAV": "America/Havana",      # Havana
    "LIM": "America/Lima",        # Lima
    "MVD": "America/Montevideo",  # Montevideo
    "NAS": "America/Nassau",      # Nassau
    "PTY": "America/Panama",      # Panama City
    "SCL": "America/Santiago",    # Santiago de Chile
    "SDQ": "America/Santo_Domingo",  # Santo Domingo
    "SJO": "America/Costa_Rica",  # San José (Costa Rica)
    "SJU": "America/Puerto_Rico", # San Juan
    "UIO": "America/Guayaquil",   # Quito

    # --------------------------------------------------------------- #
    # East Asia                                                       #
    # --------------------------------------------------------------- #
    "CAN": "Asia/Shanghai",       # Guangzhou
    "CGK": "Asia/Jakarta",        # Jakarta
    "CGO": "Asia/Shanghai",       # Zhengzhou
    "CTU": "Asia/Shanghai",       # Chengdu
    "DPS": "Asia/Makassar",       # Denpasar (Bali)
    "FUK": "Asia/Tokyo",          # Fukuoka
    "HAN": "Asia/Bangkok",        # Hanoi
    "HGH": "Asia/Shanghai",       # Hangzhou
    "HKG": "Asia/Hong_Kong",      # Hong Kong
    "HKT": "Asia/Bangkok",        # Phuket
    "HND": "Asia/Tokyo",          # Tokyo Haneda
    "ICN": "Asia/Seoul",          # Seoul Incheon
    "KIX": "Asia/Tokyo",          # Osaka Kansai
    "KMG": "Asia/Shanghai",       # Kunming
    "KUL": "Asia/Kuala_Lumpur",   # Kuala Lumpur
    "MFM": "Asia/Macau",          # Macau
    "MNL": "Asia/Manila",         # Manila
    "NGO": "Asia/Tokyo",          # Nagoya
    "NRT": "Asia/Tokyo",          # Tokyo Narita
    "PEK": "Asia/Shanghai",       # Beijing Capital
    "PEN": "Asia/Kuala_Lumpur",   # Penang
    "PKX": "Asia/Shanghai",       # Beijing Daxing
    "PNH": "Asia/Phnom_Penh",     # Phnom Penh
    "PVG": "Asia/Shanghai",       # Shanghai Pudong
    "RGN": "Asia/Yangon",         # Yangon
    "SGN": "Asia/Ho_Chi_Minh",    # Ho Chi Minh City
    "SHA": "Asia/Shanghai",       # Shanghai Hongqiao
    "SIN": "Asia/Singapore",      # Singapore Changi
    "SZX": "Asia/Shanghai",       # Shenzhen
    "TAO": "Asia/Shanghai",       # Qingdao
    "TPE": "Asia/Taipei",         # Taipei Taoyuan
    "TSA": "Asia/Taipei",         # Taipei Songshan
    "ULN": "Asia/Ulaanbaatar",    # Ulaanbaatar
    "VTE": "Asia/Vientiane",      # Vientiane
    "XIY": "Asia/Shanghai",       # Xi'an
    "BKK": "Asia/Bangkok",        # Bangkok Suvarnabhumi
    "DMK": "Asia/Bangkok",        # Bangkok Don Mueang

    # --------------------------------------------------------------- #
    # Oceania                                                         #
    # --------------------------------------------------------------- #
    "ADL": "Australia/Adelaide",  # Adelaide
    "AKL": "Pacific/Auckland",    # Auckland
    "BNE": "Australia/Brisbane",  # Brisbane
    "CBR": "Australia/Sydney",    # Canberra
    "CHC": "Pacific/Auckland",    # Christchurch
    "CNS": "Australia/Brisbane",  # Cairns
    "DRW": "Australia/Darwin",    # Darwin
    "HBA": "Australia/Hobart",    # Hobart
    "MEL": "Australia/Melbourne", # Melbourne
    "NAN": "Pacific/Fiji",        # Nadi
    "OOL": "Australia/Brisbane",  # Gold Coast
    "PER": "Australia/Perth",     # Perth
    "SYD": "Australia/Sydney",    # Sydney
    "WLG": "Pacific/Auckland",    # Wellington
    "ZQN": "Pacific/Auckland",    # Queenstown

    # --------------------------------------------------------------- #
    # Additional Europe coverage (secondary hubs)                     #
    # --------------------------------------------------------------- #
    "AGP": "Europe/Madrid",       # Málaga
    "ALC": "Europe/Madrid",       # Alicante
    "BGO": "Europe/Oslo",         # Bergen
    "BLQ": "Europe/Rome",         # Bologna
    "BOD": "Europe/Paris",        # Bordeaux
    "BRS": "Europe/London",       # Bristol
    "CGN": "Europe/Berlin",       # Cologne
    "CLJ": "Europe/Bucharest",    # Cluj-Napoca
    "CRL": "Europe/Brussels",     # Brussels South Charleroi
    "EIN": "Europe/Amsterdam",    # Eindhoven
    "FAO": "Europe/Lisbon",       # Faro
    "GOT": "Europe/Stockholm",    # Gothenburg
    "HER": "Europe/Athens",       # Heraklion
    "KBP": "Europe/Kiev",         # Kyiv Boryspil
    "KRK": "Europe/Warsaw",       # Kraków
    "LJU": "Europe/Ljubljana",    # Ljubljana
    "NAP": "Europe/Rome",         # Naples
    "OPO": "Europe/Lisbon",       # Porto
    "SKG": "Europe/Athens",       # Thessaloniki
    "SVG": "Europe/Oslo",         # Stavanger
    "TFS": "Atlantic/Canary",     # Tenerife South
    "TRN": "Europe/Rome",         # Turin
    "TXL": "Europe/Berlin",       # Berlin Tegel (decommissioned but tickets still reference it)
    "WRO": "Europe/Warsaw",       # Wrocław

    # --------------------------------------------------------------- #
    # Additional Asia coverage                                        #
    # --------------------------------------------------------------- #
    "BWN": "Asia/Brunei",         # Bandar Seri Begawan
    "CEB": "Asia/Manila",         # Cebu
    "CJU": "Asia/Seoul",          # Jeju
    "CRK": "Asia/Manila",         # Clark
    "CXR": "Asia/Ho_Chi_Minh",    # Nha Trang
    "DAD": "Asia/Ho_Chi_Minh",    # Da Nang
    "DLC": "Asia/Shanghai",       # Dalian
    "HRB": "Asia/Shanghai",       # Harbin
    "KCH": "Asia/Kuching",        # Kuching
    "KIJ": "Asia/Tokyo",          # Niigata
    "KOJ": "Asia/Tokyo",          # Kagoshima
    "KWL": "Asia/Shanghai",       # Guilin
    "MDL": "Asia/Yangon",         # Mandalay
    "OKA": "Asia/Tokyo",          # Naha (Okinawa)
    "PUS": "Asia/Seoul",          # Busan
    "REP": "Asia/Phnom_Penh",     # Siem Reap
    "SPK": "Asia/Tokyo",          # Sapporo
    "SUB": "Asia/Jakarta",        # Surabaya
    "TSN": "Asia/Shanghai",       # Tianjin
    "URC": "Asia/Urumqi",         # Ürümqi
    "WUH": "Asia/Shanghai",       # Wuhan

    # --------------------------------------------------------------- #
    # Africa                                                          #
    # --------------------------------------------------------------- #
    "ABJ": "Africa/Abidjan",      # Abidjan
    "ACC": "Africa/Accra",        # Accra
    "ADD": "Africa/Addis_Ababa",  # Addis Ababa
    "ALG": "Africa/Algiers",      # Algiers
    "CAI": "Africa/Cairo",        # Cairo
    "CMN": "Africa/Casablanca",   # Casablanca
    "CPT": "Africa/Johannesburg", # Cape Town
    "DAR": "Africa/Dar_es_Salaam",  # Dar es Salaam
    "DKR": "Africa/Dakar",        # Dakar
    "DSS": "Africa/Dakar",        # Dakar Blaise Diagne
    "DUR": "Africa/Johannesburg", # Durban
    "EBB": "Africa/Kampala",      # Entebbe
    "HRE": "Africa/Harare",       # Harare
    "JNB": "Africa/Johannesburg", # Johannesburg
    "KGL": "Africa/Kigali",       # Kigali
    "LAD": "Africa/Luanda",       # Luanda
    "LOS": "Africa/Lagos",        # Lagos
    "LUN": "Africa/Lusaka",       # Lusaka
    "MBA": "Africa/Nairobi",      # Mombasa
    "MPM": "Africa/Maputo",       # Maputo
    "NBO": "Africa/Nairobi",      # Nairobi
    "RAK": "Africa/Casablanca",   # Marrakech
    "SEZ": "Indian/Mahe",         # Mahé (Seychelles)
    "TUN": "Africa/Tunis",        # Tunis
}


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def resolve_airport_tz(
    iata: str,
    *,
    overrides: dict[str, str] | None = None,
) -> str | None:
    """Return the IANA zone name for ``iata``, or ``None`` if unknown.

    Input is case-insensitive; the registry stores uppercase codes.
    ``overrides`` (if supplied) is consulted first so per-tenant
    configuration can correct or extend the bundled registry without
    forking this file.
    """
    if not iata:
        return None
    code = iata.strip().upper()
    if overrides:
        # overrides may be keyed in any case; normalise.
        for k, v in overrides.items():
            if k.strip().upper() == code:
                return v
    return IATA_TIMEZONE.get(code)


def apply_airport_timezone(
    iata: str,
    local_naive: datetime,
    *,
    overrides: dict[str, str] | None = None,
) -> datetime:
    """Interpret ``local_naive`` as wall time at ``iata`` and return UTC.

    Raises:
        ValueError: when ``local_naive`` is already tz-aware (explicit
            is better than a surprise round-trip) or when ``iata`` is
            not in the registry (caller decides how to degrade).

    The returned datetime is timezone-aware in ``UTC`` — safe to store
    in canonical fields that require UTC.
    """
    if local_naive.tzinfo is not None:
        raise ValueError(
            "apply_airport_timezone expects a naive datetime "
            "(wall time at the airport); got a tz-aware value."
        )
    zone_name = resolve_airport_tz(iata, overrides=overrides)
    if zone_name is None:
        raise ValueError(f"Unknown IATA airport code: {iata!r}.")
    local_aware = local_naive.replace(tzinfo=ZoneInfo(zone_name))
    return local_aware.astimezone(timezone.utc)


__all__ = [
    "IATA_TIMEZONE",
    "apply_airport_timezone",
    "resolve_airport_tz",
]
