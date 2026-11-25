from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(ZoneInfo("America/New_York"))


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FixedClock:
    """Demo clock: starts at a simulated Eastern time and then advances in real time, so
    audit timestamps within a call keep their real order and spacing."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Fixed clock timestamp must be timezone-aware")
        self._instant = instant.astimezone(ZoneInfo("America/New_York"))
        self._started = time.monotonic()

    def now(self) -> datetime:
        return self._instant + timedelta(seconds=time.monotonic() - self._started)


def clock_for_job(
    metadata: str | None,
    *,
    allow_time_simulation: bool = False,
    demo_now: str | None = None,
) -> SystemClock | FixedClock:
    """Real Eastern time unless simulation is explicitly enabled by the operator.

    With `allow_time_simulation`, trusted job-dispatch metadata
    (`{"demo_mode": true, "demo_now": ...}`) wins; otherwise the local `DEMO_NOW` setting is
    used. The Agent Console dispatches jobs without metadata, so `DEMO_NOW` is how a local
    after-hours demo is run. Callers and the LLM can never change the clinic clock.
    """
    if not allow_time_simulation:
        return SystemClock()
    if metadata:
        try:
            payload = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid LiveKit job metadata") from exc
        if not isinstance(payload, dict):
            raise ValueError("LiveKit job metadata must be a JSON object")
        if payload.get("demo_mode") is True:
            metadata_now = payload.get("demo_now")
            if not isinstance(metadata_now, str):
                raise ValueError("Demo mode requires a demo_now timestamp")
            return _fixed_clock(metadata_now)
    return _fixed_clock(demo_now) if demo_now else SystemClock()


def _fixed_clock(timestamp: str) -> FixedClock:
    try:
        instant = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise ValueError("Demo timestamp must be a valid ISO 8601 datetime") from exc
    return FixedClock(instant)
