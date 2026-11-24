from clinic.domain.errors import VerificationLocked
from clinic.models import CallSession, VerificationCandidate, VerificationResult
from clinic.persistence.repositories import PatientRepository, SessionRepository
from clinic.security.hashing import verify_last4
from clinic.security.parsing import names_match

GENERIC_FAILURE = (
    "We could not verify those details. Please contact the clinic staff for assistance."
)


def verify_candidate(
    candidate: VerificationCandidate,
    *,
    session: CallSession,
    patient_repository: PatientRepository,
    session_repository: SessionRepository,
    pepper: str,
) -> VerificationResult:
    if session.status == "locked" or session.failed_attempts >= 3:
        raise VerificationLocked(GENERIC_FAILURE)
    matched_patient_id: str | None = None
    for patient in patient_repository.list_all():
        record = patient_repository.get_verification_record(patient.patient_id)
        if record is None:
            continue
        salt, digest = record
        if (
            names_match(candidate.full_name, f"{patient.first_name} {patient.last_name}")
            and candidate.dob == patient.dob
            and verify_last4(candidate.last_four, salt, digest, pepper)
        ):
            matched_patient_id = patient.patient_id
            break
    if matched_patient_id is not None:
        verified = session.model_copy(
            update={
                "verified_patient_id": matched_patient_id,
                "failed_attempts": 0,
                "status": "open",
            }
        )
        session_repository.save(verified)
        return VerificationResult(
            outcome="verified",
            verified_patient_id=matched_patient_id,
            failed_attempts=0,
        )
    failed_attempts = session.failed_attempts + 1
    if failed_attempts >= 3:
        locked = session.model_copy(
            update={"failed_attempts": 3, "status": "locked", "verified_patient_id": None}
        )
        session_repository.save(locked)
        return VerificationResult(outcome="locked_out", failed_attempts=3)
    retried = session.model_copy(update={"failed_attempts": failed_attempts})
    session_repository.save(retried)
    return VerificationResult(outcome="failed", failed_attempts=failed_attempts)
