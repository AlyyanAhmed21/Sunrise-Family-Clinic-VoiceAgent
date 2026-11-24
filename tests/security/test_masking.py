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
