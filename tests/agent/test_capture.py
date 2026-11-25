"""The pre-LLM gate: DOB and SSN digits go to server state, never into the model's context."""

from datetime import date

import pytest
from agent_helpers import MakeState

from agent.capture import REDACTED, is_affirmative, sanitize_turn

ASK_DOB = "Could I have your date of birth?"
ASK_SSN = "And the last four digits of your Social Security number?"


def test_name_dob_and_last_four_in_one_sentence(make_state: MakeState) -> None:
    state = make_state()

    safe = sanitize_turn(
        "My name is Sarah Johnson, my date of birth is March 14, 1985 and my last four is 3344",
        state,
        last_agent_text="How can I help you today?",
    )

    assert state.captured_dob() == date(1985, 3, 14)
    assert state.last_four is not None and state.last_four.get_secret_value() == "3344"
    assert "Sarah Johnson" in safe  # the model needs the name to call verify_identity
    for leaked in ("March", "14", "1985", "3344"):
        assert leaked not in safe
    assert "date of birth received" in safe and "last four SSN digits received" in safe


def test_the_failed_demo_call_no_longer_uses_the_year_as_ssn(make_state: MakeState) -> None:
    """Regression: "March" / "3" / "19 85." / "1985." used to submit 1985 as the last four."""
    state = make_state()

    notes = [
        sanitize_turn(turn, state, last_agent_text=ASK_DOB)
        for turn in ("March", "3", "19 85.", "1985.")
    ]

    assert state.captured_dob() == date(1985, 3, 3)
    assert state.last_four is None
    assert "still need the day and year" in notes[0]
    assert "still need the year" in notes[1]
    assert all("19" not in note and "85" not in note for note in notes)


def test_voice_test_2_split_year_does_not_leak_into_ssn_digits(make_state: MakeState) -> None:
    """The caller's retry: a stray "3" used to join "1 0 2 0" and be discarded as 5 digits."""
    state = make_state()

    sanitize_turn(
        "My date of birth is November 8th 19 70 3, and the last 4 digits of my "
        "Social Security number are 1 0 2 0.",
        state,
        last_agent_text="Can I get your full name, date of birth, and last four?",
    )

    assert state.captured_dob() == date(1973, 11, 8)
    assert state.last_four is not None and state.last_four.get_secret_value() == "1020"


def test_dob_correction_replaces_the_previous_value(make_state: MakeState) -> None:
    state = make_state()
    sanitize_turn("March 3rd 1985", state, last_agent_text=ASK_DOB)

    sanitize_turn("Sorry, my birthday is the 14th", state, last_agent_text=ASK_SSN)

    assert state.captured_dob() == date(1985, 3, 14)


def test_ssn_answer_after_complete_dob_is_captured(make_state: MakeState) -> None:
    state = make_state()
    sanitize_turn("March 14 1985", state, last_agent_text=ASK_DOB)

    safe = sanitize_turn("thirty three forty four", state, last_agent_text=ASK_SSN)

    assert state.last_four is not None and state.last_four.get_secret_value() == "3344"
    assert safe.startswith(REDACTED)


@pytest.mark.parametrize("said", ["000-12-3344", "my social is 0 0 0 1 2 3 3 4 4"])
def test_full_ssn_is_discarded_never_kept(make_state: MakeState, said: str) -> None:
    state = make_state()

    safe = sanitize_turn(said, state, last_agent_text=ASK_SSN)

    assert state.last_four is None
    assert "3344" not in safe and "12" not in safe
    assert "ask for only the last four" in safe


def test_appointment_preferences_and_phone_numbers_pass_through(make_state: MakeState) -> None:
    state = make_state()

    preference = sanitize_turn(
        "Do you have anything on December 2nd in the morning?",
        state,
        last_agent_text="Which day works best for you?",
    )
    phone = sanitize_turn(
        "555 201 3344", state, last_agent_text="What's the best phone number for you?"
    )

    assert preference == "Do you have anything on December 2nd in the morning?"
    assert phone == "555 201 3344"
    assert state.dob.is_empty and state.last_four is None


def test_ssn_capture_stops_after_verification(make_state: MakeState) -> None:
    state = make_state(verified_patient="P001")

    safe = sanitize_turn("my last four is 3344", state, last_agent_text="")

    assert state.last_four is None
    assert safe == "my last four is 3344"


def test_invalid_date_of_birth_is_dropped_with_a_note(make_state: MakeState) -> None:
    state = make_state()

    safe = sanitize_turn("February 30th 1985", state, last_agent_text=ASK_DOB)

    assert state.dob.is_empty
    assert "not a valid past date" in safe


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yes", True),
        ("yeah, that's right", True),
        ("Correct.", True),
        ("That's correct, thanks", True),
        ("yes but change the time", False),
        ("No", False),
        ("wait, the email is wrong", False),
        ("I'm not sure", False),
    ],
)
def test_affirmative_detection(text: str, expected: bool) -> None:
    assert is_affirmative(text) is expected
