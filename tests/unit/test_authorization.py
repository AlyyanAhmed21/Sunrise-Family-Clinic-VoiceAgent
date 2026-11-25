import pytest

from clinic.domain.errors import UnknownCallSession


def test_unknown_session_cannot_access_patient(clinic_service) -> None:
    with pytest.raises(UnknownCallSession):
        clinic_service.get_lab_status("missing-call")
