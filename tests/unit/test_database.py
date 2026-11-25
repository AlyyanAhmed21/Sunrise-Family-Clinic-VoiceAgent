import sqlite3

import pytest

from clinic.persistence.db import Database


def test_foreign_keys_are_enforced(database: Database) -> None:
    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO medications "
                "(patient_id, name, refills_remaining, last_filled, pharmacy) "
                "VALUES (?, ?, ?, ?, ?)",
                ("UNKNOWN", "Test", 1, "2026-01-01", "Test Pharmacy"),
            )


def test_seed_slots_and_appointments(database: Database) -> None:
    with database.connect() as connection:
        slots = connection.execute("SELECT COUNT(*) FROM available_slots").fetchone()[0]
        appointments = connection.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    assert slots == 7
    assert appointments == 2


def test_schema_migrates_step_one_request_and_session_tables(tmp_path) -> None:
    database = Database(tmp_path / "step-one.sqlite3")
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE call_sessions (
                call_id TEXT PRIMARY KEY, mode TEXT NOT NULL,
                verified_patient_id TEXT, failed_attempts INTEGER NOT NULL,
                unparsed_attempts INTEGER NOT NULL, status TEXT NOT NULL,
                simulated_time TEXT, updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE patient_requests (
                request_id TEXT PRIMARY KEY, call_id TEXT NOT NULL,
                patient_id TEXT, request_type TEXT NOT NULL, created_at TEXT NOT NULL,
                masked_summary TEXT NOT NULL, status TEXT NOT NULL
            )
            """
        )

    database.create_schema()

    with database.connect() as connection:
        session_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(call_sessions)")
        }
        request_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(patient_requests)")
        }
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(patient_requests)")}
    assert "pending_refill_token_digest" in session_columns
    assert "pending_refill_expires_at" in session_columns
    assert {"outcome", "medication_name", "pharmacy"} <= request_columns
    assert "uq_pending_refill_per_patient" in indexes
