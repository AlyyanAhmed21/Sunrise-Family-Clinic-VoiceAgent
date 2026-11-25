"""Open/closed routing, time simulation boundaries, and what the voice agent may never do."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from agent_helpers import MakeState
from livekit.agents.llm import utils

import agent
from agent.agents.after_hours import AfterHoursAgent
from agent.agents.receptionist import ReceptionistAgent
from agent.main import agent_for
from agent.tools.patient import PATIENT_TOOLS
from clinic.api.main import app
from clinic.clock import FixedClock, SystemClock, clock_for_job
from clinic.domain.hours import is_open
from clinic.models import CallMode

ET = ZoneInfo("America/New_York")


def test_normal_mode_uses_the_real_clock_in_eastern_time() -> None:
    clock = clock_for_job(None, allow_time_simulation=False, demo_now="2026-11-24T10:00:00-05:00")

    assert isinstance(clock, SystemClock)
    now = clock.now()
    assert now.tzinfo == ET
    assert abs((now - datetime.now(ET)).total_seconds()) < 5
    expected_open = now.weekday() < 5 and 9 <= now.hour < 17
    assert is_open(now) is expected_open


@pytest.mark.parametrize(
    ("demo_now", "mode"),
    [
        ("2026-11-24T10:00:00-05:00", CallMode.OPEN),  # Tuesday 10 AM
        ("2026-11-24T09:00:00-05:00", CallMode.OPEN),  # opening minute
        ("2026-11-24T16:59:00-05:00", CallMode.OPEN),
        ("2026-11-24T17:00:00-05:00", CallMode.CLOSED),  # 5 PM exactly is closed
        ("2026-11-24T19:00:00-05:00", CallMode.CLOSED),  # Tuesday 7 PM
        ("2026-11-24T08:59:00-05:00", CallMode.CLOSED),
        ("2026-11-28T10:00:00-05:00", CallMode.CLOSED),  # Saturday
        ("2026-11-24T15:00:00Z", CallMode.OPEN),  # 10 AM Eastern given in UTC
    ],
)
def test_simulated_time_selects_the_agent_for_the_call(
    make_state: MakeState, demo_now: str, mode: CallMode
) -> None:
    clock = clock_for_job("", allow_time_simulation=True, demo_now=demo_now)
    assert isinstance(clock, FixedClock)
    assert (CallMode.OPEN if is_open(clock.now()) else CallMode.CLOSED) == mode

    agent = agent_for(make_state(mode=mode))

    expected = ReceptionistAgent if mode == CallMode.OPEN else AfterHoursAgent
    assert type(agent) is expected


def test_after_hours_agent_has_no_patient_tools(make_state: MakeState) -> None:
    agent = agent_for(make_state(mode=CallMode.CLOSED))

    tool_ids = {tool.id for tool in agent.tools}
    assert tool_ids == {"record_callback_message", "end_call"}
    assert not tool_ids & {tool.id for tool in PATIENT_TOOLS}


def _all_tool_schemas(make_state: MakeState) -> list[tuple[str, set[str]]]:
    tools = [
        *agent_for(make_state("open", mode=CallMode.OPEN)).tools,
        *agent_for(make_state("closed", mode=CallMode.CLOSED)).tools,
    ]
    schemas = []
    for tool in tools:
        if hasattr(tool, "info"):
            schema = utils.build_legacy_openai_schema(tool)["function"]
            schemas.append((schema["name"], set(schema["parameters"].get("properties", {}))))
        else:
            schemas.append((tool.id, set()))
    return schemas


def test_no_agent_tool_can_reset_delete_or_change_time(make_state: MakeState) -> None:
    for name, params in _all_tool_schemas(make_state):
        assert not any(word in name for word in ("reset", "delete", "drop", "clear", "seed"))
        assert not params & {"now", "time", "clock", "demo_now", "simulate_time", "mode"}, name


def test_http_api_exposes_only_health_checks() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert paths - {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"} == {
        "/health",
        "/ready",
    }


def test_demo_reset_lives_only_in_the_operator_cli() -> None:
    """The reset is a developer command (`clinic reset-demo`); the voice agent cannot reach it."""
    agent_source = "".join(
        path.read_text(encoding="utf-8") for path in Path(agent.__file__).parent.rglob("*.py")
    )

    assert "reset_demo" not in agent_source
    assert "DELETE FROM" not in agent_source
