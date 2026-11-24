"""Small, SDK-independent PHI redaction primitives used by the Step 0 spike.

This is a conservative prototype, not the production masker. The production
masking layer is implemented in Step 1 and must cover spoken dates, phones,
email, member IDs, and provider-specific message shapes.
"""

from __future__ import annotations

import copy
import re
from collections.abc import MutableMapping
from typing import Any

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)\d{3}[- ]?\d{2}[- ]?\d{4}(?!\d)"), "[REDACTED_SSN]"),
    (
        re.compile(r"\b(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b"),
        "[REDACTED_DOB]",
    ),
    (
        re.compile(r"\b(?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])[-/](?:\d{2}|\d{4})\b"),
        "[REDACTED_DOB]",
    ),
    (re.compile(r"(?i)\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
    (
        re.compile(
            r"(?i)\b(?:last\s*(?:four|4)(?:\s*digits)?|ssn\s*(?:last\s*)?four)"
            r"(\s*(?:is|are|:|=)?\s*)(?:\d(?:[\s-]*\d){3,})"
        ),
        "[REDACTED_LAST4]",
    ),
)
_TEXT_KEYS = frozenset({"content", "text", "transcript", "message", "transcription"})


def redact_text(value: str) -> str:
    """Mask common written identifier forms without retaining the raw value."""
    result = value
    for pattern, replacement in _PATTERNS:
        if replacement == "[REDACTED_LAST4]":
            result = pattern.sub(
                lambda match: match.group(0).split()[0] + " [REDACTED_LAST4]", result
            )
        else:
            result = pattern.sub(replacement, result)
    return result


def _redact_in_place(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, str):
        return redact_text(value) if field_name in _TEXT_KEYS else value
    if isinstance(value, list):
        return [_redact_in_place(item, field_name) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_in_place(item, field_name) for item in value)
    if isinstance(value, MutableMapping):
        for key, child in list(value.items()):
            value[key] = _redact_in_place(child, str(key).lower())
        return value
    attributes = dict(vars(value)) if hasattr(value, "__dict__") else {}
    slots = getattr(type(value), "__slots__", ())
    if isinstance(slots, str):
        slots = (slots,)
    for key in set(attributes) | set(slots):
        if key.startswith("_") and key not in attributes:
            continue
        try:
            child = getattr(value, key)
            setattr(value, key, _redact_in_place(child, key.lower()))
        except (AttributeError, TypeError):
            continue
    return value


def redact_context_copy(context: Any) -> Any:
    """Return a deep-copied chat context with supported text fields redacted."""
    return _redact_in_place(copy.deepcopy(context))


def redact_context_in_place(context: Any) -> Any:
    """Redact a mutable inbound context before it can be retained or handed off."""
    return _redact_in_place(context)
