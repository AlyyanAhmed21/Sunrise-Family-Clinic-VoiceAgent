from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from typing import Protocol
from uuid import uuid4

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
    def save_with_audit(self, request: PatientRequest, event: AuditEvent) -> None: ...
    def create_refill_with_audit(
        self,
        request: PatientRequest,
        event: AuditEvent,
        confirmation_digest: str,
    ) -> tuple[PatientRequest, bool]: ...


class AuditRepository(Protocol):
    def save(self, event: AuditEvent) -> None: ...


class AppointmentRepository(Protocol):
    def list_for_patient(self, patient_id: str) -> list[Appointment]: ...

    def book_new_patient(
        self,
        *,
        patient_id: str,
        first_name: str,
        last_name: str,
        dob: str,
        phone: str,
        email: str,
        insurance: str,
        slot_id: str,
        request: PatientRequest,
        event: AuditEvent,
    ) -> Appointment: ...

    def book_existing_patient(
        self,
        *,
        patient_id: str,
        call_id: str,
        slot_id: str,
        email: str,
        request: PatientRequest,
        event: AuditEvent,
    ) -> Appointment: ...


class SlotRepository(Protocol):
    def list_available(self) -> list[AvailableSlot]: ...


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
            email=row["email"],
            insurance=row["insurance"],
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
                "SELECT last4_salt, last4_digest, verification_ready "
                "FROM patients WHERE patient_id = ?",
                (patient_id,),
            ).fetchone()
        if row is None or not row["verification_ready"]:
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
            pending_refill_token_digest=row["pending_refill_token_digest"],
            pending_refill_medication=row["pending_refill_medication"],
            pending_refill_pharmacy=row["pending_refill_pharmacy"],
            pending_refill_expires_at=(
                datetime.fromisoformat(row["pending_refill_expires_at"])
                if row["pending_refill_expires_at"]
                else None
            ),
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
                    unparsed_attempts, status, simulated_time,
                    pending_refill_token_digest, pending_refill_medication,
                    pending_refill_pharmacy, pending_refill_expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    mode=excluded.mode,
                    verified_patient_id=excluded.verified_patient_id,
                    failed_attempts=excluded.failed_attempts,
                    unparsed_attempts=excluded.unparsed_attempts,
                    status=excluded.status,
                    simulated_time=excluded.simulated_time,
                    pending_refill_token_digest=excluded.pending_refill_token_digest,
                    pending_refill_medication=excluded.pending_refill_medication,
                    pending_refill_pharmacy=excluded.pending_refill_pharmacy,
                    pending_refill_expires_at=excluded.pending_refill_expires_at,
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
                    session.pending_refill_token_digest,
                    session.pending_refill_medication,
                    session.pending_refill_pharmacy,
                    (
                        session.pending_refill_expires_at.isoformat()
                        if session.pending_refill_expires_at
                        else None
                    ),
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
                    created_at, masked_summary, status, outcome,
                    medication_name, pharmacy, callback_name, callback_phone, subject_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    request.outcome,
                    request.medication_name,
                    request.pharmacy,
                    request.callback_name,
                    request.callback_phone,
                    request.patient_id or "UNVERIFIED",
                ),
            )

    def save_with_audit(self, request: PatientRequest, event: AuditEvent) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO patient_requests (
                    request_id, call_id, patient_id, request_type,
                    created_at, masked_summary, status, outcome,
                    medication_name, pharmacy, callback_name, callback_phone, subject_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _request_values(request),
            )
            _insert_audit_event(connection, event)

    def create_refill_with_audit(
        self,
        request: PatientRequest,
        event: AuditEvent,
        confirmation_digest: str,
    ) -> tuple[PatientRequest, bool]:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM patient_requests
                WHERE patient_id = ? AND request_type = 'refill'
                    AND medication_name = ? COLLATE NOCASE AND status = 'open'
                LIMIT 1
                """,
                (request.patient_id, request.medication_name),
            ).fetchone()
            is_duplicate = row is not None
            if row is None:
                connection.execute(
                    """
                    INSERT INTO patient_requests (
                        request_id, call_id, patient_id, request_type,
                        created_at, masked_summary, status, outcome,
                        medication_name, pharmacy, callback_name, callback_phone, subject_reference
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _request_values(request),
                )
                stored_request = request
            else:
                stored_request = _request_from_row(row)

            updated = connection.execute(
                """
                UPDATE call_sessions
                SET pending_refill_token_digest = NULL,
                    pending_refill_medication = NULL,
                    pending_refill_pharmacy = NULL,
                    pending_refill_expires_at = NULL
                WHERE call_id = ? AND pending_refill_token_digest = ?
                """,
                (request.call_id, confirmation_digest),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("pending refill confirmation changed")
            audit_event = event.model_copy(
                update={
                    "action": "refill_request_duplicate"
                    if is_duplicate
                    else "refill_request_recorded",
                    "record_id": stored_request.request_id,
                }
            )
            _insert_audit_event(connection, audit_event)
        return stored_request, is_duplicate


class SQLiteAuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, event: AuditEvent) -> None:
        with self.database.transaction() as connection:
            _insert_audit_event(connection, event)


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


