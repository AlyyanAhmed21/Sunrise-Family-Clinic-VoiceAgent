import re

DOB_PATTERN = re.compile(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})\b")
NAMED_DOB_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?(?:,?\s+)\d{4}\b",
    re.I,
)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
LAST4_PATTERN = re.compile(r"\blast[- ]?four(?: digits)?\s*(?:is|are|[:=])?\s*[0-9 -]{4,10}", re.I)
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
RAW_PHONE_PATTERN = re.compile(r"\b(?:\+?1)?\d{10}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SPOKEN_DOB_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?:the\s+)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
    r"nineteenth|twentieth|twenty[- ]first|twenty[- ]second|twenty[- ]third|twenty[- ]fourth|"
    r"twenty[- ]fifth|twenty[- ]sixth|twenty[- ]seventh|twenty[- ]eighth|twenty[- ]ninth|"
    r"thirtieth|thirty[- ]first|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
    r"\s+(?:nineteen|twenty)[ -](?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"zero|one|two|three|four|five|six|seven|eight|nine)(?:[ -](?:zero|one|two|three|four|"
    r"five|six|seven|eight|nine))?\b",
    re.I,
)
SPOKEN_LAST4_PATTERN = re.compile(
    r"\blast\s*(?:four|4)(?:\s+digits?)?\s*(?:is|are|:|=)?\s*"
    r"(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|double)\s*){4,8}\b",
    re.I,
)
SPOKEN_PHONE_PATTERN = re.compile(
    r"\b(?:(?:phone(?: number)?|callback number|call me at)\s*(?:is|at|:)?\s*)?"
    r"(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)\s*){10,12}\b",
    re.I,
)
SPOKEN_EMAIL_PATTERN = re.compile(
    r"\b(?:(?:email(?: address)?)\s*(?:is|:)?\s*)?"
    r"[a-z0-9]+(?:\s+(?:dot|underscore|dash)\s+[a-z0-9]+)+"
    r"\s+at\s+[a-z0-9]+(?:\s+dot\s+[a-z0-9]+)+\b",
    re.I,
)
SPOKEN_SSN_PATTERN = re.compile(
    r"\b(?:(?:social security(?: number)?|ssn)\s*(?:is|:)?\s*)?"
    r"(?:(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)\s*){9}\b",
    re.I,
)
MEMBER_PATTERN = re.compile(
    r"\b(?:member|insurance|subscriber)(?: id)?[: ]+[A-Za-z0-9-]{4,30}", re.I
)


def mask_text(value: str) -> str:
    """Mask identifiers with fast, deterministic patterns (safe to run on every log line)."""
    masked = value
    masked = SSN_PATTERN.sub("[REDACTED_SSN]", masked)
    masked = SPOKEN_LAST4_PATTERN.sub("[REDACTED_LAST4]", masked)
    masked = SPOKEN_SSN_PATTERN.sub("[REDACTED_SSN]", masked)
    masked = SPOKEN_PHONE_PATTERN.sub("[REDACTED_PHONE]", masked)
    masked = SPOKEN_EMAIL_PATTERN.sub("[REDACTED_EMAIL]", masked)
    masked = LAST4_PATTERN.sub("[REDACTED_LAST4]", masked)
    masked = SPOKEN_DOB_PATTERN.sub("[REDACTED_DOB]", masked)
    masked = NAMED_DOB_PATTERN.sub("[REDACTED_DOB]", masked)
    masked = DOB_PATTERN.sub("[REDACTED_DOB]", masked)
    masked = PHONE_PATTERN.sub("[REDACTED_PHONE]", masked)
    masked = RAW_PHONE_PATTERN.sub("[REDACTED_PHONE]", masked)
    masked = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", masked)
    return MEMBER_PATTERN.sub("[REDACTED_MEMBER_ID]", masked)
