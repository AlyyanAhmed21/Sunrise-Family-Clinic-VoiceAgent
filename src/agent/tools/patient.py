"""Tools available only after the backend has verified the caller.

None of them takes a patient ID: the service resolves the patient from the server-side
call session, so the model cannot ask for anyone else's record.
"""

from __future__ import annotations

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import Tool

from agent.metrics import timed_service_call
from agent.spoken import spoken_datetime, spoken_money
from agent.state import CallState
from agent.tools.common import confirmed_by_caller, failure, result
from clinic.domain.errors import DomainError


@function_tool
async def get_next_appointment(context: RunContext[CallState]) -> str:
    """Look up the verified caller's next scheduled appointment."""
    state = context.userdata
    try:
        found = await timed_service_call(
            state.call_id, state.service.get_next_appointment, state.call_id
        )
    except DomainError as error:
        return failure(error)
    if found.appointment is None:
        return result("none", hint="Offer to book an appointment or a staff callback.")
    return result(
        "found",
        appointment=spoken_datetime(found.appointment.start_at),
        doctor=found.appointment.doctor_name,
    )


@function_tool
async def get_lab_status(context: RunContext[CallState]) -> str:
    """Get the status of the verified caller's lab results (status only, never results)."""
    state = context.userdata
    try:
        lab = await timed_service_call(state.call_id, state.service.get_lab_status, state.call_id)
    except DomainError as error:
        return failure(error)
    return result("found", lab_status=lab.status, hint="Give the status only; never interpret.")


@function_tool
async def get_balance(context: RunContext[CallState]) -> str:
    """Get the verified caller's billing balance due."""
    state = context.userdata
    try:
        balance = await timed_service_call(state.call_id, state.service.get_balance, state.call_id)
    except DomainError as error:
        return failure(error)
    return result("found", balance_due=spoken_money(balance.amount))


@function_tool
async def request_refill(
    context: RunContext[CallState], medication: str, confirmed: bool = False
) -> str:
    """Create a prescription refill request for one of the verified caller's medications.

    Call first without `confirmed` to get the medication and pharmacy to read back. Call again
    with `confirmed` true only after the caller clearly says yes to that read-back.

    Args:
        medication: The medication name the caller asked for, e.g. "metformin".
        confirmed: True only after the caller confirmed the read-back.
    """
    state = context.userdata
    try:
        preview = await timed_service_call(
            state.call_id, state.service.prepare_refill, state.call_id, medication
        )
    except DomainError as error:
        return failure(error)
    if preview.outcome in ("medication_not_found", "medication_ambiguous"):
        return result(
            "which_medication",
            hint="Didn't match one of their medications. Ask them to say or spell the name. "
            "Only if they can't remember it, use list_my_medications.",
        )
    if preview.confirmation_token is None or preview.medication_name is None:
        return result("error", hint="Offer a staff callback.")

    action = f"refill:{preview.medication_name}"
    if not confirmed_by_caller(state, action, confirmed):
        return result(
            "read_back",
            medication=preview.medication_name,
            pharmacy=preview.pharmacy,
            hint="Confirm the medication and pharmacy with the caller before submitting.",
        )
    try:
        done = await timed_service_call(
            state.call_id,
            state.service.confirm_refill,
            state.call_id,
            preview.confirmation_token,
        )
    except DomainError as error:
        return failure(error)
    hints = {
        "recorded": "Say the refill request was sent to the clinic. Never say it is approved.",
        "needs_doctor_approval": (
            "No refills are left: say the request will be sent to the doctor for approval."
        ),
        "duplicate_pending": "A request for this medication is already pending.",
    }
    return result(done.outcome, medication=done.medication_name, hint=hints.get(done.outcome))


@function_tool
async def list_my_medications(context: RunContext[CallState]) -> str:
    """Names of the verified caller's medications. Use ONLY when they want a refill but can't
    remember the medication name; never read the list out otherwise."""
    state = context.userdata
    try:
        names = await timed_service_call(
            state.call_id, state.service.list_medication_names, state.call_id
        )
    except DomainError as error:
        return failure(error)
    return result("found", medication_names=names, hint="Say the names only, nothing else.")


@function_tool
async def leave_message_for_doctor(context: RunContext[CallState], confirmed: bool = False) -> str:
    """Ask the caller's care team to follow up, e.g. for a medical question you can't answer.

    Call without `confirmed` first, ask the caller if they'd like that, then call again with
    `confirmed` true after they say yes. No health details are stored.

    Args:
        confirmed: True only after the caller said yes.
    """
    state = context.userdata
    if not confirmed_by_caller(state, "doctor_message", confirmed):
        return result("ask_caller", hint="Ask if they'd like their care team to follow up.")
    try:
        await timed_service_call(state.call_id, state.service.record_doctor_message, state.call_id)
    except DomainError as error:
        return failure(error)
    return result("recorded", hint="Tell them their care team will follow up.")


PATIENT_TOOLS: list[Tool] = [
    get_next_appointment,
    get_lab_status,
    get_balance,
    request_refill,
    list_my_medications,
    leave_message_for_doctor,
]
