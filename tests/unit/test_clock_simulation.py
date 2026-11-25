import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from clinic.clock import FixedClock, SystemClock, clock_for_job
from clinic.domain.hours import is_open


def _near(actual: datetime, expected: datetime) -> bool:
    return abs(actual - expected) < timedelta(seconds=1)


def test_simulated_clock_advances_so_audit_events_keep_their_order() -> None:
    clock = FixedClock(datetime(2026, 11, 24, 10, 0, tzinfo=ZoneInfo("America/New_York")))
    first = clock.now()
    time.sleep(0.02)
    assert clock.now() > first


def test_time_simulation_is_disabled_by_default() -> None:
    clock = clock_for_job('{"demo_mode": true, "demo_now": "2026-11-24T10:00:00-05:00"}')
    assert isinstance(clock, SystemClock)


def test_time_simulation_requires_explicit_feature_gate() -> None:
    clock = clock_for_job(
        '{"demo_mode": true, "demo_now": "2026-11-24T10:00:00-05:00"}',
        allow_time_simulation=True,
    )
    assert isinstance(clock, FixedClock)
    assert _near(clock.now(), datetime(2026, 11, 24, 10, 0, tzinfo=ZoneInfo("America/New_York")))


def test_time_simulation_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        clock_for_job(
            '{"demo_mode": true, "demo_now": "2026-11-24T10:00:00"}',
            allow_time_simulation=True,
        )


def test_time_simulation_ignores_non_demo_metadata() -> None:
    clock = clock_for_job('{"other": "value"}', allow_time_simulation=True)
    assert isinstance(clock, SystemClock)


EVENING = "2026-11-24T19:00:00-05:00"


def test_local_demo_now_is_used_when_console_sends_no_metadata() -> None:
    clock = clock_for_job("", allow_time_simulation=True, demo_now=EVENING)

    assert _near(clock.now(), datetime(2026, 11, 24, 19, 0, tzinfo=ZoneInfo("America/New_York")))
    assert not is_open(clock.now())


def test_local_demo_now_is_ignored_unless_simulation_is_allowed() -> None:
    assert isinstance(clock_for_job("", demo_now=EVENING), SystemClock)


def test_dispatch_metadata_takes_priority_over_local_demo_now() -> None:
    clock = clock_for_job(
        '{"demo_mode": true, "demo_now": "2026-11-24T10:00:00-05:00"}',
        allow_time_simulation=True,
        demo_now=EVENING,
    )

    assert clock.now().hour == 10


def test_demo_now_in_another_offset_is_converted_to_eastern() -> None:
    clock = clock_for_job("", allow_time_simulation=True, demo_now="2026-11-25T05:00:00+05:00")

    assert _near(clock.now(), datetime(2026, 11, 24, 19, 0, tzinfo=ZoneInfo("America/New_York")))


def test_demo_now_without_offset_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        clock_for_job("", allow_time_simulation=True, demo_now="2026-11-24T19:00:00")
