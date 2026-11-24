from datetime import date

import pytest
from pydantic import ValidationError

from clinic.models import Medication, Patient, VerificationCandidate


def test_valid_model_construction() -> None:
    medication = Medication(
        name="Test 1mg",
        refills_remaining=1,
        last_filled=date(2026, 1, 1),
        pharmacy="Test Pharmacy",
    )
    patient = Patient(
        patient_id="T001",
        first_name="Test",
        last_name="Patient",
        dob=date(1980, 1, 1),
        phone="555-123-4567",
        medications=(medication,),
        lab_results_status="Pending",
        balance_due=0,
    )
    assert patient.patient_id == "T001"


def test_invalid_verification_last_four() -> None:
    with pytest.raises(ValidationError):
        VerificationCandidate(
            full_name="Test Patient",
            dob=date(1980, 1, 1),
            last_four="12A4",
        )
