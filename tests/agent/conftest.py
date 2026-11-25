from __future__ import annotations

import pytest

from agent.state import CallState
from clinic.clock import FakeClock
from clinic.models import CallMode, CallSession
from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLiteSessionRepository
from clinic.service import ClinicService


@pytest.fixture
def make_state(database: Database, clinic_service: ClinicService, clock: FakeClock):  # type: ignore[no-untyped-def]
    """A call session in the database plus the matching agent-side `CallState`."""

    def make(
        call_id: str = "call-1",
        *,
        mode: CallMode = CallMode.OPEN,
        verified_patient: str | None = None,
    ) -> CallState:
        SQLiteSessionRepository(database).create(
            CallSession(
                call_id=call_id,
                mode=mode,
                verified_patient_id=verified_patient,
                updated_at=clock.now(),
            )
        )
        return CallState(
            call_id=call_id,
            mode=mode,
            service=clinic_service,
            clock=clock,
            verified=verified_patient is not None,
        )

    return make