def _request_values(request: PatientRequest) -> tuple[object, ...]:
    return (
        request.request_id,
        request.call_id,
        request.patient_id,
        request.request_type,
        request.created_at.isoformat(),
        request.masked_summary,
        request.status,
        request.outcome,
        request.medication_name,
        request.pharmacy,
        request.callback_name,
        request.callback_phone,
        request.patient_id or "UNVERIFIED",
    )


def _request_from_row(row: sqlite3.Row) -> PatientRequest:
    return PatientRequest(
        request_id=row["request_id"],
        call_id=row["call_id"],
        patient_id=row["patient_id"],
        request_type=row["request_type"],
        created_at=datetime.fromisoformat(row["created_at"]),
        masked_summary=row["masked_summary"],
        status=row["status"],
        outcome=row["outcome"],
        medication_name=row["medication_name"],
        pharmacy=row["pharmacy"],
        callback_name=row["callback_name"],
        callback_phone=row["callback_phone"],
    )


def _insert_audit_event(connection: sqlite3.Connection, event: AuditEvent) -> None:
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

    def book_new_patient(
        self,
        *,
        patient_id: str,
        first_name: str,
        last_name: str,
        dob: str,
        phone: str,
        email: str,
        insurance: str,
        slot_id: str,
        request: PatientRequest,
        event: AuditEvent,
    ) -> Appointment:
        """Atomically create a new patient, appointment, request and audit event."""
        with self.database.transaction() as connection:
            slot = connection.execute(
                "SELECT doctor_name, start_at FROM available_slots "
                "WHERE slot_id = ? AND available = 1",
                (slot_id,),
            ).fetchone()
            if slot is None:
                raise sqlite3.IntegrityError("appointment slot is no longer available")

            salt = secrets.token_hex(16)
            # New-patient booking does not collect SSN; this random placeholder
            # is never accepted for verification because verification_ready=0.
            placeholder_digest = secrets.token_hex(32)
            connection.execute(
                """
                INSERT INTO patients (
                    patient_id, first_name, last_name, dob, phone, email, insurance,
                    verification_ready, last4_salt, last4_digest, next_appointment,
                    lab_results_status, balance_due
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 'No recent labs', 0)
                """,
                (
                    patient_id,
                    first_name,
                    last_name,
                    dob,
                    phone,
                    email,
                    insurance,
                    salt,
                    placeholder_digest,
                ),
            )
            appointment_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO appointments (
                    appointment_id, patient_id, doctor_name, start_at, status
                ) VALUES (?, ?, ?, ?, 'scheduled')
                """,
                (appointment_id, patient_id, slot["doctor_name"], slot["start_at"]),
            )
            updated = connection.execute(
                "UPDATE available_slots SET available = 0 WHERE slot_id = ? AND available = 1",
                (slot_id,),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("appointment slot was already booked")
            connection.execute(
                """
                INSERT INTO patient_requests (
                    request_id, call_id, patient_id, request_type, created_at,
                    masked_summary, status, outcome, medication_name, pharmacy,
                    callback_name, callback_phone, subject_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _request_values(request),
            )
            _insert_audit_event(connection, event)
            return Appointment(
                appointment_id=appointment_id,
                patient_id=patient_id,
                doctor_name=slot["doctor_name"],
                start_at=slot["start_at"],
                status="scheduled",
            )

    def book_existing_patient(
        self,
        *,
        patient_id: str,
        call_id: str,
        slot_id: str,
        email: str,
        request: PatientRequest,
        event: AuditEvent,
    ) -> Appointment:
        """Atomically reserve a slot for a patient already verified in this call."""
        with self.database.transaction() as connection:
            slot = connection.execute(
                "SELECT doctor_name, start_at FROM available_slots "
                "WHERE slot_id = ? AND available = 1",
                (slot_id,),
            ).fetchone()
            if slot is None:
                raise sqlite3.IntegrityError("appointment slot is no longer available")
            connection.execute(
                "UPDATE patients SET email = ? WHERE patient_id = ?",
                (email, patient_id),
            )
            appointment_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO appointments (
                    appointment_id, patient_id, doctor_name, start_at, status
                ) VALUES (?, ?, ?, ?, 'scheduled')
                """,
                (appointment_id, patient_id, slot["doctor_name"], slot["start_at"]),
            )
            updated = connection.execute(
                "UPDATE available_slots SET available = 0 WHERE slot_id = ? AND available = 1",
                (slot_id,),
            )
            if updated.rowcount != 1:
                raise sqlite3.IntegrityError("appointment slot was already booked")
            connection.execute(
                """
                INSERT INTO patient_requests (
                    request_id, call_id, patient_id, request_type, created_at,
                    masked_summary, status, outcome, medication_name, pharmacy,
                    callback_name, callback_phone, subject_reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _request_values(request),
            )
            _insert_audit_event(connection, event)
            return Appointment(
                appointment_id=appointment_id,
                patient_id=patient_id,
                doctor_name=slot["doctor_name"],
                start_at=slot["start_at"],
                status="scheduled",
            )
