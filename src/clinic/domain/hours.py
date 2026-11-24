from datetime import datetime


def is_open(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    return 9 <= now.hour < 17
