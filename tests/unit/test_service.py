from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from clinic.domain.errors import (
    ClinicClosed,
    InvalidStateTransition,
    UnauthorizedPatientAccess,
    UnknownCallSession,
    VerificationLocked,
)
from clinic.models import CallMode, CallSession, SessionStatus
from clinic.persistence.db import Database
from clinic.persistence.repositories import (
    SQLiteSessionRepository,
)

_NOW = datetime(2026, 11, 2, 10, 0, tzinfo=ZoneInfo("America/New_York"))


def _create_session(
    database: Database,
    call_id: str,
    *,
    patient_id: str | None = None,
    mode: CallMode = CallMode.OPEN,
    status: SessionStatus = SessionStatus.OPEN,
) -> None:
    SQLiteSessionRepository(database).create(
        CallSession(
            call_id=call_id,
            mode=mode,
            verified_patient_id=patient_id,
            status=status,
            updated_at=_NOW,
        )
    )


def test_unknown_unverified_locked_and_closed_sessions_are_denied(
    database: Database, clinic_service
) -> None:
    with pytest.raises(UnknownCallSession):
        clinic_service.get_lab_status("unknown")

    _create_session(database, "unverified")
    with pytest.raises(UnauthorizedPatientAccess):
        clinic_service.get_lab_status("unverified")

    _create_session(database, "locked", patient_id="P001", status=SessionStatus.LOCKED)
    with pytest.raises(VerificationLocked):
        clinic_service.get_lab_status("locked")

    _create_session(database, "closed", patient_id="P001", mode=CallMode.CLOSED)
    with pytest.raises(ClinicClosed):
        clinic_service.get_lab_status("closed")


def test_open_session_returns_only_minimal_patient_service_results(
    database: Database, clinic_service
) -> None:
    _create_session(database, "verified", patient_id="P001")

    appointment = clinic_service.get_next_appointment("verified")
    lab_status = clinic_service.get_lab_status("verified")
    balance = clinic_service.get_balance("verified")

    assert appointment.outcome == "available"
    assert appointment.appointment is not None
    assert appointment.appointment.start_at.date().isoformat() == "2026-12-03"
    assert appointment.appointment.doctor_name == "Dr. Patel"
    assert lab_status.status == "Ready - doctor will call to discuss"
    assert balance.amount == Decimal("45.0")
    assert "patient_id" not in appointment.model_dump()


def test_patient_without_upcoming_appointment_gets_explicit_result(
    database: Database, clinic_service
) -> None:
    _create_session(database, "no-appointment", patient_id="P002")

    result = clinic_service.get_next_appointment("no-appointment")

    assert result.outcome == "no_upcoming_appointment"
    assert result.appointment is None


def test_saturday_fixture_appointment_is_returned_as_stored(
    database: Database, clinic_service
) -> None:
    _create_session(database, "maria", patient_id="P003")

    result = clinic_service.get_next_appointment("maria")

    assert result.outcome == "available"
    assert result.appointment is not None
    assert result.appointment.start_at.date().isoformat() == "2026-11-28"
    assert result.appointment.start_at.weekday() == 5
    assert result.appointment.doctor_name == "Dr. Lee"


def test_service_rejects_access_after_hours_even_if_call_started_open(
    database: Database, clinic_service, clock
) -> None:
    _create_session(database, "late", patient_id="P001")
    clock._now = datetime(2026, 11, 2, 17, 0, tzinfo=ZoneInfo("America/New_York"))

    with pytest.raises(ClinicClosed):
        clinic_service.get_balance("late")


def test_open_hours_callback_links_verified_patient_and_stores_only_a_category(
    database: Database, clinic_service
) -> None:
    _create_session(database, "cb-verified", patient_id="P002")
    _create_session(database, "cb-anonymous")

    clinic_service.request_callback("cb-verified", reason="my chest x-ray bill")
    with pytest.raises(InvalidStateTransition):
        clinic_service.request_callback("cb-anonymous", reason="scheduling")
    clinic_service.request_callback(
        "cb-anonymous", reason="reschedule", name="Ann Lee", phone="555-010-2020"
    )

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT patient_id, masked_summary, callback_phone FROM patient_requests "
            "WHERE request_type = 'callback' ORDER BY patient_id"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (None, "Scheduling callback requested", "5550102020"),
        ("P002", "Billing callback requested", None),
    ]


