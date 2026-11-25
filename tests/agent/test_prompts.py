from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from agent import phrases
from agent.prompts import render_prompt

NOW = datetime(2026, 11, 25, 14, 5, tzinfo=ZoneInfo("America/New_York"))


@pytest.mark.parametrize("name", ["receptionist", "after_hours"])
def test_prompts_render_with_clinic_time_and_no_leftover_placeholders(name: str) -> None:
    prompt = render_prompt(name, NOW)  # type: ignore[arg-type]

    assert "Wednesday, November 25, 2026, 02:05 PM Eastern Time" in prompt
    assert "$" not in prompt


def test_clinic_time_is_used_even_when_the_host_clock_is_elsewhere() -> None:
    utc_evening = datetime(2026, 11, 26, 2, 0, tzinfo=ZoneInfo("UTC"))  # 9 PM Eastern, Nov 25

    assert "Wednesday, November 25, 2026, 09:00 PM" in render_prompt("after_hours", utc_evening)


def test_receptionist_prompt_upcoming_days_come_from_code() -> None:
    prompt = render_prompt("receptionist", NOW)

    assert "Upcoming days: Wed Nov 25; Thu Nov 26; Fri Nov 27; Sat Nov 28" in prompt
    assert "Tue Dec 1" in prompt


@pytest.mark.parametrize("name", ["receptionist", "after_hours"])
def test_prompts_contain_no_patient_data(name: str) -> None:
    prompt = render_prompt(name, NOW)  # type: ignore[arg-type]

    for value in ("Sarah", "Johnson", "Michael", "Maria", "1985", "3344", "1020", "9081"):
        assert value not in prompt


def test_receptionist_prompt_covers_the_conversation_rules() -> None:
    prompt = " ".join(render_prompt("receptionist", NOW).casefold().split())

    for rule in (
        "never ask for something they already gave you",
        "never share, confirm or deny anything about another person",
        "never fill in a detail yourself",
        "never claim to be a person",
        'don\'t start replies with "thank you"',
        "never repeat a date of birth",
        "ask only for what is still missing",
        "is this your first visit with sunrise family clinic?",
        "never invent or",
        "verification is only for the caller",
        "call 911",
    ):
        assert rule in prompt, rule


def test_fixed_phrases_are_the_brief_wording() -> None:
    assert "may be recorded for quality purposes" in phrases.OPENING
    assert phrases.VERIFICATION_FAILED == "I'm sorry, I couldn't verify those details."
    assert phrases.ARRIVAL_INSTRUCTIONS == (
        "Please arrive 15 minutes early and bring a photo ID and your insurance card. "
        "You'll receive a confirmation by email."
    )
    assert phrases.after_hours_closing("Mark").startswith(
        "Thank you, Mark. Your message has been recorded, and our team will get back to you "
        "on the next business day."
    )


def test_only_the_deliberate_lines_are_scripted() -> None:
    scripted = [name for name in dir(phrases) if re.fullmatch(r"[A-Z_]+", name)]

    assert sorted(scripted) == [
        "ARRIVAL_INSTRUCTIONS",
        "CLOSED_GREETING",
        "EMERGENCY",
        "OPENING",
        "OPEN_GREETING",
        "STAFF_HANDOFF",
        "VERIFICATION_FAILED",
    ]
