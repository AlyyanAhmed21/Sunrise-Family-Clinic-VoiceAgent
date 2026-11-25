"""Deterministic check on what the agent is about to say, sentence by sentence.

The prompt tells the model never to read back identity data, promise a refill or give
dosing advice; this enforces the clearest violations in code. A blocked sentence is
replaced with a safe line and logged (rule name only). Patterns cannot catch every phrasing
of medical advice, so this is a backstop for the prompt, not a replacement for it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

from livekit.agents.llm import ChatChunk

logger = logging.getLogger("sunrise.agent.speech_guard")

_NEGATION = re.compile(r"\b(?:can'?t|cannot|can not|not|never|unable|won'?t|don'?t)\b", re.I)
_MONTH = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|"
    r"december)"
)


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    replacement: str
    unless_negated: bool = False


RULES = (
    Rule(
        "full_ssn",
        re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"),
        "For your privacy, I can't read that back.",
    ),
    Rule(
        "ssn_digits",
        re.compile(
            r"\b(?:social|ssn|last (?:four|4))\b[^.?!]{0,40}?(?:\d[\s,-]*){4}"
            r"|(?:\d[\s,-]*){4}[^.?!]{0,20}\b(?:social|ssn)\b",
            re.I,
        ),
        "For your privacy, I can't read that back.",
    ),
    Rule(
        "date_of_birth",
        re.compile(
            rf"\b(?:born|birth|dob|birthday)\b[^.?!]{{0,40}}(?:{_MONTH}|\d{{1,2}}/\d{{1,2}}|"
            r"(?:19|20)\d\d)",
            re.I,
        ),
        "For your privacy, I can't read that back.",
    ),
    Rule(
        "refill_promise",
        re.compile(
            r"\b(?:(?:is|been|was|has been) approved|ready (?:for|to) (?:pick ?up|collect)|"
            r"(?:has|have) been (?:filled|dispensed)|will be (?:filled|ready|approved))\b",
            re.I,
        ),
        "Your request has been sent to the clinic, and they'll follow up.",
        unless_negated=True,
    ),
    Rule(
        "dosing_advice",
        re.compile(
            r"\b(?:take|double|increase|decrease|reduce|lower|raise|stop taking|skip|try)\b"
            r"[^.?!]{0,40}\b(?:\d+\s?(?:mg|milligrams?|pills?|tablets?|capsules?)|dose|dosage)\b"
            r"|\b(?:you should|i'?d recommend|i recommend|try taking)\b[^.?!]{0,30}"
            r"\b(?:ibuprofen|acetaminophen|tylenol|advil|aspirin|naproxen|aleve|motrin)\b",
            re.I,
        ),
        "I can't give medical advice, but I can pass a message to the care team.",
        unless_negated=True,
    ),
)

_SENTENCE_END = re.compile(r"(?<=[.?!])\s+")


def check_sentence(sentence: str) -> tuple[str, str | None]:
    """Return (text to speak, name of the rule that blocked it or None)."""
    for rule in RULES:
        if rule.pattern.search(sentence) and not (
            rule.unless_negated and _NEGATION.search(sentence)
        ):
            return rule.replacement, rule.name
    return sentence, None


async def guard_stream(chunks: AsyncIterable[Any], *, call_id: str) -> AsyncIterator[Any]:
    """Pass LLM output through `check_sentence` one complete sentence at a time.

    Text is held only until its sentence ends, so speech still starts after the first
    sentence. Tool calls, usage and other chunk data pass through unchanged.
    """
    buffer = ""
    async for chunk in chunks:
        text, passthrough = _split(chunk)
        if passthrough is not None:
            if buffer:  # keep order: finish pending speech before a tool call
                yield _checked(buffer, call_id)
                buffer = ""
            yield passthrough
        if not text:
            continue
        buffer += text
        *complete, buffer = _SENTENCE_END.split(buffer)
        for sentence in complete:
            yield _checked(sentence, call_id) + " "
    if buffer:
        yield _checked(buffer, call_id)


def _split(chunk: Any) -> tuple[str, Any | None]:
    """Separate spoken text from the rest of a chunk (which is passed through untouched)."""
    if isinstance(chunk, str):
        return chunk, None
    if isinstance(chunk, ChatChunk) and chunk.delta is not None and chunk.delta.content:
        text = chunk.delta.content
        rest = chunk.model_copy(update={"delta": chunk.delta.model_copy(update={"content": None})})
        has_rest = bool(rest.delta and (rest.delta.tool_calls or rest.delta.extra)) or rest.usage
        return text, rest if has_rest else None
    return "", chunk


def _checked(sentence: str, call_id: str) -> str:
    spoken, rule = check_sentence(sentence)
    if rule is not None:
        logger.warning("event=speech_blocked call_id=%s rule=%s", call_id, rule)
    return spoken
