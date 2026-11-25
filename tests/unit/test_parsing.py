from datetime import date

import pytest

from clinic.security.parsing import (
    DateParts,
    names_match,
    normalize_member_id,
    normalize_spoken_email,
    parse_date_parts,
    parse_dob,
    parse_last_four,
    parse_phone,
    spoken_digits,
)

TODAY = date(2026, 11, 25)


@pytest.mark.parametrize(
    "text",
    [
        "March 14, 1985",
        "March 14th 1985",
        "march fourteenth nineteen eighty-five",
        "March fourteen nineteen eighty five",
        "the 14th of March 1985",
        "fourteen March nineteen eighty five",
        "14 March 1985",
        "3/14/1985",
        "03-14-1985",
        "1985-03-14",
        "3/14/85",
        "March 14 85",
        "March 14 19 85",  # Deepgram numerals can split a spoken year
        "three fourteen nineteen eighty five",
        "My name is Sarah Johnson and my date of birth is March 14 1985",
        "born March 14 1985, last four 3344",
    ],
)
def test_spoken_and_written_dates_of_birth(text: str) -> None:
    assert parse_dob(text, today=TODAY) == date(1985, 3, 14)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("March thirty-first twenty twenty-six", date(2026, 3, 31)),
        ("twenty sixth of March twenty twenty", date(2020, 3, 26)),
        ("July twenty second nineteen ninety", date(1990, 7, 22)),
        ("may 5th 1990", date(1990, 5, 5)),
        ("November eighth, nineteen seventy-two", date(1972, 11, 8)),
    ],
)
def test_other_date_shapes(text: str, expected: date) -> None:
    assert parse_dob(text, today=TODAY) == expected


@pytest.mark.parametrize(
    "text",
    [
        "2026-02-30",  # impossible day
        "March 14",  # no year: never guessed
        "3/14/05",  # two-digit year that could be 1905 or 2005: ask instead
        "December 1 2026",  # in the future, cannot be a birth date
        "May I ask something",  # "may" without a number is not a month
        "nineteen eighty-five",
    ],
)
def test_incomplete_ambiguous_or_impossible_dates_are_not_guessed(text: str) -> None:
    assert parse_dob(text, today=TODAY) is None


def test_partial_date_split_across_turns_merges_and_keeps_newest_values() -> None:
    """The exact turns from the failed demo call: "March" / "3" / "19 85." / "1985."."""
    parts = DateParts()
    for turn in ("March", "3", "19 85."):
        parts = parse_date_parts(turn, today=TODAY).over(parts)
    assert (parts.month, parts.day, parts.year) == (3, 3, 1985)

    corrected = parse_date_parts("the 14th", today=TODAY).over(parts)
    assert corrected.to_date(today=TODAY) == date(1985, 3, 14)


@pytest.mark.parametrize("said", ["November 8th 19 70 3", "November 8th 1970 3"])
def test_year_split_by_speech_to_text_is_rejoined(said: str) -> None:
    """Regression from a live call: "nineteen seventy-three" arrived as "19 70" + "3"."""
    assert parse_dob(said, today=TODAY) == date(1973, 11, 8)


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("daniel.carter@gmail.com", "daniel.carter@gmail.com"),
        ("Daniel dot carter at g mail dot com.", "daniel.carter@gmail.com"),
        ("daniel dot carter at the rate gmail dot com", "daniel.carter@gmail.com"),
        ("It's daniel underscore carter at outlook dot com", "daniel_carter@outlook.com"),
        ("my email is ann dash lee at example dot co dot uk", "ann-lee@example.co.uk"),
        ("Daniel Carter @gmail.com", "danielcarter@gmail.com"),
        ("daniel dot carter", None),
        ("at gmail dot com", None),
    ],
)
def test_spoken_emails_are_normalized(said: str, expected: str | None) -> None:
    """Regression from live calls: spoken email addresses were rejected repeatedly."""
    assert normalize_spoken_email(said) == expected


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        # Every way the 48291 ID reached the agent on a live call.
        ("4 8 2 9 1", "48291"),
        ("4 8 2 9 1.", "48291"),
        ("48 291", "48291"),
        ("It's 48. $2.91.", "48291"),  # Deepgram smart_format turned "two ninety-one" into $2.91
        ("48 $2.91", "48291"),
        ("member ID is four eight two nine one", "48291"),
        ("forty-eight two ninety-one", "48291"),
        ("48291", "48291"),
        # Other real-world shapes
        ("A B C 1 2 3 4 5 6", "ABC123456"),
        ("XYZ-1234-5678", "XYZ12345678"),
        ("w 2 6 4 double 0 7", "W264007"),
    ],
)
def test_member_ids_are_normalized(heard: str, expected: str) -> None:
    assert normalize_member_id(heard) == expected


@pytest.mark.parametrize("heard", ["48", "$2.91", "Test", "I have insurance", "", "1 2 3"])
def test_unclear_member_ids_are_rejected_so_the_agent_asks_again(heard: str) -> None:
    assert normalize_member_id(heard) is None


def test_a_year_is_never_read_as_a_day() -> None:
    parts = parse_date_parts("19 85.", today=TODAY)
    assert (parts.day, parts.year) == (None, 1985)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3344", "3344"),
        ("33 44", "3344"),
        ("3-3-4-4", "3344"),
        ("three three four four", "3344"),
        ("thirty three forty four", "3344"),
        ("my last four is oh oh four four", "0044"),
        ("my last 4 are three three four four", "3344"),
        ("last four digits are double four oh one", "4401"),
        ("Oh, it is 3344", "3344"),  # an interjection "oh" is not a zero
        ("double four", None),
        ("33444", None),
        ("000-12-3344", None),
    ],
)
def test_parse_last_four(text: str, expected: str | None) -> None:
    assert parse_last_four(text) == expected


def test_spoken_digits_reports_spans_of_every_digit() -> None:
    text = "it's 33 44"
    digits, spans = spoken_digits(text)
    assert digits == "3344"
    assert [text[start:end] for start, end in spans] == ["33", "44"]


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("555-010-2020", "5550102020"),
        ("five five five zero one zero two zero two zero", "5550102020"),
        ("five five five two oh one three three four four", "5552013344"),
        ("1 555 010 2020", "5550102020"),
        ("555-010", None),
    ],
)
def test_parse_callback_phone(spoken: str, expected: str | None) -> None:
    assert parse_phone(spoken) == expected


def test_names_match_normalized_and_tolerant() -> None:
    assert names_match("Dr. Sarah Johnson", "SARAH JOHNSON")
    assert names_match("Sarah Johns0n", "Sarah Johnson")
    assert not names_match("Sarah Verylongname", "Sarah Johnson")
