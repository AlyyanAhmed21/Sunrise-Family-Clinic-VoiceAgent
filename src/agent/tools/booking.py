"""Appointment booking for new patients and verified existing patients.

The model turns "next Tuesday morning with Dr. Lee" into structured preferences; the
application decides what is actually available and books atomically. A slot can only be
booked if `find_open_slots` offered it in this call, so availability can't be invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import Tool

from agent.metrics import timed_service_call
from agent.phrases import ARRIVAL_INSTRUCTIONS
from agent.spoken import clinic_time, spell_email, spoken_date, spoken_datetime
from agent.state import CallState
from agent.tools.common import confirmed_by_caller, failure, result, short_reason
from clinic.domain.errors import DomainError
from clinic.models import AvailableSlot
from clinic.security.parsing import normalize_member_id, normalize_spoken_email, parse_phone

Doctor = Literal["Dr. Patel", "Dr. Lee"]
Weekday = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PartOfDay = Literal["morning", "afternoon"]


@function_tool
async def find_open_slots(
    context: RunContext[CallState],
    doctor: Doctor | None = None,
    on_date: str | None = None,
    weekday: Weekday | None = None,
    part_of_day: PartOfDay | None = None,
) -> str:
    """Find open times to book a NEW appointment. This never returns the caller's existing
    appointment (use get_next_appointment for that). Leave out preferences not given.

    Args:
        doctor: Preferred doctor, if any.
        on_date: Only if the caller named a calendar date ("December 2nd"), as YYYY-MM-DD.
        weekday: A preferred day of the week ("Wednesdays", "next Tuesday").
        part_of_day: Morning (before noon) or afternoon.
    """
    state = context.userdata
    try:
        wanted = date.fromisoformat(on_date) if on_date else None
    except ValueError:
        return result("invalid_date", hint="Ask the caller which date they mean.")
    try:
        slots = await timed_service_call(
            state.call_id, state.service.list_available_slots, state.call_id
        )
    except DomainError as error:
        return failure(error)

    matches = [s for s in slots if _matches(s, doctor, wanted, weekday, part_of_day)]
    # No exact match: relax the day first, then the doctor, so alternatives stay relevant.
    nearest = [s for s in slots if _matches(s, doctor, None, None, part_of_day)] or [
        s for s in slots if _matches(s, doctor, None, None, None)
    ]
    offered = (matches or nearest or slots)[:3]
    state.offered_slots.update({slot.slot_id: slot for slot in offered})
    return result(
        "options" if matches else "no_exact_match",
        requested_date=spoken_date(wanted) if wanted else None,
        options=[
            {"slot_id": s.slot_id, "when": spoken_datetime(s.start_at), "doctor": s.doctor_name}
            for s in offered
        ],
        hint=None if matches else "Nothing matches; say so and offer these instead.",
    )


def _matches(
    slot: AvailableSlot,
    doctor: Doctor | None,
    wanted: date | None,
    weekday: Weekday | None,
    part_of_day: PartOfDay | None,
) -> bool:
    local = clinic_time(slot.start_at)
    return (
        (doctor is None or slot.doctor_name == doctor)
        and (wanted is None or local.date() == wanted)
        and (weekday is None or f"{local:%A}" == weekday)
        and (part_of_day is None or (local.hour < 12) == (part_of_day == "morning"))
    )


@function_tool
async def book_appointment(
    context: RunContext[CallState],
    slot_id: str,
    reason: str,
    confirmed: bool = False,
    full_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    insurance_provider: str | None = None,
    member_id: str | None = None,
    self_pay: bool = False,
) -> str:
    """Book an offered slot. Call without `confirmed` to get the read-back summary, read it to
    the caller, and call again with the same details and `confirmed` true once they say yes.

    A verified existing patient needs only the slot, reason and (if asked) email. A new patient
    also needs full name, phone, email, and either insurance (provider and member ID) or
    self_pay; the date of birth is taken from the call.

    Args:
        slot_id: A slot_id returned by find_open_slots.
        reason: Reason for the visit in a few words, e.g. "annual check-up".
        confirmed: True only after the caller confirmed the read-back.
        full_name: New patient's full name.
        phone: New patient's phone number.
        email: Email address as the caller said it; spoken forms like "jo dot lee at gmail
            dot com" are accepted and normalized by the system.
        insurance_provider: Insurance company name only, e.g. "Blue Cross Blue Shield".
        member_id: Member ID exactly as the caller said it, all pieces combined, e.g.
            "4 8 2 9 1" or "48 291"; the system normalizes it.
        self_pay: True only if the caller explicitly said they will self-pay.
    """
    state = context.userdata
    slot = state.offered_slots.get(slot_id)
    if slot is None:
        return result("unknown_slot", hint="Use find_open_slots and offer only returned times.")
    visit_reason = short_reason(reason)
    if visit_reason is None:
        return result("reason_too_long", hint="Ask for the reason in just a few words.")
    try:
        if state.verified:
            on_file_name, on_file_email = await timed_service_call(
                state.call_id, state.service.get_verified_patient_booking_details, state.call_id
            )
            full_name, email = on_file_name, email or on_file_email
    except DomainError as error:
        return failure(error)

    email = normalize_spoken_email(email) if email else None
    coverage = None if state.verified else _coverage(insurance_provider, member_id, self_pay)
    problems = _missing_details(state, full_name, phone, email)
    if coverage is not None and coverage.problem:
        problems.append(coverage.problem)
    if problems or full_name is None or email is None:
        return result("missing_details", missing=problems, hint=_MISSING_HINT)

    when = spoken_datetime(slot.start_at)
    stored = coverage.stored if coverage else None
    action = f"booking:{slot_id}|{full_name}|{visit_reason}|{email}|{phone}|{stored}"
    if not confirmed_by_caller(state, action, confirmed):
        return result(
            "read_back",
            summary=f"{full_name}, {when} with {slot.doctor_name}, for {visit_reason}.",
            insurance=coverage.spoken if coverage else None,
            email_spelled=spell_email(email),
            hint="Read this back (including insurance and the member ID digit by digit), "
            "spell the email, and ask if everything is correct.",
        )
    return await _book(state, slot, visit_reason, full_name, phone, email, stored)


_MISSING_HINT = "Ask for these. For the date of birth, use the words 'date of birth'."


@dataclass(frozen=True, slots=True)
class Coverage:
    """How a new patient pays: what is stored, what is read back, or what is still missing."""

    stored: str | None = None
    spoken: str | None = None
    problem: str | None = None


def _coverage(provider: str | None, member_id: str | None, self_pay: bool) -> Coverage:
    if self_pay:
        return Coverage(stored="Self-pay", spoken="self-pay")
    name = re.sub(r"\binsurance\b", "", provider or "", flags=re.I).strip(" ,.")
    if len(re.sub(r"[^a-z]", "", name, flags=re.I)) < 2:
        return Coverage(problem="insurance provider name (or self-pay if the caller chooses it)")
    if not member_id:
        return Coverage(problem="insurance member ID")
    normalized = normalize_member_id(member_id)
    if normalized is None:
        return Coverage(
            problem="a clear insurance member ID: what was heard was too short or unclear; ask "
            "the caller to read it slowly, character by character"
        )
    return Coverage(
        stored=f"{name}, member ID {normalized}",
        spoken=f"{name}, member ID {', '.join(normalized)}",
    )


def _missing_details(
    state: CallState, full_name: str | None, phone: str | None, email: str | None
) -> list[str]:
    missing: list[str] = []
    if email is None:
        missing.append("email address (ask them to say it again, e.g. 'name dot surname at…')")
    if state.verified:
        return missing
    if full_name is None or len(full_name.split()) < 2:
        missing.append("full name")
    if state.captured_dob() is None:
        missing.append("date of birth")
    if phone is None or parse_phone(phone) is None:
        missing.append("10-digit phone number")
    return missing


async def _book(
    state: CallState,
    slot: AvailableSlot,
    reason: str,
    full_name: str,
    phone: str | None,
    email: str,
    insurance: str | None,
) -> str:
    service = state.service
    try:
        if state.verified:
            booked = await timed_service_call(
                state.call_id,
                service.book_existing_patient,
                state.call_id,
                reason=reason,
                slot_id=slot.slot_id,
                email=email,
            )
        else:
            dob = state.captured_dob()
            phone_digits = parse_phone(phone or "")
            if dob is None or phone_digits is None or insurance is None:  # validated earlier
                return result("missing_details", hint=_MISSING_HINT)
            booked = await timed_service_call(
                state.call_id,
                service.book_new_patient,
                state.call_id,
                full_name=full_name,
                dob=dob,
                phone=phone_digits,
                email=email,
                insurance=insurance,
                reason=reason,
                slot_id=slot.slot_id,
            )
    except DomainError as error:
        return failure(error)
    state.offered_slots.clear()
    state.clear_identity()
    when = spoken_datetime(booked.appointment.start_at)
    return result(
        "booked",
        say=f"You're all set for {when} with {booked.appointment.doctor_name}. "
        f"{ARRIVAL_INSTRUCTIONS}",
        hint="Say this, then ask if there's anything else.",
    )


BOOKING_TOOLS: list[Tool] = [find_open_slots, book_appointment]
