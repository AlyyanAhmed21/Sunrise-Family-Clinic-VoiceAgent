from datetime import datetime

from clinic.domain.hours import is_open


def test_office_hours_boundaries() -> None:
    assert not is_open(datetime(2026, 11, 30, 8, 59))
    assert is_open(datetime(2026, 11, 30, 9, 0))
    assert is_open(datetime(2026, 11, 30, 16, 59))
    assert not is_open(datetime(2026, 11, 30, 17, 0))
    assert not is_open(datetime(2026, 12, 5, 12, 0))
