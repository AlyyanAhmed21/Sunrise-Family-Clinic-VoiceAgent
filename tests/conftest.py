from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from clinic.audit import AuditLogger
from clinic.clock import FakeClock
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

TEST_PEPPER = "deterministic-test-pepper"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "clinic.sqlite3")
    db.create_schema()
    seed_database(db, TEST_PEPPER)
    return db


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 2, 10, 0, tzinfo=ZoneInfo("America/New_York")))


@pytest.fixture
def clinic_service(database: Database, clock: FakeClock, tmp_path: Path) -> ClinicService:
    return ClinicService(
        patient_repository=SQLitePatientRepository(database),
        appointment_repository=SQLiteAppointmentRepository(database),
        session_repository=SQLiteSessionRepository(database),
        request_repository=SQLiteRequestRepository(database),
        audit_logger=AuditLogger(SQLiteAuditRepository(database)),
        clock=clock,
        verification_pepper=TEST_PEPPER,
        slot_repository=SQLiteSlotRepository(database),
        outbox_dir=tmp_path / "outbox",  # never write test emails into the demo outbox
    )
