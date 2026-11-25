"""Run a scripted caller through the real agents and the real LLM, in text mode.

Each run gets its own seeded SQLite database and email outbox in a temporary directory, so
the results can be checked turn by turn and record by record. No audio, STT or TTS.
Used by `scripts/text_conversations.py` (prints) and `tests/evals` (asserts).
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from livekit.agents import AgentSession
from livekit.agents.voice.run_result import (
    AgentHandoffEvent,
    ChatMessageEvent,
    FunctionCallEvent,
    FunctionCallOutputEvent,
    RunResult,
)

from agent.agents.after_hours import AfterHoursAgent
from agent.agents.receptionist import ReceptionistAgent
from agent.config import VoiceSettings, build_llm
from agent.guard import ClinicAgent
from agent.state import CallState
from clinic.audit import AuditLogger
from clinic.clock import FakeClock
from clinic.domain.hours import is_open
from clinic.models import CallMode, CallSession
from clinic.persistence.db import Database
from clinic.persistence.repositories import (
    SQLiteAppointmentRepository,
    SQLiteAuditRepository,
    SQLitePatientRepository,
    SQLiteRequestRepository,
    SQLiteSessionRepository,
    SQLiteSlotRepository,
)
from clinic.persistence.seed import seed_database
from clinic.service import ClinicService

ET = ZoneInfo("America/New_York")
OPEN = datetime(2026, 11, 25, 14, 0, tzinfo=ET)  # Wednesday 2 PM
CLOSED = datetime(2026, 11, 25, 20, 30, tzinfo=ET)  # Wednesday 8:30 PM
CALL_ID = "simulated-call"
TURN_TIMEOUT_SECONDS = 60


@dataclass
class Turn:
    caller: str
    agent: list[str] = field(default_factory=list)
    tool_calls: list[tuple[str, str]] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)


@dataclass
class Simulation:
    turns: list[Turn]
    records: dict[str, list[tuple[object, ...]]]
    outbox: list[str]

    @property
    def agent_text(self) -> str:
        return " ".join(text for turn in self.turns for text in turn.agent)

    @property
    def tools_called(self) -> list[str]:
        return [name for turn in self.turns for name, _ in turn.tool_calls]

    @property
    def handoffs(self) -> list[str]:
        return [name for turn in self.turns for name in turn.handoffs]

    def render(self) -> str:
        lines: list[str] = []
        for turn in self.turns:
            lines.append(f"CALLER: {turn.caller}")
            lines += [f"    -> {name}({args})" for name, args in turn.tool_calls]
            lines += [f"    == handoff to {name}" for name in turn.handoffs]
            lines += [f"  AGENT: {text}" for text in turn.agent]
        lines.append("  --- backend records ---")
        for table, rows in self.records.items():
            lines += [f"  {table}: {row}" for row in rows]
        lines += [f"  outbox: {email}" for email in self.outbox]
        return "\n".join(lines)


_RECORD_QUERIES = {
    "session": "SELECT mode, verified_patient_id, failed_attempts, status FROM call_sessions",
    "requests": "SELECT request_type, patient_id, masked_summary, outcome, medication_name, "
    "pharmacy, callback_name, callback_phone FROM patient_requests",
    "audit": "SELECT action, outcome, record_id FROM audit_events ORDER BY rowid",
    "new_patients": "SELECT first_name, last_name, dob, phone, email, insurance FROM patients "
    "WHERE patient_id LIKE 'NEW-%'",
    "new_appointments": "SELECT doctor_name, start_at, status FROM appointments "
    "WHERE appointment_id NOT LIKE 'fixture-%'",
    "unavailable_slots": "SELECT slot_id FROM available_slots WHERE available = 0",
}


async def simulate(turns: Sequence[str], *, now: datetime = OPEN) -> Simulation:
    """Play `turns` as the caller against a fresh database; return transcript and records."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        state = _make_state(root, now)
        played = await _converse(state, turns)
        return Simulation(played, _records(root / "clinic.sqlite3"), _outbox(root))


def _make_state(directory: Path, now: datetime) -> CallState:
    database = Database(directory / "clinic.sqlite3")
    pepper = "simulation-pepper"
    seed_database(database, pepper)  # reads data/seed from the repository root
    clock = FakeClock(now)
    mode = CallMode.OPEN if is_open(now) else CallMode.CLOSED
    sessions = SQLiteSessionRepository(database)
    sessions.create(CallSession(call_id=CALL_ID, mode=mode, updated_at=now))
    service = ClinicService(
        patient_repository=SQLitePatientRepository(database),
        appointment_repository=SQLiteAppointmentRepository(database),
        session_repository=sessions,
        request_repository=SQLiteRequestRepository(database),
        audit_logger=AuditLogger(SQLiteAuditRepository(database)),
        clock=clock,
        verification_pepper=pepper,
        slot_repository=SQLiteSlotRepository(database),
        outbox_dir=directory / "outbox",
    )
    return CallState(call_id=CALL_ID, mode=mode, service=service, clock=clock)


async def _converse(state: CallState, turns: Sequence[str]) -> list[Turn]:
    agent: ClinicAgent = (
        ReceptionistAgent(state) if state.mode == CallMode.OPEN else AfterHoursAgent(state)
    )
    played: list[Turn] = []
    async with AgentSession(llm=build_llm(VoiceSettings()), userdata=state) as session:
        await session.start(agent)
        for text in turns:
            turn = Turn(caller=text)
            played.append(turn)
            try:
                result: RunResult[None] = await asyncio.wait_for(
                    session.run(user_input=text), timeout=TURN_TIMEOUT_SECONDS
                )
            except (TimeoutError, RuntimeError):  # the call ended (emergency, handoff)
                break
            for event in result.events:
                _add_event(turn, event)
    return played


def _add_event(turn: Turn, event: object) -> None:
    if isinstance(event, ChatMessageEvent) and event.item.role == "assistant":
        turn.agent.append(event.item.text_content or "")
    elif isinstance(event, FunctionCallEvent):
        turn.tool_calls.append((event.item.name, event.item.arguments))
    elif isinstance(event, FunctionCallOutputEvent):
        turn.tool_outputs.append(event.item.output)
    elif isinstance(event, AgentHandoffEvent):
        turn.handoffs.append(type(event.new_agent).__name__)


def _records(path: Path) -> dict[str, list[tuple[object, ...]]]:
    connection = sqlite3.connect(path)
    try:
        return {
            name: [tuple(row) for row in connection.execute(sql).fetchall()]
            for name, sql in _RECORD_QUERIES.items()
        }
    finally:
        connection.close()


def _outbox(root: Path) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted((root / "outbox").glob("*.json"))]
