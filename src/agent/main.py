from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli

from agent.agents.after_hours import AfterHoursAgent
from agent.agents.receptionist import ReceptionistAgent
from agent.config import VoiceSettings, build_agent_session
from agent.guard import ClinicAgent
from agent.metrics import attach_session_metrics
from agent.state import CallState
from agent.tracing import configure_tracing
from clinic.audit import AuditLogger
from clinic.clock import FixedClock, clock_for_job
from clinic.config import Settings
from clinic.domain.hours import is_open
from clinic.logging import configure_logging, daily_log_file
from clinic.models import CallMode, CallSession, SessionStatus
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

logger = logging.getLogger("sunrise.agent")
# Masked, gitignored, one file per day, kept 7 days. Summarize with `uv run clinic-report`.
LOG_DIR = Path("logs")
LOG_KEEP_DAYS = 7


def agent_for(state: CallState) -> ClinicAgent:
    """The receptionist during office hours, the message-taker otherwise."""
    return ReceptionistAgent(state) if state.mode == CallMode.OPEN else AfterHoursAgent(state)


async def entrypoint(ctx: JobContext) -> None:
    load_dotenv()
    clinic_settings = Settings()
    configure_logging(
        clinic_settings.log_level_number,
        log_file=daily_log_file(LOG_DIR, keep_days=LOG_KEEP_DAYS),
    )
    voice_settings = VoiceSettings()
    voice_settings.require_deepgram_key()
    pepper = clinic_settings.require_hash_pepper()
    await ctx.connect()

    database = Database(clinic_settings.database_path)
    await asyncio.to_thread(seed_database, database, pepper)  # never block the audio loop
    clock = clock_for_job(
        ctx.job.metadata,
        allow_time_simulation=clinic_settings.allow_time_simulation,
        demo_now=clinic_settings.demo_now,
    )
    session_repository = SQLiteSessionRepository(database)
    service = ClinicService(
        patient_repository=SQLitePatientRepository(database),
        appointment_repository=SQLiteAppointmentRepository(database),
        session_repository=session_repository,
        request_repository=SQLiteRequestRepository(database),
        audit_logger=AuditLogger(SQLiteAuditRepository(database)),
        clock=clock,
        verification_pepper=pepper,
        slot_repository=SQLiteSlotRepository(database),
    )

    # Open/closed is decided once, at call start, and stored server-side. The service
    # re-checks office hours on every patient-data request as well.
    now = clock.now()
    call_id = str(uuid4())
    mode = CallMode.OPEN if is_open(now) else CallMode.CLOSED
    simulated = isinstance(clock, FixedClock)
    await asyncio.to_thread(
        session_repository.create,
        CallSession(
            call_id=call_id,
            mode=mode,
            status=SessionStatus.OPEN,
            simulated_time=now if simulated else None,
            updated_at=now,
        ),
    )
    state = CallState(call_id=call_id, mode=mode, service=service, clock=clock)
    agent = agent_for(state)
    tracer_provider = configure_tracing(call_id)  # None unless Langfuse keys are set
    voice_session = build_agent_session(state, voice_settings)
    attach_session_metrics(voice_session, call_id)

    async def close_call() -> None:
        await asyncio.to_thread(service.close_call, call_id)
        if tracer_provider is not None:
            await asyncio.to_thread(tracer_provider.force_flush)

    ctx.add_shutdown_callback(close_call)
    await voice_session.start(room=ctx.room, agent=agent, record=False)
    logger.info(
        "event=voice_session_started call_id=%s clinic_mode=%s simulated_time=%s clinic_time=%s",
        call_id,
        mode,
        simulated,
        f"{now:%a %b %d %H:%M %Z}",  # no year: an ISO date would be masked as a DOB
    )


def main() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
