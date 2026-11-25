from pathlib import Path

from clinic.security.masking import mask_text


def test_security_canary_rejects_raw_synthetic_phi(tmp_path: Path) -> None:
    raw_values = (
        "1985-03-14",
        "000-12-3344",
        "3344",
        "555-201-3344",
        "sarah@example.com",
        "ABC12345",
    )
    payload = (
        "DOB 1985-03-14 SSN 000-12-3344 last four 3344 "
        "phone 555-201-3344 email sarah@example.com member ID ABC12345"
    )
    (tmp_path / "app.log").write_text(mask_text(payload), encoding="utf-8")
    (tmp_path / "audit.json").write_text(mask_text(payload), encoding="utf-8")
    (tmp_path / "requests.json").write_text(mask_text(payload), encoding="utf-8")

    retained_text = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.iterdir() if path.is_file()
    )
    for raw in raw_values:
        assert raw not in retained_text
