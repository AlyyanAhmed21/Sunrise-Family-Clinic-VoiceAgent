from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

from livekit.agents import RunContext

from agent.state import CallState

MakeState = Callable[..., CallState]


def run_context(state: CallState) -> RunContext[CallState]:
    """Tools only read `context.userdata`, so a namespace stands in for LiveKit's context."""
    return cast(RunContext[CallState], SimpleNamespace(userdata=state))


class FakeSpeech:
    async def wait_for_playout(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.next_agent: Any = None

    def say(self, text: str, **_: Any) -> FakeSpeech:
        self.spoken.append(text)
        return FakeSpeech()

    def update_agent(self, agent: Any) -> None:
        self.next_agent = agent
