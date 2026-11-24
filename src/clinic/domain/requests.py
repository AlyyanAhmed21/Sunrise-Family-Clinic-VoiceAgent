from datetime import datetime
from uuid import uuid4

from clinic.models import PatientRequest
from clinic.security.masking import mask_text


def build_request(
    *,
    call_id: str,
    patient_id: str | None,
    request_type: str,
    summary: str,
    created_at: datetime,
) -> PatientRequest:
    allowed = {"refill", "booking", "callback", "message", "transfer"}
    if request_type not in allowed:
        raise ValueError("unsupported patient request type")
    return PatientRequest(
        request_id=str(uuid4()),
        call_id=call_id,
        patient_id=patient_id,
        request_type=request_type,  # type: ignore[arg-type]
        created_at=created_at,
        masked_summary=mask_text(summary),
    )
