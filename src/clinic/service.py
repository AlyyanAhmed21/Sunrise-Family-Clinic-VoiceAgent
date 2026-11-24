from clinic.domain.errors import UnauthorizedPatientAccess
from clinic.models import Patient
from clinic.persistence.repositories import PatientRepository, SessionRepository


class ClinicService:
    """Step 1 skeleton: later stages add workflows; identity remains call-scoped."""

    def __init__(
        self,
        patient_repository: PatientRepository,
        session_repository: SessionRepository,
    ) -> None:
        self.patient_repository = patient_repository
        self.session_repository = session_repository

    def get_verified_patient(self, call_id: str) -> Patient:
        session = self.session_repository.get(call_id)
        if session is None or session.status != "open" or session.verified_patient_id is None:
            raise UnauthorizedPatientAccess("Patient access requires a verified session")
        patient = self.patient_repository.get(session.verified_patient_id)
        if patient is None:
            raise UnauthorizedPatientAccess("Verified patient record is unavailable")
        return patient
