"""Tool behaviour: the LLM drives the conversation, but code decides what is allowed."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from agent_helpers import MakeState, run_context
from livekit.agents.llm import utils

from agent.agents.receptionist import ReceptionistAgent
from agent.agents.scripted import ScriptedAgent, StaffHandoffAgent
from agent.capture import sanitize_turn
from agent.phrases import ARRIVAL_INSTRUCTIONS, VERIFICATION_FAILED
from agent.state import CallState
from agent.tools import after_hours_tools, open_hours_tools
from agent.tools.booking import book_appointment, find_open_slots
from agent.tools.patient import PATIENT_TOOLS, get_balance, list_my_medications, request_refill
from agent.tools.staff import record_callback_message, transfer_to_staff
from clinic.models import CallMode
from clinic.persistence.db import Database


def call(tool: Any, state: CallState, *args: Any, **kwargs: Any) -> Any:
    return asyncio.run(tool(run_context(state), *args, **kwargs))


def status(output: str) -> dict[str, Any]:
    return dict(json.loads(output))


def caller_says(state: CallState, text: str, *, agent_asked: str = "") -> None:
    """What `ClinicAgent.on_user_turn_completed` does with each caller turn."""
    from agent.capture import is_affirmative

    sanitize_turn(text, state, last_agent_text=agent_asked)
    state.caller_confirmed = is_affirmative(text)


def give_identity(state: CallState, dob: str = "March 14 1985", ssn: str = "3344") -> None:
    caller_says(state, f"my date of birth is {dob} and my last four is {ssn}")


def count(database: Database, sql: str) -> int:
    with database.connect() as connection:
        return int(connection.execute(sql).fetchone()[0])


# --- verification -----------------------------------------------------------------------


def test_verify_identity_needs_captured_details_and_counts_no_attempt(
    make_state: MakeState, database: Database
) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)

    out = status(asyncio.run(agent.verify_identity(run_context(state), "Sarah Johnson")))

    assert out["status"] == "missing_details"
    assert out["missing"] == ["date of birth", "last four SSN digits"]
    assert count(database, "SELECT failed_attempts FROM call_sessions") == 0


def test_patient_data_is_refused_until_the_backend_verifies_the_caller(
    make_state: MakeState,
) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)
    assert status(call(get_balance, state))["status"] == "not_verified"

    give_identity(state)
    out = status(asyncio.run(agent.verify_identity(run_context(state), "sarah johnson")))

    assert out["status"] == "verified"
    assert state.verified and state.dob.is_empty and state.last_four is None
    assert status(call(get_balance, state)) == {"status": "found", "balance_due": "$45.00"}


@pytest.mark.parametrize(
    "name", ["unknown", "Hi. I would like to get my prescription refilled.", "Sarah 3344"]
)
def test_verify_identity_rejects_things_that_are_not_names(
    make_state: MakeState, name: str
) -> None:
    state = make_state()
    give_identity(state)

    out = status(asyncio.run(ReceptionistAgent(state).verify_identity(run_context(state), name)))

    assert out["status"] == "missing_details" and out["missing"] == ["full name"]
    assert state.captured_dob() is not None  # nothing consumed, no attempt counted


def test_wrong_dob_and_wrong_ssn_get_identical_generic_failures(make_state: MakeState) -> None:
    outputs = []
    for call_id, dob, ssn in (("a", "March 15 1985", "3344"), ("b", "March 14 1985", "3345")):
        state = make_state(call_id)
        agent = ReceptionistAgent(state)
        give_identity(state, dob, ssn)
        outputs.append(asyncio.run(agent.verify_identity(run_context(state), "Sarah Johnson")))
        assert not state.verified

    assert outputs[0] == outputs[1]  # nothing reveals which detail was wrong
    assert status(outputs[0])["status"] == "not_verified"
    assert status(outputs[0])["say"] == VERIFICATION_FAILED


def test_third_failure_locks_verification(make_state: MakeState) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)
    outcomes = []
    for _ in range(4):
        give_identity(state, "January 1 1980", "0000")
        outcomes.append(
            status(asyncio.run(agent.verify_identity(run_context(state), "Sarah Johnson")))
        )

    assert [o["status"] for o in outcomes] == ["not_verified", "not_verified", "locked", "locked"]
    give_identity(state)  # even correct details are refused once locked
    final = status(asyncio.run(agent.verify_identity(run_context(state), "Sarah Johnson")))
    assert final["status"] == "locked" and not state.verified


def test_patient_tools_refuse_unverified_callers(make_state: MakeState) -> None:
    state = make_state()

    assert status(call(get_balance, state))["status"] == "not_verified"


def test_patient_tools_refuse_after_hours_even_if_verified(make_state: MakeState) -> None:
    state = make_state(mode=CallMode.CLOSED, verified_patient="P001")

    assert status(call(get_balance, state))["status"] == "unavailable"


def test_no_tool_accepts_identity_or_record_arguments() -> None:
    all_tools = [*PATIENT_TOOLS, *open_hours_tools(), *after_hours_tools()]
    for tool in all_tools:
        if not hasattr(tool, "info"):
            continue  # the EndCallTool toolset takes no arguments
        properties = utils.build_legacy_openai_schema(tool)["function"]["parameters"]
        names = set(properties.get("properties", {}))
        assert not names & {"patient_id", "dob", "date_of_birth", "ssn", "last_four"}, tool.id


# --- refills ----------------------------------------------------------------------------


def test_refill_is_saved_only_after_the_caller_says_yes(
    make_state: MakeState, database: Database
) -> None:
    state = make_state(verified_patient="P001")

    preview = status(call(request_refill, state, "lisinopril"))
    assert preview["status"] == "read_back"
    assert (preview["medication"], preview["pharmacy"]) == ("Lisinopril 10mg", "CVS Main St")

    # The model claims confirmation, but the caller never said yes.
    assert status(call(request_refill, state, "lisinopril", True))["status"] == "read_back"
    assert count(database, "SELECT COUNT(*) FROM patient_requests") == 0

    caller_says(state, "yes, that's right")
    done = status(call(request_refill, state, "lisinopril", True))
    assert done["status"] == "recorded"
    assert "approved" in done["hint"].lower() and "never" in done["hint"].lower()
    assert count(database, "SELECT COUNT(*) FROM patient_requests") == 1


def test_refill_with_no_refills_left_goes_to_the_doctor(make_state: MakeState) -> None:
    state = make_state(verified_patient="P001")
    call(request_refill, state, "metformin")
    caller_says(state, "yes")

    done = status(call(request_refill, state, "metformin", True))

    assert done["status"] == "needs_doctor_approval"
    assert "doctor for approval" in done["hint"]


def test_unmatched_medication_does_not_read_out_the_list(make_state: MakeState) -> None:
    state = make_state(verified_patient="P001")

    out = status(call(request_refill, state, "the blood pressure one"))

    assert out["status"] == "which_medication"
    assert "Lisinopril" not in json.dumps(out) and "Metformin" not in json.dumps(out)
    names = status(call(list_my_medications, state))["medication_names"]
    assert names == ["Lisinopril 10mg", "Metformin 500mg"]


@pytest.mark.parametrize("said", ["l I s I n o p r I l 10 mg", "lisinoprill", "my lisinopril"])
def test_spelled_or_misheard_medication_still_matches(make_state: MakeState, said: str) -> None:
    """Regression from a live call: the caller spelled the name letter by letter."""
    state = make_state(verified_patient="P001")

    out = status(call(request_refill, state, said))

    assert (out["status"], out["medication"]) == ("read_back", "Lisinopril 10mg")


# --- booking ----------------------------------------------------------------------------


def test_find_open_slots_filters_by_preference_and_never_invents(make_state: MakeState) -> None:
    # Filtering must use Eastern Time regardless of the host machine's timezone.
    state = make_state()

    lee = status(call(find_open_slots, state, doctor="Dr. Lee", part_of_day="afternoon"))
    friday = status(call(find_open_slots, state, weekday="Friday"))
    none = status(call(find_open_slots, state, on_date="2026-12-25"))

    assert [o["when"] for o in lee["options"]] == ["Wednesday, December 2 at 1:30 PM"]
    assert {o["doctor"] for o in friday["options"]} == {"Dr. Patel"}
    assert all("Friday, December 4" in o["when"] for o in friday["options"])
    assert none["status"] == "no_exact_match"
    assert none["requested_date"] == "Friday, December 25"
    assert len(none["options"]) == 3  # real alternatives, not invented ones


def test_no_match_alternatives_keep_the_preferred_doctor(make_state: MakeState) -> None:
    state = make_state()

    out = status(call(find_open_slots, state, doctor="Dr. Lee", on_date="2026-11-25"))

    assert out["status"] == "no_exact_match"
    assert {o["doctor"] for o in out["options"]} == {"Dr. Lee"}


def test_booking_refuses_a_slot_that_was_never_offered(make_state: MakeState) -> None:
    state = make_state()

    out = status(call(book_appointment, state, "made-up-slot", "check-up"))

    assert out["status"] == "unknown_slot"


def test_new_patient_booking_full_flow(make_state: MakeState, database: Database) -> None:
    state = make_state()
    slot = status(call(find_open_slots, state, doctor="Dr. Lee"))["options"][0]
    details = {
        "full_name": "Ann Lee",
        "phone": "555-010-2020",
        "email": "ann dot lee at the rate example dot com",  # spoken form, as heard on calls
        "insurance_provider": "Aetna",
        "member_id": "A 1 2 3 4",
    }

    missing = status(call(book_appointment, state, slot["slot_id"], "check-up", **details))
    assert missing == {
        "status": "missing_details",
        "missing": ["date of birth"],
        "hint": "Ask for these. For the date of birth, use the words 'date of birth'.",
    }

    caller_says(state, "July 4th 1990", agent_asked="And your date of birth?")
    read_back = status(call(book_appointment, state, slot["slot_id"], "check-up", **details))
    assert read_back["status"] == "read_back"
    assert (
        read_back["summary"]
        == "Ann Lee, Wednesday, December 2 at 10 AM with Dr. Lee, for check-up."
    )
    assert read_back["email_spelled"].startswith("a, n, n, dot, l, e, e, at")
    assert "1990" not in json.dumps(read_back)

    caller_says(state, "Yes, that's all correct")
    booked = status(
        call(book_appointment, state, slot["slot_id"], "check-up", confirmed=True, **details)
    )
    assert booked["status"] == "booked"
    with database.connect() as connection:
        summary = connection.execute("SELECT masked_summary FROM patient_requests").fetchone()[0]
    assert summary == "New patient booking: Check-up"  # not mislabelled "Annual check-up"
    assert booked["say"] == (
        f"You're all set for Wednesday, December 2 at 10 AM with Dr. Lee. {ARRIVAL_INSTRUCTIONS}"
    )
    assert count(database, "SELECT COUNT(*) FROM patient_requests") == 1
    remaining = status(call(find_open_slots, state, doctor="Dr. Lee"))["options"]
    assert slot["slot_id"] not in {o["slot_id"] for o in remaining}


def _book_daniel(state: CallState, slot_id: str, **coverage: Any) -> dict[str, Any]:
    return status(
        call(
            book_appointment,
            state,
            slot_id,
            "general consultation",
            full_name="Daniel Carter",
            phone="555 010 2468",
            email="Daniel.Carter@gmail.com",
            **coverage,
        )
    )


@pytest.mark.parametrize(
    "member_id_as_heard",
    ["4 8 2 9 1", "48 $2.91", "It's 48. $2.91.", "48291", "four eight two nine one"],
)
def test_voice_test_bcbs_48291_is_accepted_and_read_back(
    make_state: MakeState, database: Database, member_id_as_heard: str
) -> None:
    """Regression from a live call: Blue Cross Blue Shield / 48291 was rejected three times."""
    state = make_state()
    caller_says(state, "06/12/1994", agent_asked="What's your date of birth?")
    slot_id = status(call(find_open_slots, state))["options"][1]["slot_id"]  # 11 AM

    read_back = _book_daniel(
        state,
        slot_id,
        insurance_provider="Blue Cross Blue Shield insurance",
        member_id=member_id_as_heard,
    )
    assert read_back["status"] == "read_back"
    assert read_back["insurance"] == "Blue Cross Blue Shield, member ID 4, 8, 2, 9, 1"

    caller_says(state, "Yeah, that's right.")
    booked = _book_daniel(
        state,
        slot_id,
        insurance_provider="Blue Cross Blue Shield insurance",
        member_id=member_id_as_heard,
        confirmed=True,
    )
    assert booked["status"] == "booked"
    with database.connect() as connection:
        stored = connection.execute("SELECT insurance FROM patients WHERE patient_id LIKE 'NEW-%'")
        assert stored.fetchone()[0] == "Blue Cross Blue Shield, member ID 48291"


@pytest.mark.parametrize(
    ("coverage", "missing_text"),
    [
        ({"insurance_provider": "Blue Cross Blue Shield"}, "insurance member ID"),
        ({"insurance_provider": "Blue Cross Blue Shield", "member_id": "48"}, "clear insurance"),
        ({"insurance_provider": "Blue Cross Blue Shield", "member_id": "Test"}, "clear insurance"),
        ({"member_id": "48291"}, "insurance provider name"),
        ({"insurance_provider": "insurance", "member_id": "48291"}, "insurance provider name"),
        ({}, "insurance provider name"),
    ],
)
def test_incomplete_or_unclear_insurance_is_never_accepted(
    make_state: MakeState, coverage: dict[str, Any], missing_text: str
) -> None:
    state = make_state()
    caller_says(state, "06/12/1994", agent_asked="What's your date of birth?")
    slot_id = status(call(find_open_slots, state))["options"][0]["slot_id"]

    out = _book_daniel(state, slot_id, **coverage)

    assert out["status"] == "missing_details"
    assert any(missing_text in item for item in out["missing"])


def test_explicit_self_pay_needs_no_insurance(make_state: MakeState) -> None:
    state = make_state()
    caller_says(state, "06/12/1994", agent_asked="What's your date of birth?")
    slot_id = status(call(find_open_slots, state))["options"][0]["slot_id"]

    out = _book_daniel(state, slot_id, self_pay=True)

    assert (out["status"], out["insurance"]) == ("read_back", "self-pay")


def test_changed_details_after_read_back_need_a_new_confirmation(make_state: MakeState) -> None:
    state = make_state(verified_patient="P001")
    slot = status(call(find_open_slots, state))["options"][0]
    call(book_appointment, state, slot["slot_id"], "follow-up", email="sj@example.com")
    caller_says(state, "yes")

    out = status(
        call(book_appointment, state, slot["slot_id"], "follow-up", True, email="other@example.com")
    )

    assert out["status"] == "read_back"


def test_reason_for_visit_must_be_brief(make_state: MakeState) -> None:
    state = make_state(verified_patient="P001")
    slot = status(call(find_open_slots, state))["options"][0]
    reason = "I have had a bad headache and dizziness for three weeks after a fall"

    out = status(call(book_appointment, state, slot["slot_id"], reason, email="a@b.com"))

    assert out["status"] == "reason_too_long"


# --- staff and after hours --------------------------------------------------------------


def test_transfer_to_staff_records_request_and_hands_off(
    make_state: MakeState, database: Database
) -> None:
    state = make_state()

    assert isinstance(call(transfer_to_staff, state), StaffHandoffAgent)
    assert (
        count(database, "SELECT COUNT(*) FROM patient_requests WHERE request_type='transfer'") == 1
    )


def test_after_hours_message_is_read_back_then_saved_with_scripted_close(
    make_state: MakeState, database: Database
) -> None:
    state = make_state(mode=CallMode.CLOSED)
    args = ("Mark Davis", "five five five two oh one nine nine nine nine", "reschedule appointment")

    preview = status(call(record_callback_message, state, *args))
    assert (
        preview["summary"]
        == "Mark Davis, callback number 555-201-9999, about reschedule appointment."
    )

    caller_says(state, "yep")
    closing = call(record_callback_message, state, *args, confirmed=True)

    assert isinstance(closing, ScriptedAgent)
    assert closing._line.startswith("Thank you, Mark. Your message has been recorded")
    with database.connect() as connection:
        row = connection.execute(
            "SELECT patient_id, masked_summary FROM patient_requests"
        ).fetchone()
    assert tuple(row) == (None, "Scheduling callback requested")