def test_emergency_redirect_is_audited_without_details(database: Database, clinic_service) -> None:
    _create_session(database, "emergency")

    clinic_service.record_emergency("emergency")

    with database.connect() as connection:
        row = connection.execute(
            "SELECT action, outcome, record_id FROM audit_events WHERE call_id = 'emergency'"
        ).fetchone()
    assert tuple(row) == ("emergency_redirected", "success", None)


def test_medical_question_callback_gets_its_own_category(
    database: Database, clinic_service
) -> None:
    _create_session(database, "medical")

    clinic_service.request_callback(
        "medical", reason="headache question", name="Sam Sampson", phone="124 578 1212"
    )

    with database.connect() as connection:
        summary = connection.execute("SELECT masked_summary FROM patient_requests").fetchone()[0]
    assert summary == "Clinical question callback"


def test_verification_audit_names_the_record_only_on_success(
    database: Database, clinic_service
) -> None:
    from datetime import date

    from clinic.models import VerificationCandidate

    _create_session(database, "audit-ok")
    _create_session(database, "audit-bad")
    good = VerificationCandidate(full_name="Sarah Johnson", dob=date(1985, 3, 14), last_four="3344")
    clinic_service.verify_caller("audit-ok", good)
    clinic_service.verify_caller("audit-bad", good.model_copy(update={"last_four": "0000"}))

    with database.connect() as connection:
        rows = dict(
            connection.execute(
                "SELECT call_id, record_id FROM audit_events WHERE action='identity_verification'"
            ).fetchall()
        )
    assert rows == {"audit-ok": "P001", "audit-bad": None}


def test_medication_names_require_verification_and_return_names_only(
    database: Database, clinic_service
) -> None:
    _create_session(database, "meds-anonymous")
    _create_session(database, "meds", patient_id="P001")

    with pytest.raises(UnauthorizedPatientAccess):
        clinic_service.list_medication_names("meds-anonymous")
    assert clinic_service.list_medication_names("meds") == ["Lisinopril 10mg", "Metformin 500mg"]


def test_close_call_marks_session_closed(database: Database, clinic_service) -> None:
    _create_session(database, "closing")

    clinic_service.close_call("closing")

    with pytest.raises(UnknownCallSession):
        clinic_service.get_lab_status("closing")


def test_refill_requires_one_time_explicit_confirmation_and_masks_request(
    database: Database, clinic_service
) -> None:
    _create_session(database, "refill", patient_id="P001")

    preview = clinic_service.prepare_refill("refill", "lisinopril")
    assert preview.outcome == "confirmation_required"
    assert preview.medication_name == "Lisinopril 10mg"
    assert preview.pharmacy == "CVS Main St"
    assert preview.confirmation_token is not None
    assert preview.confirmation_token not in repr(preview)
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM patient_requests").fetchone()[0] == 0

    with pytest.raises(InvalidStateTransition):
        clinic_service.confirm_refill("refill", "not-the-token")
    assert clinic_service.confirm_refill("refill", preview.confirmation_token).outcome == "recorded"

    with database.connect() as connection:
        request = connection.execute("SELECT * FROM patient_requests").fetchone()
        events = connection.execute(
            "SELECT action, outcome FROM audit_events WHERE call_id = ? ORDER BY timestamp",
            ("refill",),
        ).fetchall()
    assert request["status"] == "open"
    assert request["outcome"] == "pending"
    assert request["medication_name"] == "Lisinopril 10mg"
    assert request["masked_summary"] == "Refill request"
    assert "3344" not in request["masked_summary"]
    assert [row["action"] for row in events] == ["refill_preview", "refill_request_recorded"]


def test_zero_refills_require_doctor_approval_without_claiming_approval(
    database: Database, clinic_service
) -> None:
    _create_session(database, "zero-refills", patient_id="P001")
    preview = clinic_service.prepare_refill("zero-refills", "metformin")
    assert preview.refills_remaining == 0
    assert preview.confirmation_token is not None

    result = clinic_service.confirm_refill("zero-refills", preview.confirmation_token)

    assert result.outcome == "needs_doctor_approval"
    assert result.request_outcome == "needs_doctor_approval"
    with database.connect() as connection:
        stored = connection.execute("SELECT outcome FROM patient_requests").fetchone()
    assert stored["outcome"] == "needs_doctor_approval"
    assert stored["outcome"] != "approved"


