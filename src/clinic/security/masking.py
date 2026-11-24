import re

DOB_PATTERN = re.compile(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
LAST4_PATTERN = re.compile(r"\blast[- ]?four(?: digits)?\s*(?:is|are|[:=])?\s*[0-9 -]{4,10}", re.I)
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MEMBER_PATTERN = re.compile(
    r"\b(?:member|insurance|subscriber)(?: id)?[: ]+[A-Za-z0-9-]{4,30}", re.I
)


def mask_text(value: str) -> str:
    masked = SSN_PATTERN.sub("[REDACTED_SSN]", value)
    masked = LAST4_PATTERN.sub("[REDACTED_LAST4]", masked)
    masked = DOB_PATTERN.sub("[REDACTED_DOB]", masked)
    masked = PHONE_PATTERN.sub("[REDACTED_PHONE]", masked)
    masked = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", masked)
    return MEMBER_PATTERN.sub("[REDACTED_MEMBER_ID]", masked)
