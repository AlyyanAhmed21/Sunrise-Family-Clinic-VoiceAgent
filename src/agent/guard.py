"""Base class for the LLM-driven agents: the deterministic gate in front of the model."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from livekit.agents import Agent, APIError, StopResponse
from livekit.agents.llm import ChatContext, ChatMessage, Tool, Toolset

from agent.agents.scripted import EmergencyAgent
from agent.capture import is_affirmative, sanitize_turn
from agent.metrics import timed_service_call
from agent.speech_guard import guard_stream
from agent.state import CallState
from clinic.domain.errors import DomainError
from clinic.security.emergency import detect_emergency

logger = logging.getLogger("sunrise.agent")

EMERGENCY_MARKER = "[caller described an emergency]"
LLM_FALLBACK_REPLY = (
    "I'm having trouble on my end right now. You can call back shortly, "
    "or I can have a staff member call you."
)


class ClinicAgent(Agent):
    """Screens every caller message in code before the LLM can see it:

    1. Emergency language ends normal handling at once (scripted 911 direction).
    2. Date of birth / SSN digits are captured into `CallState` and cut from the text.
    3. Whether the caller just said "yes" is recorded for confirmation-gated tools.

    On the way out, the model's speech passes `speech_guard` sentence by sentence.

    `llm_node` is the single choke point: every model call screens the context it sends,
    so spoken turns and typed chat (which skips `on_user_turn_completed`) are both covered.
    Each message is screened once and cached by id.
    """

    first_token_timeout_seconds = 10.0

    def __init__(self, *, instructions: str, state: CallState, tools: list[Tool | Toolset]) -> None:
        super().__init__(instructions=instructions, tools=tools)
        self.state = state
        self._screened: dict[str, str] = {}

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        """Spoken turns: store only the screened text in the conversation history."""
        safe = await self._screen(new_message, _last_agent_text(turn_ctx.items))
        new_message.content = [safe if safe is not None else EMERGENCY_MARKER]
        if safe is None:
            raise StopResponse()

    async def llm_node(
        self, chat_ctx: ChatContext, tools: list[Tool], model_settings: Any
    ) -> AsyncIterable[Any]:
        safe_ctx = await self._screened_context(chat_ctx)
        if safe_ctx is None:
            return
        model_output = self._timed_model_stream(safe_ctx, tools, model_settings)
        async for chunk in guard_stream(model_output, call_id=self.state.call_id):
            yield chunk

    async def _timed_model_stream(
        self, safe_ctx: ChatContext, tools: list[Tool], model_settings: Any
    ) -> AsyncIterator[Any]:
        """The model's raw output, with a time-to-first-token bound and timing log."""
        started = time.perf_counter()
        first_chunk_at: float | None = None
        outcome = "success"
        try:
            async with asyncio.timeout(self.first_token_timeout_seconds) as deadline:
                async for chunk in Agent.default.llm_node(self, safe_ctx, tools, model_settings):
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter()
                        deadline.reschedule(None)  # bound time-to-first-token only
                    yield chunk
        except (TimeoutError, APIError) as error:
            outcome = type(error).__name__
            if first_chunk_at is None:
                yield LLM_FALLBACK_REPLY
        finally:
            logger.info(
                "event=llm_timing call_id=%s ttft_ms=%s total_ms=%.0f outcome=%s",
                self.state.call_id,
                f"{(first_chunk_at - started) * 1000:.0f}" if first_chunk_at else "none",
                (time.perf_counter() - started) * 1000,
                outcome,
            )

    async def _screened_context(self, chat_ctx: ChatContext) -> ChatContext | None:
        """A copy of the context with every caller message screened; None on emergency."""
        safe_ctx = chat_ctx.copy()
        items: list[Any] = []
        for item in safe_ctx.items:
            if isinstance(item, ChatMessage) and item.role == "user":
                safe = await self._screen(item, _last_agent_text(items))
                if safe is None:
                    return None
                item = item.model_copy(update={"content": [safe]})
            items.append(item)
        safe_ctx.items = items
        return safe_ctx

    async def _screen(self, message: ChatMessage, last_agent_text: str) -> str | None:
        if message.id in self._screened:
            return self._screened[message.id]
        text = message.text_content or ""
        if text == EMERGENCY_MARKER or detect_emergency(text):
            self._screened[message.id] = EMERGENCY_MARKER
            logger.info("event=emergency_detected call_id=%s", self.state.call_id)
            await self._audit_emergency()
            self.session.update_agent(EmergencyAgent())
            return None
        started = time.perf_counter()
        safe = sanitize_turn(text, self.state, last_agent_text=last_agent_text)
        self.state.caller_confirmed = is_affirmative(text)
        self._screened[message.id] = safe
        logger.info(
            "event=turn_screened call_id=%s duration_ms=%.2f",
            self.state.call_id,
            (time.perf_counter() - started) * 1000,
        )
        return safe

    async def _audit_emergency(self) -> None:
        """Record the 911 redirect (a few ms) before handing off; never block the warning."""
        try:
            await asyncio.wait_for(
                timed_service_call(
                    self.state.call_id, self.state.service.record_emergency, self.state.call_id
                ),
                timeout=1.0,
            )
        except (DomainError, TimeoutError):
            logger.warning("event=emergency_audit_failed call_id=%s", self.state.call_id)


def _last_agent_text(items: list[Any]) -> str:
    for item in reversed(items):
        if isinstance(item, ChatMessage) and item.role == "assistant":
            return item.text_content or ""
    return ""
