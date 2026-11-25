"""Deterministic parsing of caller speech: dates, digit strings and names.

Speech-to-text may return words ("March fourteenth nineteen eighty-five"), digits
("March 14 1985"), split years ("19 85") or numeric dates ("3/14/1985"). Everything is
reduced to `Number` tokens with character spans, so callers can both read a value and
remove exactly the words that carried it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "july": 7, "august": 8, "aug": 8, "september": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}  # fmt: skip
_UNITS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}  # fmt: skip
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_ORDINAL_UNITS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
}  # fmt: skip
_ORDINALS = {
    **_ORDINAL_UNITS, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17,
    "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
}  # fmt: skip
_REPEATS = {"double": 2, "triple": 3}
_TOKEN = re.compile(r"\d+(?:st|nd|rd|th)?|[a-z]+")
_NUMERIC_DATE = re.compile(r"\b(\d{1,4})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_LAST_FOUR_LABEL = re.compile(r"\blast\s*(?:four|4)(?:\s+digits?)?\b|\bfour\s+digits?\b")

Span = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Number:
    value: int
    digits: str
    ordinal: bool
    span: Span


@dataclass(frozen=True, slots=True)
class DateParts:
    """A possibly partial calendar date with the text spans it was read from."""

    month: int | None = None
    day: int | None = None
    year: int | None = None
    spans: tuple[Span, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.month is None and self.day is None and self.year is None

    @property
    def is_complete(self) -> bool:
        return None not in (self.month, self.day, self.year)

    @property
    def missing(self) -> tuple[str, ...]:
        names = ("month", "day", "year")
        values = (self.month, self.day, self.year)
        return tuple(name for name, value in zip(names, values, strict=True) if value is None)

    def over(self, older: DateParts) -> DateParts:
        """Newer components win; components the caller did not repeat are kept."""
        return DateParts(
            month=self.month if self.month is not None else older.month,
            day=self.day if self.day is not None else older.day,
            year=self.year if self.year is not None else older.year,
            spans=self.spans,
        )

    def to_date(self, *, today: date) -> date | None:
        """Return a real, past date of birth, or None if incomplete or impossible."""
        if self.month is None or self.day is None or self.year is None:
            return None
        try:
            value = date(self.year, self.month, self.day)
        except ValueError:
            return None
        return value if date(1900, 1, 1) <= value <= today else None


def _tokens(text: str) -> list[tuple[str, Span]]:
    return [(m.group(), m.span()) for m in _TOKEN.finditer(text.casefold().replace("-", " "))]


def _year_words(words: list[str]) -> tuple[int, int] | None:
    """Read "nineteen eighty five", "twenty twelve", "nineteen oh five", "two thousand five"."""
    first, second = words[0], words[1] if len(words) > 1 else ""
    third = words[2] if len(words) > 2 else ""
    if first == "two" and second == "thousand":
        rest = words[3:] if third == "and" else words[2:]
        tail = _small_words(rest)
        return (2000 + tail[0], len(words) - len(rest) + tail[1]) if tail else (2000, 2)
    if first not in ("nineteen", "twenty"):
        return None
    century = 1900 if first == "nineteen" else 2000
    if second in _TENS:
        return century + _TENS[second] + _UNITS.get(third, 0), 3 if third in _UNITS else 2
    if second in _TEENS:
        return century + _TEENS[second], 2
    if second == "oh" and third in _UNITS:
        return century + _UNITS[third], 3
    return None


def _small_words(words: list[str]) -> tuple[int, int] | None:
    if not words:
        return None
    first, second = words[0], words[1] if len(words) > 1 else ""
    if first in _TENS and second in _UNITS and _UNITS[second] > 0:
        return _TENS[first] + _UNITS[second], 2
    for table in (_UNITS, _TEENS, _TENS):
        if first in table:
            return table[first], 1
    return None


def numbers_in(text: str, *, skip: tuple[Span, ...] = ()) -> list[Number]:
    """Group digits and number words into numbers, keeping the character span of each."""
    tokens = [t for t in _tokens(text) if not any(s <= t[1][0] < e for s, e in skip)]
    words = [word for word, _ in tokens]
    found: list[Number] = []
    index = 0
    while index < len(tokens):
        start = tokens[index][1][0]
        number, used = _number_at(words, index)
        if number is None:
            index += 1
            continue
        value, digits, ordinal = number
        found.append(Number(value, digits, ordinal, (start, tokens[index + used - 1][1][1])))
        index += used
    return found


def _number_at(words: list[str], index: int) -> tuple[tuple[int, str, bool] | None, int]:
    word, following = words[index], words[index + 1 : index + 5]
    previous = words[index - 1] if index > 0 else ""
    after = following[0] if following else ""
    if word == "oh" and not (_is_digit_word(previous) or _is_digit_word(after)):
        return None, 1  # "Oh, it's..." is an interjection, not a zero
    numeric = re.fullmatch(r"(\d+)(st|nd|rd|th)?", word)
    if numeric:
        digits, used = numeric.group(1), 1
        if digits in ("19", "20") and following and re.fullmatch(r"\d\d", following[0]):
            digits, used = digits + following[0], 2  # "19 85" -> 1985
        if _is_split_year(digits, words[index + used : index + used + 1]):
            # "nineteen seventy-three" can arrive as "19 70 3" or "1970 3"
            digits, used = digits[:3] + words[index + used], used + 1
        return (int(digits), digits, used == 1 and numeric.group(2) is not None), used
    if word in _REPEATS and following and (following[0] in _UNITS or _is_digit(following[0])):
        digit = following[0] if _is_digit(following[0]) else str(_UNITS[following[0]])
        return (int(digit * _REPEATS[word]), digit * _REPEATS[word], False), 2
    year = _year_words(words[index : index + 5])
    if year is not None:
        return (year[0], str(year[0]), False), year[1]
    if word in _TENS and following and following[0] in _ORDINAL_UNITS:
        value = _TENS[word] + _ORDINAL_UNITS[following[0]]
        return (value, str(value), True), 2
    if word in _ORDINALS:
        return (_ORDINALS[word], str(_ORDINALS[word]), True), 1
    small = _small_words(words[index : index + 2])
    if small is not None:
        digits = "0" if word == "oh" else str(small[0])
        return (small[0], digits, False), small[1]
    return None, 1


def _is_split_year(digits: str, following: list[str]) -> bool:
    return (
        len(digits) == 4
        and digits[:2] in ("19", "20")
        and digits[2] != "0"
        and digits[3] == "0"
        and bool(following)
        and re.fullmatch(r"[1-9]", following[0]) is not None
    )


def _is_digit(word: str) -> bool:
    return len(word) == 1 and word.isdigit()


def _is_digit_word(word: str) -> bool:
    return word.isdigit() or word in _UNITS or word in _REPEATS


def parse_date_parts(text: str, *, today: date) -> DateParts:
    """Read month/day/year from speech. US month-first order for numeric dates."""
    lowered = text.casefold()
    numeric = _NUMERIC_DATE.search(lowered)
    if numeric:
        first, second, third = numeric.groups()
        if len(first) == 4:
            return DateParts(int(second), int(third), int(first), (numeric.span(),))
        return DateParts(int(first), int(second), _expand_year(third, today), (numeric.span(),))

    tokens = _tokens(text)
    month_index = _month_index(tokens)
    labels = tuple(m.span() for m in _LAST_FOUR_LABEL.finditer(lowered))
    numbers = numbers_in(text, skip=labels)
    year = next(
        (n for n in reversed(numbers) if len(n.digits) == 4 and 1900 <= n.value <= today.year),
        None,
    )
    rest = [n for n in numbers if n is not year and 1 <= n.value <= 31]
    if month_index is None:
        return _numeric_month_day(rest, year)

    month_span = tokens[month_index][1]
    day = _nearest_day(rest, month_span)
    if year is None and day is not None:
        year = next((n for n in numbers if n.span[0] > day.span[0] and 32 <= n.value <= 99), None)
        if year is not None:
            year = replace(year, value=1900 + year.value)
    spans = tuple(n.span for n in (day, year) if n is not None) + (month_span,)
    return DateParts(
        _MONTHS[tokens[month_index][0]],
        day.value if day else None,
        year.value if year else None,
        spans,
    )


def _month_index(tokens: list[tuple[str, Span]]) -> int | None:
    for index, (word, _) in enumerate(tokens):
        if word not in _MONTHS:
            continue
        if word == "may":  # "may" is a month only beside a number
            neighbours = [tokens[i][0] for i in (index - 1, index + 1) if 0 <= i < len(tokens)]
            if not any(w[0].isdigit() or w in _ORDINALS or w in _UNITS for w in neighbours):
                continue
        return index
    return None


def _nearest_day(candidates: list[Number], month_span: Span) -> Number | None:
    def distance(number: Number) -> int:
        return min(abs(number.span[0] - month_span[1]), abs(month_span[0] - number.span[1]))

    return min(candidates, key=distance, default=None)


def _numeric_month_day(numbers: list[Number], year: Number | None) -> DateParts:
    """Without a month name: "3 14 1985" is month-first; a lone number is read as a day."""
    spans = (year.span,) if year else ()
    year_value = year.value if year else None
    if len(numbers) == 1:
        return DateParts(day=numbers[0].value, year=year_value, spans=spans + (numbers[0].span,))
    if not numbers:
        return DateParts(year=year_value, spans=spans)
    first, second = numbers[0], numbers[1]
    if first.value > 12 and second.value <= 12:
        first, second = second, first
    if first.value > 12:
        return DateParts(year=year_value, spans=spans)
    return DateParts(first.value, second.value, year_value, spans + (first.span, second.span))


def _expand_year(value: str, today: date) -> int | None:
    if len(value) == 4:
        return int(value)
    two_digit = int(value)
    # "85" can only mean 1985 for a birth date; "05" could be 1905 or 2005, so ask.
    return 1900 + two_digit if two_digit > today.year % 100 else None


def parse_dob(text: str, *, today: date) -> date | None:
    return parse_date_parts(text, today=today).to_date(today=today)


def spoken_digits(text: str, *, skip: tuple[Span, ...] = ()) -> tuple[str, tuple[Span, ...]]:
    """Concatenate every spoken or written digit, ignoring a "last four" label itself."""
    labels = tuple(m.span() for m in _LAST_FOUR_LABEL.finditer(text.casefold()))
    numbers = numbers_in(text, skip=skip + labels)
    return "".join(n.digits for n in numbers), tuple(n.span for n in numbers)


def parse_last_four(text: str) -> str | None:
    digits, _ = spoken_digits(text)
    return digits if len(digits) == 4 else None


def parse_phone(text: str) -> str | None:
    digits, _ = spoken_digits(text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}")
_SPOKEN_EMAIL_WORDS = (
    (r"\b(?:at the rate(?: of)?|at sign|at)\b", "@"),
    (r"\b(?:dot|period|point)\b", "."),
    (r"\bunderscore\b", "_"),
    (r"\b(?:dash|hyphen|minus)\b", "-"),
    (r"\bg\s*mail\b", "gmail"),
    (r"\bhot\s*mail\b", "hotmail"),
    (r"\bout\s*look\b", "outlook"),
    (r"\bya\s*hoo\b", "yahoo"),
)


def normalize_spoken_email(value: str) -> str | None:
    """Turn a spoken or partly written email ("daniel dot carter at g mail dot com") into
    `daniel.carter@gmail.com`. Returns None if the result is not a plausible address."""
    text = value.casefold().strip().rstrip(".!?,")
    text = re.sub(r"^(?:my\s+)?(?:email(?:\s+address)?\s+is|it'?s)\s+", "", text)
    for pattern, replacement in _SPOKEN_EMAIL_WORDS:
        text = re.sub(pattern, f" {replacement} ", text)
    email = re.sub(r"\s+", "", text)
    return email if len(email) <= 254 and _EMAIL.fullmatch(email) else None


_MEMBER_ID_FILLER = {
    "it", "its", "is", "my", "the", "member", "id", "number", "no", "on", "card", "insurance",
    "and", "um", "uh", "er", "so", "okay", "ok", "yes", "yeah", "of", "policy", "subscriber",
}  # fmt: skip


def normalize_member_id(value: str) -> str | None:
    """Turn a spoken insurance member ID into its written form, or None if it is unusable.

    Handles digit-by-digit speech ("4 8 2 9 1"), number words ("forty-eight two nine one"),
    speech-to-text formatting artifacts ("48 $2.91"), and letter prefixes ("A B C 1 2 3 4").
    A usable ID has 4-20 letters/digits including at least 4 digits; anything else is
    returned as None so the agent asks again instead of saving a guess.
    """
    text = value.casefold().replace("'", "")
    spans = numbers_in(text)
    pieces: list[str] = []
    position = 0
    for number in spans:  # rebuild left to right, replacing every number with its digits
        pieces.append(text[position : number.span[0]])
        pieces.append(f" {number.digits} ")
        position = number.span[1]
    pieces.append(text[position:])
    words = re.findall(r"[a-z0-9]+", "".join(pieces))
    member_id = "".join(word for word in words if word not in _MEMBER_ID_FILLER).upper()
    digits = sum(char.isdigit() for char in member_id)
    return member_id if 4 <= len(member_id) <= 20 and digits >= 4 else None


def normalize_name(value: str) -> tuple[str, ...]:
    cleaned = re.sub(r"[^\w\s'-]", " ", value, flags=re.UNICODE)
    words = cleaned.lower().replace("'", "").split()
    return tuple(word for word in words if word not in {"mr", "mrs", "ms", "dr"})


def levenshtein_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) <= 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    return any(long[:i] + long[i + 1 :] == short for i in range(len(long)))


def names_match(candidate: str, stored: str) -> bool:
    candidate_tokens = normalize_name(candidate)
    stored_tokens = normalize_name(stored)
    if len(candidate_tokens) != len(stored_tokens):
        return False
    return all(
        levenshtein_at_most_one(candidate_token, stored_token)
        for candidate_token, stored_token in zip(candidate_tokens, stored_tokens, strict=True)
    )
