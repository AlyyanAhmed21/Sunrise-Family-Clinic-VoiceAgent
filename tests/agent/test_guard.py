"""The deterministic gate in front of the LLM, and the scripted agents."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import pytest
from agent_helpers import FakeSession, MakeState
from livekit.agents import Agent, StopResponse
from livekit.agents.llm import ChatContext, ChatMessage

from agent.agents.after_hours import AfterHoursAgent
from agent.agents.receptionist import ReceptionistAgent
from agent.agents.scripted import EmergencyAgent, ScriptedAgent
from agent.guard import LLM_FALLBACK_REPLY, ClinicAgent
from agent.phrases import CLOSED_GREETING, EMERGENCY, OPENING
from clinic.models import CallMode
from clinic.persistence.db import Database


@pytest.fixture
def fake_session(monkeypatch: pytest.MonkeyPatch) -> FakeSession:
    session = FakeSession()
    monkeypatch.setattr(Agent, "session", property(lambda self: session))
    return session


def turn(agent: ClinicAgent, text: str, *, agent_asked: str = "") -> ChatMessage:
    history = ChatContext()
    if agent_asked:
        history.add_message(role="assistant", content=agent_asked)
    message = ChatMessage(role="user", content=[text])
    asyncio.run(agent.on_user_turn_completed(history, message))
    return message


@pytest.mark.parametrize(
    "text",
    [
        "I have chest pain",
        "my date of birth is March 14 1985 and I can't breathe",
        "I want to kill myself",
    ],
)
def test_emergency_takes_precedence_over_everything(
    make_state: MakeState, fake_session: FakeSession, database: Database, text: str
) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)

    with pytest.raises(StopResponse):
        turn(agent, text, agent_asked="What's your date of birth?")

    assert isinstance(fake_session.next_agent, EmergencyAgent)
    assert state.dob.is_empty  # nothing else was processed
    with database.connect() as connection:
        actions = [row[0] for row in connection.execute("SELECT action FROM audit_events")]
    assert actions == ["emergency_redirected"]


def test_emergency_also_wins_after_hours(make_state: MakeState, fake_session: FakeSession) -> None:
    agent = AfterHoursAgent(make_state(mode=CallMode.CLOSED))

    with pytest.raises(StopResponse):
        turn(agent, "my husband is unconscious")

    assert isinstance(fake_session.next_agent, EmergencyAgent)


def test_history_keeps_only_the_redacted_text(
    make_state: MakeState, fake_session: FakeSession
) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)

    message = turn(agent, "It's March 14th 1985", agent_asked="And your date of birth?")

    assert state.captured_dob() == date(1985, 3, 14)
    stored = message.text_content or ""
    assert "1985" not in stored and "14" not in stored
    assert "date of birth received" in stored


def test_caller_yes_is_recorded_for_confirmation_gated_tools(
    make_state: MakeState, fake_session: FakeSession
) -> None:
    state = make_state()
    agent = ReceptionistAgent(state)

    turn(agent, "Yes, that's right")
    assert state.caller_confirmed
    turn(agent, "No, the email is wrong")
    assert not state.caller_confirmed


def test_greetings_are_said_once_on_enter(make_state: MakeState, fake_session: FakeSession) -> None:
    asyncio.run(ReceptionistAgent(make_state("open")).on_enter())
    asyncio.run(AfterHoursAgent(make_state("closed", mode=CallMode.CLOSED)).on_enter())

    assert fake_session.spoken[0].startswith(OPENING)
    assert fake_session.spoken[1] == f"{OPENING} {CLOSED_GREETING}"
    assert "911" in CLOSED_GREETING


def test_llm_first_token_timeout_speaks_a_fallback(
    make_state: MakeState, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def silent_llm(*_: Any) -> AsyncIterator[str]:
        await asyncio.sleep(1)
        yield "too late"

    monkeypatch.setattr(Agent.default, "llm_node", silent_llm)
    agent = ReceptionistAgent(make_state())
    agent.first_token_timeout_seconds = 0.01

    async def collect() -> list[Any]:
        return [chunk async for chunk in agent.llm_node(ChatContext(), [], None)]

    assert "".join(asyncio.run(collect())) == LLM_FALLBACK_REPLY


def test_scripted_agents_never_call_the_llm() -> None:
    async def collect() -> list[Any]:
        return [chunk async for chunk in EmergencyAgent().llm_node()]

    assert asyncio.run(collect()) == []
    assert EmergencyAgent()._line == EMERGENCY
    assert isinstance(EmergencyAgent(), ScriptedAgent)
