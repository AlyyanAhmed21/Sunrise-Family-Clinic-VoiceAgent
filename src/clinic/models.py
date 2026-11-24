from __future__ import annotations

from datetime import date, datetime
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


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: str
    call_id: str
    actor: str = "caller"
    record_id: str | None = None
    timestamp: datetime
    action: str = Field(min_length=1, max_length=100)
    outcome: Literal["success", "failure", "locked"]
