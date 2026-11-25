"""Deterministic emergency detection, run on every caller turn before the LLM.

Patterns allow the ways people actually say things ("pain in my chest", "difficulty to
breathe"), not just fixed phrases. False positives are accepted: a needless 911 prompt is
far cheaper than a missed emergency. A negation just before a match ("I don't have chest
pain") suppresses that match.
"""

import re

_NEAR = r"[^.?!]{0,25}?"
EMERGENCY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        # chest pain / pressure, either word order
        rf"\bchest\b{_NEAR}\b(?:pains?|hurts?|hurting|pressure|tight\w*|crushing|aching|ache)\b",
        rf"\b(?:pains?|pressure|tightness|crushing|hurts?|hurting)\b{_NEAR}\bchest\b",
        r"\bheart attack\b",
        # breathing
        rf"\b(?:can'?t|cannot|can not|unable to|hard to|trouble|difficult\w*|struggling to|"
        rf"struggle to)\b{_NEAR}\bbreath\w*",
        r"\bshort(?:ness)? of breath\b|\bnot breathing\b|\bgasping\b|\bchoking\b",
        # neurological / consciousness
        r"\bstroke\b|\bface (?:is )?drooping\b|\bslurred speech\b|\bseizure\w*\b",
        r"\bunconscious\b|\bunresponsive\b|\bpassed out\b|\bwon'?t wake up\b",
        # bleeding, poisoning, overdose, allergy
        r"\b(?:severe|heavy|uncontrolled) bleeding\b|\bbleeding (?:a lot|heavily|badly)\b|"
        r"\bwon'?t stop bleeding\b",
        r"\bpoison\w*\b(?! (?:ivy|oak|sumac))|\boverdos\w*\b",
        r"\b(?:throat|tongue) (?:is )?(?:swelling|closing)\b|\banaphyla\w*\b",
        # self-harm
        r"\bsuicid\w*\b|\bkill (?:myself|himself|herself)\b|\bwant to die\b|"
        r"\bend my life\b|\bhurt myself\b",
        r"\bemergency\b",
    )
)
_NEGATED = re.compile(
    r"\b(?:no|not|without|never|don'?t|do not|doesn'?t|isn'?t|aren'?t|wasn'?t)"
    r"(?:\s+(?:have|having|had|experiencing|feel|feeling|an|any|a))?\s*$"
)


def detect_emergency(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold().replace("’", "'")).strip()
    for pattern in EMERGENCY_PATTERNS:
        for match in pattern.finditer(normalized):
            prefix = normalized[max(0, match.start() - 40) : match.start()]
            if not _NEGATED.search(prefix):
                return True
    return False
