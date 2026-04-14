"""Pure functions that parse Tally Gateway Server responses.

Tally is case-insensitive with tag names in practice — the gateway
accepts ``<VOUCHER>`` or ``<Voucher>`` interchangeably and sometimes
echoes one casing even when the request used another. This module
normalises via ``local-name()``-style matching (implemented by walking
the tree with :meth:`Element.iter` and comparing ``.tag.lower()``).

Each parser raises :class:`ValidationFailedError` on any malformed
input rather than propagating an :class:`AttributeError` or
:class:`KeyError`. Response-level Tally error envelopes
(``<LINEERROR>``) are handled by :mod:`drivers.tally.errors` and are
deliberately not special-cased here — the parsers assume their input
is a success body.
"""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree
from pydantic import BaseModel, ConfigDict, Field

from drivers._contracts.errors import ValidationFailedError

from .errors import DRIVER_NAME

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helper models                                                               #
# --------------------------------------------------------------------------- #


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TallyCompanyInfo(_Strict):
    """Minimal subset of Tally's Company Info response used for ping."""

    company_name: str
    books_from_date: str | None = Field(default=None)
    currency: str | None = Field(default=None)


class TallyLedger(_Strict):
    """Driver-layer row for one Tally Ledger master."""

    name: str
    parent: str | None = Field(default=None)
    opening_balance_str: str | None = Field(default=None)
    currency: str | None = Field(default=None)


class TallyVoucherAck(_Strict):
    """The ack Tally returns after a successful voucher import."""

    created: int = 0
    altered: int = 0
    last_vch_id: str | None = None


# --------------------------------------------------------------------------- #
# Internal parsing helpers                                                    #
# --------------------------------------------------------------------------- #


def _parse_xml(body: bytes, ctx: str) -> etree._Element:
    if body is None or not body.strip():
        raise ValidationFailedError(
            DRIVER_NAME, f"{ctx}: empty response body from Tally."
        )
    try:
        # ``recover=True`` tolerates Tally's occasional stray whitespace and
        # XML fragments that are missing a declaration. This is a deliberate
        # compromise — we still hard-fail if there's no valid root element.
        parser = etree.XMLParser(recover=True, remove_comments=True)
        root = etree.fromstring(body, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationFailedError(
            DRIVER_NAME, f"{ctx}: XML syntax error: {exc!s}"
        ) from exc
    if root is None:
        raise ValidationFailedError(
            DRIVER_NAME, f"{ctx}: no root element in response."
        )
    return root


def _iter_by_local_name(root: etree._Element, name: str) -> list[etree._Element]:
    """Return all descendants whose local tag-name (lowercased) matches."""
    target = name.lower()
    matches: list[etree._Element] = []
    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):  # skip comments / PIs
            continue
        if tag.split("}", 1)[-1].lower() == target:
            matches.append(el)
    return matches


def _first_text(root: etree._Element, name: str) -> str | None:
    """Return the stripped text of the first element with the given local name."""
    for el in _iter_by_local_name(root, name):
        if el.text is not None and el.text.strip():
            return el.text.strip()
    return None


def _child_text_map(el: etree._Element) -> dict[str, str]:
    """Collect direct-child text into a ``{lowercase-tag: text}`` dict."""
    out: dict[str, str] = {}
    for child in el:
        tag = child.tag
        if not isinstance(tag, str):
            continue
        key = tag.split("}", 1)[-1].lower()
        if child.text is not None:
            text = child.text.strip()
            if text:
                out.setdefault(key, text)
    return out


def _parse_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Public parsers                                                              #
# --------------------------------------------------------------------------- #


def parse_ping_response(body: bytes) -> TallyCompanyInfo:
    """Parse a Company Info export into :class:`TallyCompanyInfo`.

    Tolerant to Tally's field naming variation: both ``<NAME>`` and
    ``<COMPANYNAME>`` are accepted. If no recognisable company name is
    present the function raises :class:`ValidationFailedError`.
    """
    root = _parse_xml(body, "parse_ping_response")

    # Tally may wrap the response in <ENVELOPE><BODY><DATA>...</DATA></BODY></ENVELOPE>
    # or return bare fields. Search by local name regardless of depth.
    name = _first_text(root, "companyname") or _first_text(root, "name")
    if not name:
        raise ValidationFailedError(
            DRIVER_NAME,
            "parse_ping_response: could not locate a company name in response.",
        )
    books_from = _first_text(root, "booksfrom") or _first_text(root, "startingfrom")
    currency = _first_text(root, "basecurrencysymbol") or _first_text(root, "currencysymbol")
    return TallyCompanyInfo(
        company_name=name, books_from_date=books_from, currency=currency
    )


def parse_ledger_list(body: bytes) -> list[TallyLedger]:
    """Parse a 'List of Ledgers' collection into a list of :class:`TallyLedger`.

    Each ``<LEDGER>`` element yields one row. Tally usually carries the
    ledger name on the ``NAME`` attribute of ``<LEDGER>``; we also accept
    a child ``<NAME>`` element. Missing-parent ledgers still produce a
    row — the parent is ``None`` and mapping falls back to the default
    type with a warning (see :mod:`drivers.tally.mapping`).
    """
    root = _parse_xml(body, "parse_ledger_list")
    ledgers: list[TallyLedger] = []
    for el in _iter_by_local_name(root, "ledger"):
        name_attr = el.get("NAME") or el.get("name")
        children = _child_text_map(el)
        name = name_attr or children.get("name")
        if not name:
            # Skip malformed rows rather than aborting the whole list — a
            # single bad ledger should not wipe the chart of accounts.
            logger.warning("tally: skipping ledger without a name (keys=%s)", list(children))
            continue
        ledgers.append(
            TallyLedger(
                name=name,
                parent=children.get("parent"),
                opening_balance_str=children.get("openingbalance"),
                currency=children.get("currencysymbol"),
            )
        )
    return ledgers


def parse_voucher_create_response(body: bytes) -> TallyVoucherAck:
    """Parse the ack returned by a successful voucher import.

    Tally returns ``<CREATED>`` / ``<ALTERED>`` counts and optionally
    ``<LASTVCHID>``. Absent counts default to zero rather than raising —
    but a response with ``<CREATED>0</CREATED>`` and no ``<LASTVCHID>``
    is suspicious and callers should treat it as a soft failure. The
    driver layer does that check.
    """
    root = _parse_xml(body, "parse_voucher_create_response")
    created = _parse_int(_first_text(root, "created"))
    altered = _parse_int(_first_text(root, "altered"))
    last_id = _first_text(root, "lastvchid")
    return TallyVoucherAck(created=created, altered=altered, last_vch_id=last_id)


__all__ = [
    "TallyCompanyInfo",
    "TallyLedger",
    "TallyVoucherAck",
    "parse_ledger_list",
    "parse_ping_response",
    "parse_voucher_create_response",
]
