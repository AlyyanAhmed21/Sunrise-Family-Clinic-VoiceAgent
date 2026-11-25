"""Pre-LLM capture of verification secrets from caller speech.

Runs in code on every caller turn, before the LLM sees the text. A date of birth and SSN
digits are moved into server-side `CallState` and cut out of the transcript, so the model
only learns *that* a detail was received, never its value. The LLM still runs the
conversation; the backend still does the matching.

Whether a turn is about the date of birth or the SSN is decided from explicit cues in the
caller's words or in the agent's previous question ("date of birth", "last four"). A full
date with a past year is always treated as a date of birth.
"""

from __future__ import annotations

import re

from pydantic import SecretStr

from agent.state import CallState
from clinic.security.parsing import DateParts, Span, parse_date_parts, spoken_digits

_DOB_CUE = re.compile(r"\b(?:birth|born|birthday|dob|d\.o\.b)\b", re.I)
_SSN_CUE = re.compile(r"\b(?:social|ssn|last\s*(?:four|4)|four\s+digits)\b", re.I)
_FULL_SSN = re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b")
_AFFIRMATIVE = re.compile(
    r"^\W*(?:yes|yeah|yep|yup|correct|right|sure|absolutely|definitely|ok(?:ay)?|"
    r"that'?s (?:right|correct)|that is (?:right|correct)|sounds (?:good|right)|"
    r"go ahead|please do|perfect)\b",
    re.I,
)
_HESITATION = re.compile(r"\b(?:no|not|wrong|wait|change|actually|but|incorrect)\b", re.I)
REDACTED = "[redacted]"


def is_affirmative(text: str) -> bool:
    """A clear "yes" with no correction attached ("yes, but change the time" is not one)."""
    return bool(_AFFIRMATIVE.search(text)) and not _HESITATION.search(text)


def sanitize_turn(text: str, state: CallState, *, last_agent_text: str) -> str:
    """Capture DOB / SSN-last-four into `state`; return the text the LLM may see."""
    spans: list[Span] = []
    notes: list[str] = []

    parts = parse_date_parts(text, today=state.today)
    full_past_date = parts.is_complete and (parts.year or 0) < state.today.year
    dob_cue = _DOB_CUE.search(text) or _DOB_CUE.search(last_agent_text)
    if not parts.is_empty and (dob_cue or full_past_date):
        spans.extend(parts.spans)
        notes.append(_record_dob(state, parts))

    ssn_cue = _SSN_CUE.search(text) or _SSN_CUE.search(last_agent_text)
    if not state.verified and ssn_cue:
        digits, digit_spans = _ssn_digits(text, skip=tuple(spans))
        if digits:
            spans.extend(digit_spans)
            notes.append(_record_last_four(state, digits))

    full_ssn = [match.span() for match in _FULL_SSN.finditer(text)]
    if full_ssn:
        spans.extend(full_ssn)
        notes.append("a full SSN was said and discarded; ask for only the last four digits")

    safe = _redact(text, spans)
    return f"{safe} [system note: {'; '.join(dict.fromkeys(notes))}]" if notes else safe


def _ssn_digits(text: str, *, skip: tuple[Span, ...]) -> tuple[str, tuple[Span, ...]]:
    """Digits after "...last four digits are", if the caller said so; otherwise all digits.

    Stops stray numbers earlier in the same breath (a split year, a count) joining the SSN.
    """
    cues = list(_SSN_CUE.finditer(text))
    if cues:
        after_cue = spoken_digits(text, skip=skip + ((0, cues[-1].end()),))
        if after_cue[0]:
            return after_cue
    return spoken_digits(text, skip=skip)


def _record_dob(state: CallState, parts: DateParts) -> str:
    merged = parts if parts.is_complete else parts.over(state.dob)
    state.dob = merged
    if not merged.is_complete:
        return f"date of birth partly received, still need the {' and '.join(merged.missing)}"
    if state.captured_dob() is None:
        state.dob = DateParts()
        return "the date of birth heard is not a valid past date; ask for it again"
    return "date of birth received"


def _record_last_four(state: CallState, digits: str) -> str:
    if len(digits) == 4:
        state.last_four = SecretStr(digits)
        return "last four SSN digits received"
    state.last_four = None
    if len(digits) > 4:
        return "more than four digits were said and discarded; ask for only the last four"
    return "fewer than four SSN digits were heard; ask for the last four again"


def _redact(text: str, spans: list[Span]) -> str:
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + REDACTED + text[end:]
    return re.sub(rf"(?:{re.escape(REDACTED)}[\s,]*)+{re.escape(REDACTED)}", REDACTED, text)
