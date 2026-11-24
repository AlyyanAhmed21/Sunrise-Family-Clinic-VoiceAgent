from __future__ import annotations

from typing import Protocol

from clinic.models import (
    Appointment,
    AuditEvent,
    AvailableSlot,
    CallSession,
    Medication,
    Patient,
    PatientRequest,
)
from clinic.persistence.db import Database


class PatientRepository(Protocol):
    def get(self, patient_id: str) -> Patient | None: ...
    def list_all(self) -> list[Patient]: ...
    def get_verification_record(self, patient_id: str) -> tuple[str, str] | None: ...


class SessionRepository(Protocol):
    def get(self, call_id: str) -> CallSession | None: ...
    def create(self, session: CallSession) -> None: ...
    def save(self, session: CallSession) -> None: ...


class RequestRepository(Protocol):
    def save(self, request: PatientRequest) -> None: ...


class AuditRepository(Protocol):
    def save(self, event: AuditEvent) -> None: ...


class SQLitePatientRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, patient_id: str) -> Patient | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
            ).fetchone()
            if row is None:
                return None
            medication_rows = connection.execute(
                "SELECT name, refills_remaining, last_filled, pharmacy FROM medications "
                "WHERE patient_id = ?",
                (patient_id,),
            ).fetchall()
        medications = tuple(
            Medication(
                name=row_med["name"],
                refills_remaining=row_med["refills_remaining"],
                last_filled=row_med["last_filled"],
                pharmacy=row_med["pharmacy"],
            )
            for row_med in medication_rows
        )
        return Patient(
            patient_id=row["patient_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            dob=row["dob"],
            phone=row["phone"],
            medications=medications,
            next_appointment=row["next_appointment"],
            lab_results_status=row["lab_results_status"],
            balance_due=row["balance_due"],
        )

    def list_all(self) -> list[Patient]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT patient_id FROM patients ORDER BY patient_id"
            ).fetchall()
        return [patient for row in rows if (patient := self.get(row["patient_id"])) is not None]

    def get_verification_record(self, patient_id: str) -> tuple[str, str] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT last4_salt, last4_digest FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
        if row is None:
            return None
        return row["last4_salt"], row["last4_digest"]


class SQLiteSessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, call_id: str) -> CallSession | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM call_sessions WHERE call_id = ?", (call_id,)
            ).fetchone()
        if row is None:
            return None
        return CallSession(
            call_id=row["call_id"],
            mode=row["mode"],
            verified_patient_id=row["verified_patient_id"],
            failed_attempts=row["failed_attempts"],
            unparsed_attempts=row["unparsed_attempts"],
            status=row["status"],
            simulated_time=row["simulated_time"],
            updated_at=row["updated_at"],
        )

    def create(self, session: CallSession) -> None:
        self.save(session)

    def save(self, session: CallSession) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO call_sessions (
                    call_id, mode, verified_patient_id, failed_attempts,
                    unparsed_attempts, status, simulated_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    mode=excluded.mode,
                    verified_patient_id=excluded.verified_patient_id,
                    failed_attempts=excluded.failed_attempts,
                    unparsed_attempts=excluded.unparsed_attempts,
                    status=excluded.status,
                    simulated_time=excluded.simulated_time,
                    updated_at=excluded.updated_at
                """,
                (
                    session.call_id,
                    session.mode,
                    session.verified_patient_id,
                    session.failed_attempts,
                    session.unparsed_attempts,
                    session.status,
                    session.simulated_time.isoformat() if session.simulated_time else None,
                    session.updated_at.isoformat(),
                ),
            )


class SQLiteRequestRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, request: PatientRequest) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patient_requests (
                    request_id, call_id, patient_id, request_type,
                    created_at, masked_summary, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO NOTHING
                """,
                (
                    request.request_id,
                    request.call_id,
                    request.patient_id,
                    request.request_type,
                    request.created_at.isoformat(),
                    request.masked_summary,
                    request.status,
                ),
            )


class SQLiteAuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, event: AuditEvent) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    audit_id, call_id, actor, record_id, timestamp, action, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.audit_id,
                    event.call_id,
                    event.actor,
                    event.record_id,
                    event.timestamp.isoformat(),
                    event.action,
                    event.outcome,
                ),
            )


class SQLiteSlotRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_available(self) -> list[AvailableSlot]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT slot_id, doctor_name, start_at
                FROM available_slots
                WHERE available = 1
                ORDER BY start_at
                """
            ).fetchall()
        return [
            AvailableSlot(
                slot_id=row["slot_id"],
                doctor_name=row["doctor_name"],
                start_at=row["start_at"],
            )
            for row in rows
        ]


class SQLiteAppointmentRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_for_patient(self, patient_id: str) -> list[Appointment]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT appointment_id, patient_id, doctor_name, start_at, status
                FROM appointments
                WHERE patient_id = ?
                ORDER BY start_at
                """,
                (patient_id,),
            ).fetchall()
        return [
            Appointment(
                appointment_id=row["appointment_id"],
                patient_id=row["patient_id"],
                doctor_name=row["doctor_name"],
                start_at=row["start_at"],
                status=row["status"],
            )
            for row in rows
        ]
