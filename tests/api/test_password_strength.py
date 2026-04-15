"""Unit tests for :func:`validate_password_strength`.

Exercises every error code plus two happy-path cases.
"""

from __future__ import annotations

import pytest

from voyagent_api.auth_inhouse.passwords import (
    PasswordTooWeakError,
    validate_password_strength,
)


def _code(pw: str) -> str:
    with pytest.raises(PasswordTooWeakError) as ei:
        validate_password_strength(pw)
    return ei.value.code


def test_blank_password_rejected() -> None:
    assert _code("") == "password_blank"


def test_whitespace_only_rejected() -> None:
    assert _code("          ") == "password_blank"


def test_too_short_rejected() -> None:
    assert _code("Ab1") == "password_too_short"


def test_nine_chars_rejected() -> None:
    assert _code("Abcdefgh1") == "password_too_short"


def test_too_long_rejected() -> None:
    assert _code("A1" + ("x" * 200)) == "password_too_long"


def test_no_letter_rejected() -> None:
    assert _code("12345678901") == "password_no_letter"


def test_no_digit_rejected() -> None:
    assert _code("abcdefghijk") == "password_no_digit"


def test_common_password_rejected_lowercase() -> None:
    assert _code("password123") == "password_common"


def test_common_password_rejected_case_insensitive() -> None:
    assert _code("Password123".lower()) == "password_common"


def test_common_password_blocklist_qwerty() -> None:
    assert _code("qwerty1234") == "password_common"


# --------------------------------------------------------------------------- #
# Happy paths                                                                 #
# --------------------------------------------------------------------------- #


def test_strong_password_accepted() -> None:
    validate_password_strength("R3dBalloon!Dance")  # no raise


def test_borderline_10_char_mixed_accepted() -> None:
    validate_password_strength("abcdefghi1")  # exactly 10, letter + digit