def test_refill_matching_is_safe_for_missing_ambiguous_and_wrong_pharmacy(
    database: Database, clinic_service
) -> None:
    _create_session(database, "matching", patient_id="P001")
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO medications (patient_id, name, refills_remaining, last_filled, pharmacy) "
            "VALUES (?, ?, ?, ?, ?)",
            ("P001", "Metformin XR 500mg", 1, "2026-10-01", "CVS Main St"),
        )

    assert clinic_service.prepare_refill("matching", "unknown").outcome == "medication_not_found"
    assert clinic_service.prepare_refill("matching", "metformin").outcome == "medication_ambiguous"
    wrong_pharmacy = clinic_service.prepare_refill("matching", "lisinopril", "Walgreens Oak Ave")
    assert wrong_pharmacy.outcome == "pharmacy_mismatch"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM patient_requests").fetchone()[0] == 0


def test_pending_duplicate_refill_is_idempotent(database: Database, clinic_service) -> None:
    _create_session(database, "first", patient_id="P001")
    _create_session(database, "second", patient_id="P001")
    first = clinic_service.prepare_refill("first", "lisinopril")
    second = clinic_service.prepare_refill("second", "lisinopril")
    assert first.confirmation_token is not None
    assert second.confirmation_token is not None

    assert clinic_service.confirm_refill("first", first.confirmation_token).outcome == "recorded"
    duplicate = clinic_service.confirm_refill("second", second.confirmation_token)

    assert duplicate.outcome == "duplicate_pending"
    assert duplicate.request_id is not None
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM patient_requests").fetchone()[0] == 1
        actions = connection.execute(
            "SELECT action FROM audit_events WHERE action LIKE 'refill_request_%'"
        ).fetchall()
    assert [row["action"] for row in actions] == [
        "refill_request_recorded",
        "refill_request_duplicate",
    ]


def test_audit_and_request_records_exclude_sensitive_values(
    database: Database, clinic_service
) -> None:
    _create_session(database, "audit-safe", patient_id="P001")
    preview = clinic_service.prepare_refill("audit-safe", "lisinopril")
    assert preview.confirmation_token is not None
    clinic_service.confirm_refill("audit-safe", preview.confirmation_token)

    with database.connect() as connection:
        request_summaries = connection.execute(
            "SELECT masked_summary FROM patient_requests"
        ).fetchall()
        audit_rows = connection.execute(
            "SELECT action, record_id FROM audit_events WHERE call_id = ?",
            ("audit-safe",),
        ).fetchall()
    rendered = repr(request_summaries) + repr(audit_rows)
    assert "1985-03-14" not in rendered
    assert "3344" not in rendered
    assert "Sarah" not in rendered


def test_staff_assistance_request_links_verified_patient_without_details(
    database: Database, clinic_service
) -> None:
    _create_session(database, "staff", patient_id="P001")

    clinic_service.request_staff_assistance("staff")

    with database.connect() as connection:
        request = connection.execute("SELECT * FROM patient_requests").fetchone()
    assert request["request_type"] == "transfer"
    assert request["patient_id"] == "P001"
    assert request["subject_reference"] == "P001"
    assert request["masked_summary"] == "Staff assistance requested"


def test_after_hours_callback_is_saved_without_patient_link(database, clinic_service, clock):
    from clinic.models import CallMode, CallSession

    clinic_service.session_repository.create(
        CallSession(
            call_id="after-hours-callback",
            mode=CallMode.CLOSED,
            verified_patient_id="P001",
            updated_at=clock.now(),
        )
    )
    request_id = clinic_service.record_after_hours_callback(
        "after-hours-callback",
        name="Alex Morgan",
        phone="555-010-2020",
        reason="I need to schedule an appointment",
    )
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM patient_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
    assert row is not None
    assert row["patient_id"] is None
    assert row["subject_reference"] == "UNVERIFIED"
    assert row["request_type"] == "callback"
    assert row["callback_name"] == "Alex Morgan"
    assert row["callback_phone"] == "5550102020"
    assert row["masked_summary"] == "Scheduling callback requested"


