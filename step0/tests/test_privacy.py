from __future__ import annotations

from dataclasses import dataclass

from step0.guard import redact_context_copy, redact_context_in_place, redact_text


def test_redacts_ssn_written_dob_phone_and_email() -> None:
    text = "SSN 000-12-3344 DOB 1985-03-14 phone 555-201-3344 email sarah@example.com"
    masked = redact_text(text)
    assert "000-12-3344" not in masked
    assert "1985-03-14" not in masked
    assert "555-201-3344" not in masked
    assert "sarah@example.com" not in masked


def test_redacts_last_four_phrase() -> None:
    masked = redact_text("My SSN last four are 3-3-4-4")
    assert "3-3-4-4" not in masked
    assert "REDACTED_LAST4" in masked


def test_copy_redaction_does_not_mutate_original() -> None:
    original = {"messages": [{"content": "DOB is 1985-03-14"}]}
    safe = redact_context_copy(original)
    assert "1985-03-14" in original["messages"][0]["content"]
    assert "1985-03-14" not in safe["messages"][0]["content"]


def test_in_place_redaction_masks_mutable_context() -> None:
    context = {"content": "Call me at 555-201-3344"}
    redact_context_in_place(context)
    assert "555-201-3344" not in context["content"]


def test_unrelated_numeric_text_is_preserved() -> None:
    assert redact_text("My appointment is on 2026-12-03") == "My appointment is on [REDACTED_DOB]"
    assert redact_text("I need 4 tablets") == "I need 4 tablets"


def test_dataclass_text_field_is_redacted_on_copy() -> None:
    @dataclass
    class Message:
        content: str

    original = Message("SSN 000-12-3344")
    safe = redact_context_copy(original)
    assert original.content == "SSN 000-12-3344"
    assert "000-12-3344" not in safe.content
