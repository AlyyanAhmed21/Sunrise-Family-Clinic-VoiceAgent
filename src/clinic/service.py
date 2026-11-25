from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from clinic.audit import AuditLogger
from clinic.clock import Clock
from clinic.domain.errors import (
    ClinicClosed,
    InvalidStateTransition,
    PatientRecordUnavailable,
    PersistenceFailure,
    UnauthorizedPatientAccess,
    UnknownCallSession,
    VerificationLocked,
)
from clinic.domain.hours import is_open
from clinic.domain.verification import verify_candidate
from clinic.models import (
    Appointment,
    AppointmentLookupResult,
    AppointmentSummary,
    AuditEvent,
    AvailableSlot,
    BalanceResult,
    BookingResult,
    CallMode,
    CallSession,
    LabStatusResult,
    Medication,
    Patient,
    PatientRequest,
    RefillResult,
    SessionStatus,
    VerificationCandidate,
    VerificationResult,
)
from clinic.persistence.repositories import (
    AppointmentRepository,
    PatientRepository,
    RequestRepository,
    SessionRepository,
    SlotRepository,
)

_LOCAL_TIMEZONE = ZoneInfo("America/New_York")
_PENDING_REFILL_LIFETIME = timedelta(minutes=5)


class ClinicService:
    """In-process application boundary for authorized patient service operations."""

    def __init__(
        self,
        patient_repository: PatientRepository,
        appointment_repository: AppointmentRepository,
        session_repository: SessionRepository,
        request_repository: RequestRepository,
        audit_logger: AuditLogger,
        clock: Clock,
        verification_pepper: str,
        slot_repository: SlotRepository | None = None,
        outbox_dir: Path = Path("data/outbox"),
    ) -> None:
        self.outbox_dir = outbox_dir  # simulated confirmation emails (synthetic data only)
        self.patient_repository = patient_repository
        self.appointment_repository = appointment_repository
        self.session_repository = session_repository
        self.request_repository = request_repository
        self.audit_logger = audit_logger
        self.clock = clock
        self.verification_pepper = verification_pepper
        self.slot_repository = slot_repository

    def ensure_open_call(self, call_id: str) -> CallSession:
        try:
            session = self._get_active_session(call_id)
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc
        if session.status == SessionStatus.LOCKED:
            raise VerificationLocked("Verification is locked; staff assistance is required")
        if session.mode != CallMode.OPEN or not is_open(self.clock.now()):
            raise ClinicClosed("Patient services are unavailable while the clinic is closed")
        return session

    def close_call(self, call_id: str) -> None:
        """Mark the call closed and drop any pending refill confirmation."""
        session = self.session_repository.get(call_id)
        if session is None:
            return
        self.session_repository.save(
            session.model_copy(
                update={
                    "status": SessionStatus.CLOSED,
                    "pending_refill_token_digest": None,
                    "pending_refill_medication": None,
                    "pending_refill_pharmacy": None,
                    "pending_refill_expires_at": None,
                    "updated_at": self.clock.now(),
                }
            )
        )

    def verify_caller(self, call_id: str, candidate: VerificationCandidate) -> VerificationResult:
        try:
            session = self._get_active_session(call_id)
            if session.status == SessionStatus.LOCKED:
                raise VerificationLocked("Verification is locked; staff assistance is required")
            if session.verified_patient_id is not None:
                raise InvalidStateTransition("This call has already completed verification")
            if session.mode != CallMode.OPEN or not is_open(self.clock.now()):
                raise ClinicClosed("Verification is unavailable while the clinic is closed")
            result = verify_candidate(
                candidate,
                session=session,
                patient_repository=self.patient_repository,
                session_repository=self.session_repository,
                pepper=self.verification_pepper,
            )
            # On success the audit names the record that was unlocked; failures name none,
            # so the audit trail never reveals which (or whether a) patient almost matched.
            self.audit_logger.record(
                call_id=call_id,
                action="identity_verification",
                outcome="success" if result.outcome == "verified" else "failure",
                record_id=result.verified_patient_id,
                timestamp=self.clock.now(),
            )
            return result
        except VerificationLocked:
            self._record_audit(call_id, "identity_verification", "locked")
            raise
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def list_available_slots(self, call_id: str) -> list[AvailableSlot]:
        self.ensure_open_call(call_id)
        if self.slot_repository is None:
            raise PersistenceFailure("Appointment availability is not configured")
        try:
            now = _local_datetime(self.clock.now())
            return [
                slot
                for slot in self.slot_repository.list_available()
                if _local_datetime(slot.start_at) >= now
            ]
        except sqlite3.Error as exc:
            raise PersistenceFailure("Appointment availability is unavailable") from exc

    def book_new_patient(
        self,
        call_id: str,
        *,
        full_name: str,
        dob: date,
        phone: str,
        email: str,
        insurance: str,
        reason: str,
        slot_id: str,
    ) -> BookingResult:
        """Create a synthetic new-patient record and reserve one slot atomically."""
        session = self.ensure_open_call(call_id)
        if session.verified_patient_id is not None:
            raise InvalidStateTransition("Use the verified-patient booking flow")
        name_parts = " ".join(full_name.split()).split()
        phone_digits = re.sub(r"\D", "", phone)
        if len(name_parts) < 2 or len(full_name) > 200 or len(phone_digits) not in {10, 11}:
            raise InvalidStateTransition("Required booking details are incomplete")
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise InvalidStateTransition("A valid email address is required")
        if dob >= self.clock.now().date():
            raise InvalidStateTransition("A valid date of birth is required")
        if not insurance.strip() or len(insurance) > 200 or not reason.strip() or len(reason) > 100:
            raise InvalidStateTransition("Insurance and visit reason are required")
        reason_summary = _visit_summary(reason)
        patient_id = f"NEW-{uuid4().hex[:10].upper()}"
        now = self.clock.now()
        request = PatientRequest(
            request_id=str(uuid4()),
            call_id=call_id,
            patient_id=patient_id,
            request_type="booking",
            created_at=now,
            masked_summary=f"New patient booking: {reason_summary}",
            status="open",
        )
        event = AuditEvent(
            audit_id=str(uuid4()),
            call_id=call_id,
            actor="caller",
            record_id=patient_id,
            timestamp=now,
            action="new_patient_appointment_booked",
            outcome="success",
        )
        try:
            appointment = self.appointment_repository.book_new_patient(
                patient_id=patient_id,
                first_name=name_parts[0],
                last_name=" ".join(name_parts[1:]),
                dob=dob.isoformat(),
                phone=phone_digits[-10:],
                email=email,
                insurance=insurance.strip()[:200],
                slot_id=slot_id,
                request=request,
                event=event,
            )
        except sqlite3.IntegrityError as exc:
            raise InvalidStateTransition(
                "That appointment time is no longer available. Please choose another."
            ) from exc
        except sqlite3.Error as exc:
            raise PersistenceFailure("The appointment could not be saved") from exc

        email_saved = self._write_confirmation_email(appointment, email, full_name)
        return BookingResult(
            patient_id=patient_id,
            appointment=AppointmentSummary(
                start_at=_local_datetime(appointment.start_at),
                doctor_name=appointment.doctor_name,
            ),
            email_confirmation_saved=email_saved,
        )

    def _write_confirmation_email(self, appointment: Appointment, email: str, name: str) -> bool:
        """Simulated confirmation email: a JSON file in the outbox (no real email is sent)."""
        payload = {
            "to": email,
            "subject": "Sunrise Family Clinic appointment confirmation",
            "patient_name": name,
            "appointment": appointment.start_at.isoformat(),
            "doctor": appointment.doctor_name,
            "instructions": "Arrive 15 minutes early and bring photo ID and insurance card.",
        }
        try:
            self.outbox_dir.mkdir(parents=True, exist_ok=True)
            (self.outbox_dir / f"{appointment.appointment_id}.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError:
            return False
        return True

    def get_verified_patient_booking_details(self, call_id: str) -> tuple[str, str | None]:
        patient = self._resolve_verified_patient(call_id)
        return f"{patient.first_name} {patient.last_name}", patient.email

    def book_existing_patient(
        self, call_id: str, *, reason: str, slot_id: str, email: str
    ) -> BookingResult:
        patient = self._resolve_verified_patient(call_id)
        if not reason.strip() or len(reason) > 100:
            raise InvalidStateTransition("A brief appointment reason is required")
        if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise InvalidStateTransition("A valid email address is required")
        now = self.clock.now()
        reason_summary = _visit_summary(reason)
        request = PatientRequest(
            request_id=str(uuid4()),
            call_id=call_id,
            patient_id=patient.patient_id,
            request_type="booking",
            created_at=now,
            masked_summary=f"Appointment booking: {reason_summary}",
            status="open",
        )
        event = AuditEvent(
            audit_id=str(uuid4()),
            call_id=call_id,
            actor="caller",
            record_id=patient.patient_id,
            timestamp=now,
            action="existing_patient_appointment_booked",
            outcome="success",
        )
        try:
            appointment = self.appointment_repository.book_existing_patient(
                patient_id=patient.patient_id,
                call_id=call_id,
                slot_id=slot_id,
                email=email,
                request=request,
                event=event,
            )
        except sqlite3.IntegrityError as exc:
            raise InvalidStateTransition(
                "That appointment time is no longer available. Please choose another."
            ) from exc
        except sqlite3.Error as exc:
            raise PersistenceFailure("The appointment could not be saved") from exc
        email_saved = self._write_confirmation_email(
            appointment, email, f"{patient.first_name} {patient.last_name}"
        )
        return BookingResult(
            patient_id=patient.patient_id,
            appointment=AppointmentSummary(
                start_at=_local_datetime(appointment.start_at),
                doctor_name=appointment.doctor_name,
            ),
            email_confirmation_saved=email_saved,
        )

    def get_next_appointment(self, call_id: str) -> AppointmentLookupResult:
        try:
            patient = self._resolve_verified_patient(call_id)
            self._record_audit(
                call_id, "appointment_lookup", "success", record_id=patient.patient_id
            )
            now = _local_datetime(self.clock.now())
            appointments = [
                appointment
                for appointment in self.appointment_repository.list_for_patient(patient.patient_id)
                if appointment.status == "scheduled"
                and _local_datetime(appointment.start_at) >= now
            ]
            if not appointments:
                return AppointmentLookupResult(outcome="no_upcoming_appointment")
            appointment = min(appointments, key=lambda item: item.start_at)
            return AppointmentLookupResult(
                outcome="available",
                appointment=AppointmentSummary(
                    start_at=_local_datetime(appointment.start_at),
                    doctor_name=appointment.doctor_name,
                ),
            )
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def get_lab_status(self, call_id: str) -> LabStatusResult:
        try:
            patient = self._resolve_verified_patient(call_id)
            self._record_audit(
                call_id, "lab_status_lookup", "success", record_id=patient.patient_id
            )
            return LabStatusResult(status=patient.lab_results_status)
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def get_balance(self, call_id: str) -> BalanceResult:
        try:
            patient = self._resolve_verified_patient(call_id)
            self._record_audit(call_id, "balance_lookup", "success", record_id=patient.patient_id)
            return BalanceResult(amount=Decimal(str(patient.balance_due)))
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def prepare_refill(
        self,
        call_id: str,
        medication_name: str,
        pharmacy: str | None = None,
    ) -> RefillResult:
        try:
            patient = self._resolve_verified_patient(call_id)
            matches = _match_medications(patient, medication_name)
            if not matches:
                self._record_audit(
                    call_id, "refill_lookup", "failure", record_id=patient.patient_id
                )
                return RefillResult(outcome="medication_not_found")
            if len(matches) > 1:
                self._record_audit(
                    call_id, "refill_lookup", "failure", record_id=patient.patient_id
                )
                return RefillResult(outcome="medication_ambiguous")

            medication = matches[0]
            if pharmacy and _normalized_text(pharmacy) != _normalized_text(medication.pharmacy):
                self._record_audit(
                    call_id, "refill_lookup", "failure", record_id=patient.patient_id
                )
                return RefillResult(
                    outcome="pharmacy_mismatch",
                    medication_name=medication.name,
                    pharmacy=medication.pharmacy,
                    refills_remaining=medication.refills_remaining,
                )

            token = secrets.token_urlsafe(32)
            now = self.clock.now()
            session = self.ensure_open_call(call_id)
            self.session_repository.save(
                session.model_copy(
                    update={
                        "pending_refill_token_digest": _confirmation_digest(token),
                        "pending_refill_medication": medication.name,
                        "pending_refill_pharmacy": medication.pharmacy,
                        "pending_refill_expires_at": now + _PENDING_REFILL_LIFETIME,
                        "updated_at": now,
                    }
                )
            )
            self._record_audit(call_id, "refill_preview", "success", record_id=patient.patient_id)
            return RefillResult(
                outcome="confirmation_required",
                medication_name=medication.name,
                pharmacy=medication.pharmacy,
                refills_remaining=medication.refills_remaining,
                confirmation_token=token,
            )
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def confirm_refill(self, call_id: str, confirmation_token: str) -> RefillResult:
        try:
            patient = self._resolve_verified_patient(call_id)
            session = self.session_repository.get(call_id)
            now = self.clock.now()
            if (
                session is None
                or session.pending_refill_token_digest is None
                or session.pending_refill_medication is None
                or session.pending_refill_pharmacy is None
                or session.pending_refill_expires_at is None
                or session.pending_refill_expires_at < now
                or not hmac.compare_digest(
                    session.pending_refill_token_digest,
                    _confirmation_digest(confirmation_token),
                )
            ):
                raise InvalidStateTransition("There is no current refill awaiting confirmation")

            medication = next(
                (
                    item
                    for item in patient.medications
                    if item.name == session.pending_refill_medication
                ),
                None,
            )
            if medication is None or medication.pharmacy != session.pending_refill_pharmacy:
                raise InvalidStateTransition("The refill details are no longer available")

            request = PatientRequest(
                request_id=str(uuid4()),
                call_id=call_id,
                patient_id=patient.patient_id,
                request_type="refill",
                created_at=now,
                masked_summary="Refill request",
                status="open",
                outcome=(
                    "pending" if medication.refills_remaining > 0 else "needs_doctor_approval"
                ),
                medication_name=medication.name,
                pharmacy=medication.pharmacy,
            )
            event = AuditEvent(
                audit_id=str(uuid4()),
                call_id=call_id,
                actor="caller",
                record_id=request.request_id,
                timestamp=now,
                action="refill_request_recorded",
                outcome="success",
            )
            stored, duplicate = self.request_repository.create_refill_with_audit(
                request,
                event,
                session.pending_refill_token_digest,
            )
            outcome: Literal["duplicate_pending", "recorded", "needs_doctor_approval"]
            if duplicate:
                outcome = "duplicate_pending"
            elif stored.outcome == "pending":
                outcome = "recorded"
            else:
                outcome = "needs_doctor_approval"
            return RefillResult(
                outcome=outcome,
                medication_name=stored.medication_name,
                pharmacy=stored.pharmacy,
                refills_remaining=medication.refills_remaining,
                request_id=stored.request_id,
                request_outcome=stored.outcome,
            )
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def record_after_hours_callback(
        self, call_id: str, *, name: str, phone: str, reason: str
    ) -> str:
        """Persist the minimum callback details without linking to a patient record."""
        try:
            session = self._get_active_session(call_id)
            if session.mode != CallMode.CLOSED:
                raise InvalidStateTransition("After-hours messages are only accepted after hours")
            clean_name = " ".join(name.split())[:200]
            clean_phone = re.sub(r"[^0-9+]", "", phone)[:30]
            if len(clean_name.split()) < 2:
                raise InvalidStateTransition("A full callback name is required")
            if len(re.sub(r"\D", "", clean_phone)) not in {10, 11}:
                raise InvalidStateTransition("A valid callback number is required")
            request = PatientRequest(
                request_id=str(uuid4()),
                call_id=call_id,
                patient_id=None,
                request_type="callback",
                created_at=self.clock.now(),
                masked_summary=_callback_summary(reason),
                status="open",
                callback_name=clean_name,
                callback_phone=clean_phone,
            )
            event = AuditEvent(
                audit_id=str(uuid4()),
                call_id=call_id,
                actor="caller",
                record_id=request.request_id,
                timestamp=self.clock.now(),
                action="after_hours_callback_recorded",
                outcome="success",
            )
            self.request_repository.save_with_audit(request, event)
            return request.request_id
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def record_emergency(self, call_id: str) -> None:
        """Audit that the caller was redirected to 911. No words or details are stored."""
        self._record_audit(call_id, "emergency_redirected", "success")

    def request_callback(
        self,
        call_id: str,
        *,
        reason: str,
        name: str | None = None,
        phone: str | None = None,
    ) -> str:
        """Open-hours staff callback. Verified callers are linked to their record; anyone else
        must leave a name and number, stored without a patient link."""
        session = self.ensure_open_call(call_id)
        patient_id = session.verified_patient_id
        clean_name = " ".join((name or "").split())[:200]
        clean_phone = re.sub(r"\D", "", phone or "")[-10:]
        if patient_id is None and (len(clean_name.split()) < 2 or len(clean_phone) != 10):
            raise InvalidStateTransition("A full name and callback number are required")
        now = self.clock.now()
        request = PatientRequest(
            request_id=str(uuid4()),
            call_id=call_id,
            patient_id=patient_id,
            request_type="callback",
            created_at=now,
            masked_summary=_callback_summary(reason),
            status="open",
            callback_name=None if patient_id else clean_name,
            callback_phone=None if patient_id else clean_phone,
        )
        event = AuditEvent(
            audit_id=str(uuid4()),
            call_id=call_id,
            actor="caller",
            record_id=request.request_id,
            timestamp=now,
            action="staff_callback_requested",
            outcome="success",
        )
        try:
            self.request_repository.save_with_audit(request, event)
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc
        return request.request_id

    def list_medication_names(self, call_id: str) -> list[str]:
        """Medication names only (minimum necessary), for a caller who can't recall one."""
        try:
            patient = self._resolve_verified_patient(call_id)
            self._record_audit(
                call_id, "medication_names_lookup", "success", record_id=patient.patient_id
            )
            return [medication.name for medication in patient.medications]
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def record_doctor_message(self, call_id: str) -> str:
        """Create a minimal doctor-follow-up request after successful verification."""
        try:
            patient = self._resolve_verified_patient(call_id)
            request = PatientRequest(
                request_id=str(uuid4()),
                call_id=call_id,
                patient_id=patient.patient_id,
                request_type="message",
                created_at=self.clock.now(),
                masked_summary="Caller requested doctor follow-up",
                status="open",
            )
            event = AuditEvent(
                audit_id=str(uuid4()),
                call_id=call_id,
                actor="caller",
                record_id=request.request_id,
                timestamp=self.clock.now(),
                action="doctor_follow_up_requested",
                outcome="success",
            )
            self.request_repository.save_with_audit(request, event)
            return request.request_id
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def request_staff_assistance(self, call_id: str) -> str:
        try:
            session = self._get_active_session(call_id)
            request = PatientRequest(
                request_id=str(uuid4()),
                call_id=call_id,
                patient_id=session.verified_patient_id,
                request_type="transfer",
                created_at=self.clock.now(),
                masked_summary="Staff assistance requested",
                status="open",
            )
            event = AuditEvent(
                audit_id=str(uuid4()),
                call_id=call_id,
                actor="caller",
                record_id=request.request_id,
                timestamp=self.clock.now(),
                action="staff_assistance_requested",
                outcome="success",
            )
            self.request_repository.save_with_audit(request, event)
            return "Staff assistance request recorded."
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc

    def _resolve_verified_patient(self, call_id: str) -> Patient:
        session = self.ensure_open_call(call_id)
        if session.verified_patient_id is None:
            raise UnauthorizedPatientAccess("Patient access requires a verified session")
        patient = self.patient_repository.get(session.verified_patient_id)
        if patient is None:
            raise PatientRecordUnavailable("The verified patient record is unavailable")
        return patient

    def _get_active_session(self, call_id: str) -> CallSession:
        session = self.session_repository.get(call_id)
        if session is None or session.status == SessionStatus.CLOSED:
            raise UnknownCallSession("The call session is unavailable")
        return session

    def _record_audit(
        self,
        call_id: str,
        action: str,
        outcome: str,
        *,
        record_id: str | None = None,
    ) -> None:
        try:
            self.audit_logger.record(
                call_id=call_id,
                action=action,
                outcome=outcome,
                record_id=record_id,
                timestamp=self.clock.now(),
            )
        except sqlite3.Error as exc:
            raise PersistenceFailure("Clinic service is temporarily unavailable") from exc


def _callback_summary(reason: str) -> str:
    """Store a category, never the caller's own words (they may contain health details)."""
    lowered = reason.casefold()
    categories = (
        (("appointment", "schedul", "booking", "reschedul"), "Scheduling callback requested"),
        (("refill", "prescription", "medication"), "Prescription callback requested"),
        (("bill", "balance", "payment"), "Billing callback requested"),
        (("lab", "test result"), "Lab-status callback requested"),
        (_CLINICAL_WORDS, "Clinical question callback"),
    )
    for words, summary in categories:
        if any(word in lowered for word in words):
            return summary
    return "General callback requested"


_CLINICAL_WORDS = (
    "medical", "doctor", "symptom", "health", "advice", "nurse", "pain", "ache", "fever",
    "sick", "dizz", "cough", "rash", "medicine",
)  # fmt: skip


def _visit_summary(reason: str) -> str:
    """Store a visit category, never the caller's own words."""
    lowered = reason.casefold()
    if "follow" in lowered:
        return "Follow-up visit"
    if "annual" in lowered or "physical" in lowered:
        return "Annual check-up"
    if "check" in lowered:
        return "Check-up"
    return "General appointment"


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _match_medications(patient: Patient, query: str) -> list[Medication]:
    """Match what the caller said to their own medications.

    Accepts spelled-out names ("l i s i n o p r i l"), dosage words, and small speech-to-text
    misspellings (up to two edits in names of six letters or more).
    """
    query_tokens = _medication_tokens(query) - _MEDICATION_FILLER
    if not query_tokens:
        return []
    matches = []
    for medication in patient.medications:
        known = _medication_tokens(medication.name)
        if all(any(_similar(token, name) for name in known) for token in query_tokens):
            matches.append(medication)
    return matches


_MEDICATION_FILLER = {
    "mg", "milligram", "milligrams", "mcg", "micrograms", "my", "the", "a", "one",
    "for", "please", "refill", "medication", "medicine", "pill", "pills", "tablet", "tablets",
}  # fmt: skip


def _medication_tokens(value: str) -> set[str]:
    """Words of a medication name; a run of 3+ single letters is a spelled-out word."""
    tokens: list[str] = []
    letters: list[str] = []
    for word in [*_normalized_text(value).split(), ""]:
        if len(word) == 1 and word.isalpha():
            letters.append(word)
            continue
        tokens.extend(["".join(letters)] if len(letters) >= 3 else letters)
        letters = []
        if word:
            tokens.append(word)
    return {re.sub(r"^(\d+)(mg|mcg)$", r"\1", token) for token in tokens}


def _similar(said: str, known: str) -> bool:
    if said == known:
        return True
    if len(known) < 6 or not said.isalpha():
        return False
    return _edit_distance(said, known) <= 2


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left_char != right_char)
                )
            )
        previous = current
    return previous[-1]


def _confirmation_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_LOCAL_TIMEZONE)
    return value.astimezone(_LOCAL_TIMEZONE)
