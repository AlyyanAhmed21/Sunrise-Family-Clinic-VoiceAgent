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
