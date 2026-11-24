from clinic.models import Medication


def prepare_refill(medication: Medication) -> tuple[str, bool]:
    if medication.refills_remaining == 0:
        return "doctor approval required", False
    return "refill request requires confirmation", True
