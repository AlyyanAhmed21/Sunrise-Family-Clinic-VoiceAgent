import re
from datetime import date


def normalize_name(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"[^\w\s'-]", " ", value, flags=re.UNICODE)
    words = cleaned.lower().replace("'", "").split()
    return tuple(word for word in words if word not in {"mr", "mrs", "ms", "dr"})


def parse_last_four(value: str) -> str | None:
    text = value.lower().replace("oh", "0")
    if "last four" in text:
        text = text.split("last four", 1)[1]
    text = text.replace("double zero", "00").replace("double one", "11")
    text = text.replace("double two", "22").replace("double three", "33")
    text = text.replace("double four", "44").replace("double five", "55")
    text = text.replace("double six", "66").replace("double seven", "77")
    text = text.replace("double eight", "88").replace("double nine", "99")
    words = {
        "zero": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "nine": "9",
    }
    for word, digit in words.items():
        text = re.sub(rf"\b{word}\b", digit, text)
    digits = re.sub(r"\D", "", text)
    if len(digits) != 4:
        return None
    return digits


def parse_dob(value: str) -> date | None:
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    named_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+(?:the\s+)?"
        r"(\d{1,2})(?:st|nd|rd|th)?(?:,\s*|\s+)(\d{4})\b",
        value.lower(),
    )
    if named_match:
        try:
            month = months[named_match.group(1)]
            return date(int(named_match.group(3)), month, int(named_match.group(2)))
        except ValueError:
            return None
    match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", value)
    if match:
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            return None
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", value)
    if match:
        try:
            month, day, year = (int(part) for part in match.groups())
            return date(year, month, day)
        except ValueError:
            return None
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", value)
    if year_match:
        return date(int(year_match.group(1)), 1, 1)
    spoken_year = re.search(
        r"\b(nineteen|twenty)\s+(?:([a-z]+)\s+)?([a-z]+)\b",
        value.lower(),
    )
    if spoken_year:
        words = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
        }
        tens = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }
        century = 1900 if spoken_year.group(1) == "nineteen" else 2000
        middle = spoken_year.group(2)
        final = spoken_year.group(3)
        if middle in tens:
            year = century + tens[middle] + words.get(final, 0)
        elif final in words:
            year = century + words[final]
        else:
            return None
        if 1900 <= year <= 2099:
            return date(year, 1, 1)
    return None


def levenshtein_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = sum(a != b for a, b in zip(left, right, strict=True))
        return differences <= 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    index_short = index_long = 0
    edits = 0
    while index_short < len(short) and index_long < len(long):
        if short[index_short] == long[index_long]:
            index_short += 1
        else:
            edits += 1
        index_long += 1
    return edits + (len(long) - index_long) <= 1


def names_match(candidate: str, stored: str) -> bool:
    candidate_tokens = normalize_name(candidate)
    stored_tokens = normalize_name(stored)
    if len(candidate_tokens) != len(stored_tokens):
        return False
    return all(
        levenshtein_at_most_one(candidate_token, stored_token)
        for candidate_token, stored_token in zip(candidate_tokens, stored_tokens, strict=True)
    )
