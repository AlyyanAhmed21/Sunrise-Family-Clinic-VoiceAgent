from datetime import UTC, date, datetime

import pytest

from clinic.domain.errors import VerificationLocked
from clinic.domain.verification import verify_candidate
from clinic.models import CallMode, CallSession, VerificationCandidate
from clinic.persistence.db import Database
from clinic.persistence.repositories import (
    SQLitePatientRepository,
    SQLiteSessionRepository,
)

PEPPER = "deterministic-test-pepper"


def make_session() -> CallSession:
    return CallSession(
        call_id="verify-call",
        mode=CallMode.OPEN,
        updated_at=datetime.now(UTC),
    )


def verify(database: Database, candidate: VerificationCandidate) -> tuple[str, CallSession]:
    patients = SQLitePatientRepository(database)
    sessions = SQLiteSessionRepository(database)
    session = make_session()
    sessions.create(session)
    result = verify_candidate(
        candidate,
        session=session,
        patient_repository=patients,
        session_repository=sessions,
        pepper=PEPPER,
    )
    stored = sessions.get("verify-call")
    assert stored is not None
    return result.outcome, stored


def test_successful_verification(database: Database) -> None:
    outcome, session = verify(
        database,
        VerificationCandidate(full_name="Sarah Johnson", dob=date(1985, 3, 14), last_four="3344"),
    )
    assert outcome == "verified"
    assert session.verified_patient_id == "P001"


@pytest.mark.parametrize(
    ("name", "dob", "last_four"),
    [
        ("Wrong Name", date(1985, 3, 14), "3344"),
        ("Sarah Johnson", date(1985, 3, 15), "3344"),
        ("Sarah Johnson", date(1985, 3, 14), "3345"),
    ],
)
def test_single_field_mismatch_is_generic(
    database: Database, name: str, dob: date, last_four: str
) -> None:
    outcome, session = verify(
        database,
        VerificationCandidate(full_name=name, dob=dob, last_four=last_four),
    )
    assert outcome == "failed"
    assert session.failed_attempts == 1
    assert session.verified_patient_id is None


def test_name_normalization_and_one_edit_tolerance(database: Database) -> None:
    outcome, _ = verify(
        database,
        VerificationCandidate(full_name="SARAH JOHNSON", dob=date(1985, 3, 14), last_four="3344"),
    )
    assert outcome == "verified"


def test_three_failures_lock_out(database: Database) -> None:
    patients = SQLitePatientRepository(database)
    sessions = SQLiteSessionRepository(database)
    session = make_session()
    sessions.create(session)
    candidate = VerificationCandidate(full_name="Nobody", dob=date(2000, 1, 1), last_four="0000")
    outcomes = []
    for _ in range(3):
        current = sessions.get("verify-call")
        assert current is not None
        outcomes.append(
            verify_candidate(
                candidate,
                session=current,
                patient_repository=patients,
                session_repository=sessions,
                pepper=PEPPER,
            )
        )
    assert [item.outcome for item in outcomes] == ["failed", "failed", "locked_out"]
    with pytest.raises(VerificationLocked):
        verify_candidate(
            candidate,
            session=sessions.get("verify-call"),
            patient_repository=patients,
            session_repository=sessions,
            pepper=PEPPER,
        )
