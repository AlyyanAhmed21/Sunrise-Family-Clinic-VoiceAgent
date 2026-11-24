from datetime import datetime

from clinic.models import AvailableSlot


def filter_slots(
    slots: list[AvailableSlot],
    doctor_name: str | None = None,
) -> list[AvailableSlot]:
    filtered = slots
    if doctor_name is not None:
        filtered = [slot for slot in filtered if slot.doctor_name == doctor_name]
    return sorted(filtered, key=lambda slot: slot.start_at)[:3]


def slot_is_past(slot: AvailableSlot, now: datetime) -> bool:
    return slot.start_at <= now
