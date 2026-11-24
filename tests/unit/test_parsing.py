from datetime import date

import pytest

from clinic.security.parsing import names_match, parse_dob, parse_last_four


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3344", "3344"),
        ("3-3-4-4", "3344"),
        ("three three four four", "3344"),
        ("double four", None),
        ("33 44", "3344"),
        ("my last four is oh oh four four", "0044"),
    ],
)
def test_parse_last_four(text: str, expected: str | None) -> None:
    assert parse_last_four(text) == expected


def test_parse_overlong_last_four() -> None:
    assert parse_last_four("33444") is None


def test_dob_formats() -> None:
    assert parse_dob("March 14, 1985") == date(1985, 3, 14)
    assert parse_dob("1985-03-14") == date(1985, 3, 14)
    assert parse_dob("03/14/1985") == date(1985, 3, 14)
    assert parse_dob("nineteen eighty-five") is None


def test_names_match_normalized_and_tolerant() -> None:
    assert names_match("Dr. Sarah Johnson", "SARAH JOHNSON")
    assert names_match("Sarah Johns0n", "Sarah Johnson")
    assert not names_match("Sarah Verylongname", "Sarah Johnson")