def test_after_hours_callback_rejects_open_session(database, clinic_service, clock):
    from clinic.domain.errors import InvalidStateTransition
    from clinic.models import CallMode, CallSession

    clinic_service.session_repository.create(
        CallSession(
            call_id="open-callback",
            mode=CallMode.OPEN,
            updated_at=clock.now(),
        )
    )
    with pytest.raises(InvalidStateTransition):
        clinic_service.record_after_hours_callback(
            "open-callback", name="Alex Morgan", phone="5550102020", reason="appointment"
        )


def test_new_patient_booking_consumes_slot_and_creates_records(
    database, clinic_service, clock, tmp_path
):
    from datetime import date

    from clinic.models import CallMode, CallSession

    clinic_service.session_repository.create(
        CallSession(
            call_id="new-booking",
            mode=CallMode.OPEN,
            updated_at=clock.now(),
        )
    )
    slots = clinic_service.list_available_slots("new-booking")
    selected = next(slot for slot in slots if slot.doctor_name == "Dr. Patel")
    result = clinic_service.book_new_patient(
        "new-booking",
        full_name="Alex Morgan",
        dob=date(1994, 6, 18),
        phone="5550102020",
        email="alex.morgan@example.com",
        insurance="self-pay",
        reason="annual check-up",
        slot_id=selected.slot_id,
    )
    assert result.patient_id.startswith("NEW-")
    assert result.appointment.doctor_name == "Dr. Patel"
    assert result.email_confirmation_saved
    with database.connect() as connection:
        patient = connection.execute(
            "SELECT verification_ready, email, insurance FROM patients WHERE patient_id = ?",
            (result.patient_id,),
        ).fetchone()
        slot = connection.execute(
            "SELECT available FROM available_slots WHERE slot_id = ?", (selected.slot_id,)
        ).fetchone()
        request = connection.execute(
            "SELECT request_type, patient_id, subject_reference FROM patient_requests "
            "WHERE patient_id = ?",
            (result.patient_id,),
        ).fetchone()
    assert patient["verification_ready"] == 0
    assert patient["email"] == "alex.morgan@example.com"
    assert patient["insurance"] == "self-pay"
    assert slot["available"] == 0
    assert request["request_type"] == "booking"
    assert request["patient_id"] == result.patient_id
    assert request["subject_reference"] == result.patient_id
    assert list(clinic_service.outbox_dir.glob("*.json"))
    assert clinic_service.outbox_dir.is_relative_to(tmp_path)  # never the demo outbox


def test_verified_existing_patient_can_book_without_recollecting_details(
    database, clinic_service, clock
):
    from clinic.models import CallMode, CallSession

    clinic_service.session_repository.create(
        CallSession(
            call_id="existing-booking",
            mode=CallMode.OPEN,
            verified_patient_id="P001",
            updated_at=clock.now(),
        )
    )
    selected = clinic_service.list_available_slots("existing-booking")[0]
    result = clinic_service.book_existing_patient(
        "existing-booking",
        reason="follow-up",
        slot_id=selected.slot_id,
        email="sarah@example.com",
    )
    assert result.patient_id == "P001"
    assert result.appointment.doctor_name == selected.doctor_name
    assert result.email_confirmation_saved
    with database.connect() as connection:
        slot = connection.execute(
            "SELECT available FROM available_slots WHERE slot_id = ?", (selected.slot_id,)
        ).fetchone()
    assert slot["available"] == 0


def test_doctor_follow_up_message_is_minimal_and_requires_verified_patient(
    database, clinic_service, clock
):
    from clinic.domain.errors import UnauthorizedPatientAccess
    from clinic.models import CallMode, CallSession

    clinic_service.session_repository.create(
        CallSession(
            call_id="doctor-message",
            mode=CallMode.OPEN,
            verified_patient_id="P001",
            updated_at=clock.now(),
        )
    )
    request_id = clinic_service.record_doctor_message("doctor-message")
    with database.connect() as connection:
        row = connection.execute(
            "SELECT patient_id, request_type, masked_summary FROM patient_requests "
            "WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    assert row["patient_id"] == "P001"
    assert row["request_type"] == "message"
    assert row["masked_summary"] == "Caller requested doctor follow-up"

    clinic_service.session_repository.create(
        CallSession(call_id="unverified-message", mode=CallMode.OPEN, updated_at=clock.now())
    )
    with pytest.raises(UnauthorizedPatientAccess):
        clinic_service.record_doctor_message("unverified-message")
