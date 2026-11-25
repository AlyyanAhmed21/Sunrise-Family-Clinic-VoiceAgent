"""Output-side guardrail: what the agent says is checked before it is spoken."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from livekit.agents.llm import ChatChunk, ChoiceDelta, FunctionToolCall

from agent.speech_guard import check_sentence, guard_stream


@pytest.mark.parametrize(
    ("sentence", "rule"),
    [
        ("Your SSN is 000-12-3344.", "full_ssn"),
        ("The last four of your social are 3, 3, 4, 4.", "ssn_digits"),
        ("You were born March 14th, 1985.", "date_of_birth"),
        ("Your date of birth is 3/14/1985.", "date_of_birth"),
        ("Your refill has been approved.", "refill_promise"),
        ("It will be ready for pickup tomorrow.", "refill_promise"),
        ("You can take 400 mg of it twice a day.", "dosing_advice"),
        ("Just double the dose for a few days.", "dosing_advice"),
        ("I'd recommend ibuprofen for that.", "dosing_advice"),
    ],
)
def test_violations_are_replaced(sentence: str, rule: str) -> None:
    spoken, blocked = check_sentence(sentence)

    assert blocked == rule
    assert spoken != sentence


@pytest.mark.parametrize(
    "sentence",
    [
        # Things the agent legitimately says, close to the blocked patterns.
        "And the last four digits of your Social Security number?",
        "And what year were you born?",
        "I have Daniel Carter, callback number 555-010-2468, about scheduling.",
        "A callback for Sam at 124, 578, 1212, about a headache question.",
        "The refill request will go to the doctor for approval.",
        "I can't say whether it's approved; the doctor will review it.",
        "I can't recommend a medication or a dose change.",
        "Please arrive 15 minutes early and bring a photo ID and your insurance card.",
        "You're all set for Tuesday, December 1 at 9:30 AM with Dr. Patel.",
        "Your balance due is 45 dollars.",
        "Blue Cross Blue Shield, member ID 4, 8, 2, 9, 1.",
        "Your next appointment is Thursday, December 3 at 10:30 AM with Dr. Patel.",
    ],
)
def test_normal_speech_passes_unchanged(sentence: str) -> None:
    assert check_sentence(sentence) == (sentence, None)


async def _stream(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


def _run(items: list[Any]) -> list[Any]:
    async def collect() -> list[Any]:
        return [chunk async for chunk in guard_stream(_stream(items), call_id="c")]

    return asyncio.run(collect())


def test_stream_releases_each_sentence_as_soon_as_it_ends() -> None:
    out = _run(["Sure. Your refill ", "has been approved", ". Anything else?"])

    assert out == [
        "Sure. ",
        "Your request has been sent to the clinic, and they'll follow up. ",
        "Anything else?",
    ]


def test_tool_calls_and_structured_chunks_pass_through_in_order() -> None:
    call = FunctionToolCall(call_id="1", name="get_balance", arguments="{}")
    tool_chunk = ChatChunk(id="x", delta=ChoiceDelta(tool_calls=[call]))
    text_chunk = ChatChunk(id="y", delta=ChoiceDelta(content="One moment."))

    out = _run([text_chunk, tool_chunk])

    assert out == ["One moment.", tool_chunk]
