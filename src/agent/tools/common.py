"""Helpers shared by every tool: compact JSON results, safe failures, confirmation gate."""

from __future__ import annotations

import json
import logging

from agent.state import CallState
from clinic.domain.errors import (
    ClinicClosed,
    DomainError,
    InvalidStateTransition,
    UnauthorizedPatientAccess,
    VerificationLocked,
)

logger = logging.getLogger("sunrise.agent.tools")


def result(status: str, **fields: object) -> str:
    """Tool output for the LLM: a status plus only the fields that are set."""
    return json.dumps({"status": status, **{k: v for k, v in fields.items() if v is not None}})


def failure(error: DomainError) -> str:
    """Map a domain error to a safe result. Domain messages never contain PHI."""
    logger.info("event=tool_refused error_category=%s", type(error).__name__)
    if isinstance(error, ClinicClosed):
        return result("unavailable", hint="Patient services are closed; offer to take a message.")
    if isinstance(error, VerificationLocked):
        return result("locked", hint="Verification is locked; offer a transfer to clinic staff.")
    if isinstance(error, UnauthorizedPatientAccess):
        return result("not_verified", hint="The caller must be verified first.")
    if isinstance(error, InvalidStateTransition):
        return result("not_done", reason=str(error))
    return result("error", hint="Something went wrong; offer a staff callback or transfer.")


def confirmed_by_caller(state: CallState, action: str, confirmed: bool) -> bool:
    """True only if the caller said yes right after hearing exactly this `action` read back.

    Otherwise the action becomes the pending read-back and the tool must not save anything.
    """
    if confirmed and state.take_confirmation(action):
        return True
    state.await_confirmation(action)
    return False


def short_reason(reason: str, max_words: int = 8) -> str | None:
    words = reason.split()
    return " ".join(words) if 0 < len(words) <= max_words else None
