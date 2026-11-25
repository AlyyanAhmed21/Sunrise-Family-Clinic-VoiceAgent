"""Function tools, grouped by who may use them (least privilege per call state)."""

from __future__ import annotations

from livekit.agents.beta.tools import EndCallTool
from livekit.agents.llm import Tool, Toolset

from agent.tools.booking import BOOKING_TOOLS
from agent.tools.patient import PATIENT_TOOLS
from agent.tools.staff import record_callback_message, request_callback, transfer_to_staff

__all__ = ["after_hours_tools", "open_hours_tools"]


def _end_call() -> EndCallTool:
    return EndCallTool(
        delete_room=False,
        end_instructions="Say a brief, friendly goodbye.",
        ignore_on_enter=True,
    )


def open_hours_tools() -> list[Tool | Toolset]:
    """Tools for open-hours callers.

    Patient tools are listed from the start: the model can't see tools added mid-response,
    so unlocking them on verification made it reach for the wrong tool. Access control does
    not depend on the list anyway: the service refuses patient data until the server-side
    session is verified, and no tool takes a patient identifier.
    """
    return [*PATIENT_TOOLS, *BOOKING_TOOLS, request_callback, transfer_to_staff, _end_call()]


def after_hours_tools() -> list[Tool | Toolset]:
    return [record_callback_message, _end_call()]
