"""The open-hours receptionist: one LLM-led conversation for every caller need."""

from __future__ import annotations

import logging
import re

from livekit.agents import RunContext, function_tool

from agent.guard import ClinicAgent
from agent.metrics import timed_service_call
from agent.phrases import OPEN_GREETING, OPENING, VERIFICATION_FAILED
from agent.prompts import render_prompt
from agent.state import CallState
from agent.tools import open_hours_tools
from agent.tools.common import failure, result
from clinic.domain.errors import DomainError
from clinic.models import VerificationCandidate

logger = logging.getLogger("sunrise.agent")
_FULL_NAME = re.compile(
    r"[^\W\d_]+(?:['.-][^\W\d_]+)*\.?(?:\s+[^\W\d_]+(?:['.-][^\W\d_]+)*\.?){1,3}"
)


def _looks_like_full_name(value: str) -> bool:
    """2-4 words of letters; rejects a whole sentence passed as a name."""
    return bool(_FULL_NAME.fullmatch(value.strip()))


class ReceptionistAgent(ClinicAgent):
    def __init__(self, state: CallState) -> None:
        super().__init__(
            instructions=render_prompt("receptionist", state.clock.now()),
            state=state,
            tools=open_hours_tools(),
        )

    async def on_enter(self) -> None:
        self.session.say(f"{OPENING} {OPEN_GREETING}")

    @function_tool
    async def verify_identity(self, context: RunContext[CallState], full_name: str) -> str:
        """Verify an existing patient. Call once you have their full name and the system notes
        say the date of birth and last four SSN digits were received. Matching is done by the
        clinic system; you never see or pass the date of birth or SSN digits.

        Args:
            full_name: The caller's full name as they said it.
        """
        state = context.userdata
        if state.verified:
            return result("verified")
        dob, last_four = state.captured_dob(), state.last_four
        missing = [
            label
            for label, value in (("date of birth", dob), ("last four SSN digits", last_four))
            if value is None
        ]
        if not _looks_like_full_name(full_name):
            missing.insert(0, "full name")
        if missing or dob is None or last_four is None:
            return result(
                "missing_details",
                missing=missing,
                hint="Nothing was checked and no attempt was used. Do NOT say verification "
                "failed; just ask for these details.",
            )

        candidate = VerificationCandidate(
            full_name=full_name.strip()[:200], dob=dob, last_four=last_four.get_secret_value()
        )
        state.clear_identity()  # every attempt starts from fresh details
        try:
            outcome = await timed_service_call(
                state.call_id, state.service.verify_caller, state.call_id, candidate
            )
        except DomainError as error:
            return failure(error)
        logger.info("event=verification call_id=%s outcome=%s", state.call_id, outcome.outcome)

        if outcome.outcome == "verified":
            state.verified = True
            return result(
                "verified",
                hint="Don't announce this. Now use the right tool for what they called about.",
            )
        if outcome.outcome == "locked_out":
            return result(
                "locked", say=VERIFICATION_FAILED, hint="Don't retry. Offer a transfer to staff."
            )
        return result(
            "not_verified",
            say=VERIFICATION_FAILED,
            attempts_left=3 - outcome.failed_attempts,
            hint="Never say which detail was wrong. Offer to try again with all three details.",
        )
