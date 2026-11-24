"""LiveKit 1.8.x agent adapters for the Step 0 privacy spike.

Import this module only in the project's LiveKit environment. Unit tests for
redaction remain SDK-independent in step0/guard.py.
"""

from __future__ import annotations

from typing import Any

from livekit.agents import Agent, StopResponse

from step0.guard import redact_context_copy, redact_context_in_place


class GuardedAgent(Agent):
    """Agent whose inbound history and final model egress are redacted."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Per-agent setting is intentional: a future session default must not
        # silently re-enable preemptive generation for this agent.
        kwargs["turn_handling"] = {
            **kwargs.get("turn_handling", {}),
            "preemptive_generation": False,
        }
        super().__init__(*args, **kwargs)

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        # Defense in depth before normal history retention/handoff. The final
        # llm_node guard below remains necessary for preemptive/tool paths.
        redact_context_in_place(turn_ctx)
        redact_context_in_place(new_message)

    def llm_node(self, chat_ctx: Any, tools: list[Any], model_settings: Any) -> Any:
        """Redact a copy at the last boundary before the model is invoked."""
        safe_context = redact_context_copy(chat_ctx)
        return super().llm_node(safe_context, tools, model_settings)


class NoModelAgent(GuardedAgent):
    """Verification agent: its conversation must never invoke an LLM."""

    def llm_node(self, chat_ctx: Any, tools: list[Any], model_settings: Any) -> None:
        raise StopResponse()
