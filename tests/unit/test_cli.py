from pathlib import Path

import pytest

from clinic.cli import COMMANDS, seed, show_requests


def test_operator_commands_are_exactly_the_documented_ones() -> None:
    assert set(COMMANDS) == {"seed", "show-requests", "show-audit", "reset-demo"}


def test_seed_creates_the_synthetic_clinic(monkeypatch, tmp_path: Path, capsys) -> None:
    from clinic.persistence.db import Database

    database = Database(tmp_path / "clinic.sqlite3")
    database.create_schema()
    monkeypatch.setattr("clinic.cli._database", lambda: database)
    monkeypatch.setenv("HASH_PEPPER", "cli-test-pepper")

    seed()

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM available_slots").fetchone()[0] == 7
    assert "ready" in capsys.readouterr().out


def test_seed_refuses_to_run_without_a_pepper(monkeypatch, tmp_path: Path) -> None:
    from clinic.config import Settings

    monkeypatch.setattr(Settings, "model_config", {"env_file": None, "extra": "ignore"})
    monkeypatch.delenv("HASH_PEPPER", raising=False)

    with pytest.raises(RuntimeError, match="HASH_PEPPER"):
        seed()


def test_show_requests_masks_callback_contact(monkeypatch, tmp_path: Path, capsys) -> None:
    from clinic.persistence.db import Database

    database = Database(tmp_path / "clinic.sqlite3")
    database.create_schema()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO call_sessions (
                call_id, mode, status, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            ("call-1", "closed", "open", "2026-11-24T20:00:00-05:00"),
        )
        connection.execute(
            """
            INSERT INTO patient_requests (
                request_id, call_id, request_type, created_at, masked_summary,
                status, outcome, callback_name, callback_phone, subject_reference
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "request-1",
                "call-1",
                "callback",
                "2026-11-24T20:00:00-05:00",
                "Scheduling callback requested",
                "open",
                "pending",
                "Alex Morgan",
                "5550102020",
                "UNVERIFIED",
            ),
        )

    monkeypatch.setattr("clinic.cli._database", lambda: database)
    show_requests()
    terminal = capsys.readouterr().out
    assert "Alex Morgan" not in terminal
    assert "5550102020" not in terminal
    assert "[REDACTED_CALLBACK_NAME]" in terminal
    assert "[REDACTED_CALLBACK_PHONE]" in terminal
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT callback_name, callback_phone FROM patient_requests "
            "WHERE request_id = 'request-1'"
        ).fetchone()
    assert stored["callback_name"] == "Alex Morgan"
    assert stored["callback_phone"] == "5550102020"
