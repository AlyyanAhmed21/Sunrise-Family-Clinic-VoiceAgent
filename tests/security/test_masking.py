from clinic.security.masking import mask_text


def test_masks_supported_identifiers() -> None:
    text = (
        "DOB 1985-03-14 SSN 000-12-3344 last four 3344 "
        "phone 555-201-3344 email sarah@example.com member ID: ABC12345"
    )
    masked = mask_text(text)
    for sensitive in (
        "1985-03-14",
        "000-12-3344",
        "3344",
        "555-201-3344",
        "sarah@example.com",
        "ABC12345",
    ):
        assert sensitive not in masked


def test_masks_spoken_dob_and_last_four() -> None:
    text = (
        "My date of birth is March fourteen nineteen eighty five. "
        "My last four are three three four four."
    )
    masked = mask_text(text)
    assert "March fourteen nineteen eighty five" not in masked
    assert "three three four four" not in masked


def test_masks_spoken_phone_email_and_ssn() -> None:
    text = (
        "Phone number is five five five zero one zero two zero two zero. "
        "Email address is alex dot morgan at example dot com. "
        "Social security number is one two three four five six seven eight nine."
    )
    masked = mask_text(text)
    assert "five five five zero one zero two zero two zero" not in masked
    assert "alex dot morgan at example dot com" not in masked
    assert "one two three four five six seven eight nine" not in masked


def test_masks_named_month_dob() -> None:
    text = "My date is March 14, 1985 and I need a refill."
    masked = mask_text(text)
    assert "March 14, 1985" not in masked
    assert "[REDACTED_DOB]" in masked


def test_masks_unlabeled_spoken_contact_identifiers() -> None:
    text = (
        "My contact is five five five two zero one three three four four. "
        "My email is alex dot morgan at example dot com. "
        "The digits are one two three four five six seven eight nine."
    )
    masked = mask_text(text)
    assert "five five five two zero one three three four four" not in masked
    assert "alex dot morgan at example dot com" not in masked
    assert "one two three four five six seven eight nine" not in masked
