"""Agents that only say one fixed line and end the call (emergency, staff handoff)."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any

from livekit.agents import Agent, StopResponse
from livekit.agents.llm import ChatContext, ChatMessage

from agent.phrases import EMERGENCY, STAFF_HANDOFF


class ScriptedAgent(Agent):
    """Speaks `line` without interruption, then ends the call. Never invokes the LLM."""

    def __init__(self, line: str) -> None:
        super().__init__(instructions="Say the scripted line only.")
        self._line = line

    async def on_enter(self) -> None:
        speech = self.session.say(self._line, allow_interruptions=False)
        await speech.wait_for_playout()
        self.session.shutdown(drain=True)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        raise StopResponse()

    async def llm_node(self, *args: Any, **kwargs: Any) -> AsyncIterable[str]:
        return
        yield  # pragma: no cover - makes this an (empty) async generator


class EmergencyAgent(ScriptedAgent):
    def __init__(self) -> None:
        super().__init__(EMERGENCY)


class StaffHandoffAgent(ScriptedAgent):
    def __init__(self) -> None:
        super().__init__(STAFF_HANDOFF)
