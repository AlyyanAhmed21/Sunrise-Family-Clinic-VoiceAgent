"""Format values the way a receptionist would say them out loud."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

CLINIC_TZ = ZoneInfo("America/New_York")
_EMAIL_SYMBOLS = {"@": "at", ".": "dot", "-": "dash", "_": "underscore", "+": "plus"}


def clinic_time(value: datetime) -> datetime:
    """Stored times without a zone are clinic (Eastern) times, never the host's local time."""
    return value.astimezone(CLINIC_TZ) if value.tzinfo else value.replace(tzinfo=CLINIC_TZ)


def spoken_date(value: date) -> str:
    return f"{value:%A}, {value:%B} {value.day}"


def spoken_datetime(value: datetime) -> str:
    local = clinic_time(value)
    hour = local.strftime("%I").lstrip("0")
    minutes = "" if local.minute == 0 else f":{local.minute:02d}"
    return f"{spoken_date(local.date())} at {hour}{minutes} {local:%p}"


def spell_email(email: str) -> str:
    """'ann.lee@mail.com' -> 'a, n, n, dot, l, e, e, at, m, a, i, l, dot, c, o, m'."""
    return ", ".join(_EMAIL_SYMBOLS.get(char, char) for char in email.lower())


def spoken_phone(digits: str) -> str:
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}" if len(digits) == 10 else digits


def spoken_money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def upcoming_calendar(today: date, days: int = 14) -> str:
    """A short day list so the model never has to compute weekdays itself."""
    dates = (today + timedelta(days=offset) for offset in range(days))
    return "; ".join(f"{day:%a %b} {day.day}" for day in dates)
