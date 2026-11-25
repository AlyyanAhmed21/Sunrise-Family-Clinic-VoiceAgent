"""Human handoff and callback/message tools (open hours and after hours)."""

from __future__ import annotations

from livekit.agents import Agent, RunContext, function_tool

from agent.agents.scripted import ScriptedAgent, StaffHandoffAgent
from agent.metrics import timed_service_call
from agent.phrases import after_hours_closing
from agent.spoken import spoken_phone
from agent.state import CallState
from agent.tools.common import confirmed_by_caller, failure, result, short_reason
from clinic.domain.errors import DomainError
from clinic.security.parsing import parse_phone


@function_tool
async def transfer_to_staff(context: RunContext[CallState]) -> Agent | str:
    """Transfer the call to clinic staff: the caller asked for a person, is upset or confused,
    or verification is locked."""
    state = context.userdata
    try:
        await timed_service_call(
            state.call_id, state.service.request_staff_assistance, state.call_id
        )
    except DomainError as error:
        return failure(error)
    return StaffHandoffAgent()


@function_tool
async def request_callback(
    context: RunContext[CallState],
    reason: str,
    confirmed: bool = False,
    full_name: str | None = None,
    phone: str | None = None,
) -> str:
    """Ask clinic staff to call the caller back during office hours.

    Verified callers need only a short reason. Others also need their full name and phone.
    Call without `confirmed` to get the read-back, then again with `confirmed` true after
    the caller says yes.

    Args:
        reason: Reason for the callback in a few words, no health details.
        confirmed: True only after the caller confirmed the read-back.
        full_name: Caller's full name (unverified callers).
        phone: Callback phone number (unverified callers).
    """
    state = context.userdata
    brief = short_reason(reason)
    digits = parse_phone(phone or "")
    if brief is None:
        return result("reason_too_long", hint="Ask for the reason in a few words.")
    if not state.verified and (digits is None or not full_name or len(full_name.split()) < 2):
        return result("missing_details", missing=["full name", "10-digit phone number"])
    caller = (
        "you, at the number on file"
        if state.verified
        else f"{full_name}, {spoken_phone(digits or '')}"
    )
    if not confirmed_by_caller(state, f"callback:{brief}|{full_name}|{digits}", confirmed):
        return result("read_back", summary=f"A callback for {caller}, about {brief}.")
    try:
        await timed_service_call(
            state.call_id,
            state.service.request_callback,
            state.call_id,
            reason=brief,
            name=None if state.verified else full_name,
            phone=None if state.verified else digits,
        )
    except DomainError as error:
        return failure(error)
    return result("recorded", hint="Tell them staff will call back during office hours.")


@function_tool
async def record_callback_message(
    context: RunContext[CallState],
    full_name: str,
    callback_number: str,
    reason: str,
    confirmed: bool = False,
) -> Agent | str:
    """Record an after-hours message so the team calls back on the next business day.

    Call without `confirmed` to get the read-back, then again with the same details and
    `confirmed` true after the caller says yes.

    Args:
        full_name: Caller's full name.
        callback_number: Phone number to call back.
        reason: Reason for the call in a few words, no health details.
        confirmed: True only after the caller confirmed the read-back.
    """
    state = context.userdata
    digits = parse_phone(callback_number)
    brief = short_reason(reason)
    if len(full_name.split()) < 2 or digits is None or brief is None:
        return result(
            "missing_details",
            hint="Need a full name, a 10-digit callback number, and a reason in a few words.",
        )
    action = f"message:{full_name}|{digits}|{brief}"
    if not confirmed_by_caller(state, action, confirmed):
        return result(
            "read_back",
            summary=f"{full_name}, callback number {spoken_phone(digits)}, about {brief}.",
        )
    try:
        await timed_service_call(
            state.call_id,
            state.service.record_after_hours_callback,
            state.call_id,
            name=full_name,
            phone=digits,
            reason=brief,
        )
    except DomainError as error:
        return failure(error)
    return ScriptedAgent(after_hours_closing(full_name.split()[0]))
