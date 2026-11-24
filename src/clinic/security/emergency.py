import re

EMERGENCY_TERMS = (
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "suicide",
    "stroke",
    "unconscious",
    "severe bleeding",
    "overdose",
    "heart attack",
)


def detect_emergency(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return any(term in normalized for term in EMERGENCY_TERMS)
