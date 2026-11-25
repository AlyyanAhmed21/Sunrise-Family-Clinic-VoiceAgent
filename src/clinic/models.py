from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionStatus(StrEnum):
    OPEN = "open"
    LOCKED = "locked"
    CLOSED = "closed"


class CallMode(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Medication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    refills_remaining: int = Field(ge=0)
    last_filled: date
    pharmacy: str = Field(min_length=1, max_length=200)


class Doctor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    specialty: str = Field(min_length=1, max_length=100)


class Patient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    dob: date
    phone: str = Field(min_length=5, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    insurance: str | None = Field(default=None, max_length=200)
    medications: tuple[Medication, ...] = ()
    next_appointment: str | None = None
    lab_results_status: str = Field(max_length=200)
    balance_due: float = Field(ge=0)


class AvailableSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: str
    doctor_name: str
    start_at: datetime
    available: bool = True


class Appointment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    appointment_id: str
    patient_id: str
    doctor_name: str
    start_at: datetime
    status: Literal["scheduled", "cancelled"] = "scheduled"


class CallSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(min_length=1, max_length=100)
    mode: CallMode
    verified_patient_id: str | None = None
    failed_attempts: int = Field(default=0, ge=0, le=3)
    unparsed_attempts: int = Field(default=0, ge=0)
    status: SessionStatus = SessionStatus.OPEN
    simulated_time: datetime | None = None
    pending_refill_token_digest: str | None = Field(default=None, repr=False)
    pending_refill_medication: str | None = None
    pending_refill_pharmacy: str | None = None
    pending_refill_expires_at: datetime | None = None
    updated_at: datetime


class VerificationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=200)
    dob: date
    last_four: str = Field(min_length=4, max_length=4)

    @field_validator("last_four")
    @classmethod
    def digits_only(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("last four must contain digits")
        return value


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["verified", "failed", "locked_out"]
    verified_patient_id: str | None = None
    failed_attempts: int = Field(ge=0, le=3)


class PatientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    call_id: str
    patient_id: str | None
    request_type: Literal["refill", "booking", "callback", "message", "transfer"]
    created_at: datetime
    masked_summary: str = Field(max_length=500)
    status: Literal["open", "completed", "cancelled"] = "open"
    outcome: Literal["pending", "needs_doctor_approval"] = "pending"
    medication_name: str | None = Field(default=None, max_length=200)
    pharmacy: str | None = Field(default=None, max_length=200)
    callback_name: str | None = Field(default=None, max_length=200)
    callback_phone: str | None = Field(default=None, max_length=30)


class AppointmentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_at: datetime
    doctor_name: str


class AppointmentLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["available", "no_upcoming_appointment"]
    appointment: AppointmentSummary | None = None


class BookingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str
    appointment: AppointmentSummary
    email_confirmation_saved: bool


class LabStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class BalanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(ge=0)


class RefillResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal[
        "confirmation_required",
        "medication_not_found",
        "medication_ambiguous",
        "pharmacy_mismatch",
        "recorded",
        "needs_doctor_approval",
        "duplicate_pending",
    ]
    medication_name: str | None = None
    pharmacy: str | None = None
    refills_remaining: int | None = Field(default=None, ge=0)
    request_id: str | None = None
    request_outcome: Literal["pending", "needs_doctor_approval"] | None = None
    confirmation_token: str | None = Field(default=None, exclude=True, repr=False)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: str
    call_id: str
    actor: str = "caller"
    record_id: str | None = None
    timestamp: datetime
    action: str = Field(min_length=1, max_length=100)
    outcome: Literal["success", "failure", "locked"]
