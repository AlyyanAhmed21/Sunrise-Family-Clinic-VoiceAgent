"""After-hours agent: says the office is closed and takes a callback message. No PHI tools."""

from __future__ import annotations

from agent.guard import ClinicAgent
from agent.phrases import CLOSED_GREETING, OPENING
from agent.prompts import render_prompt
from agent.state import CallState
from agent.tools import after_hours_tools


class AfterHoursAgent(ClinicAgent):
    def __init__(self, state: CallState) -> None:
        super().__init__(
            instructions=render_prompt("after_hours", state.clock.now()),
            state=state,
            tools=after_hours_tools(),
        )

    async def on_enter(self) -> None:
        self.session.say(f"{OPENING} {CLOSED_GREETING}")
