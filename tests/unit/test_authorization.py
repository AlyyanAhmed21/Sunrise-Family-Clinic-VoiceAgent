import pytest

from clinic.domain.errors import UnauthorizedPatientAccess
from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLitePatientRepository, SQLiteSessionRepository
from clinic.service import ClinicService


def test_unverified_session_cannot_access_patient(database: Database) -> None:
    service = ClinicService(
        SQLitePatientRepository(database),
        SQLiteSessionRepository(database),
    )
    with pytest.raises(UnauthorizedPatientAccess):
        service.get_verified_patient("missing-call")
