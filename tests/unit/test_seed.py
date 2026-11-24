from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLitePatientRepository
from clinic.persistence.seed import seed_database

TEST_PEPPER = "step1-deterministic-test-pepper"


def test_seed_has_three_exact_patients(database: Database) -> None:
    repository = SQLitePatientRepository(database)
    patients = repository.list_all()
    assert [patient.patient_id for patient in patients] == ["P001", "P002", "P003"]
    maria = repository.get("P003")
    assert maria is not None
    assert maria.next_appointment == "2026-11-28 2:00 PM with Dr. Lee"


def test_seed_is_repeatable(database: Database) -> None:
    seed_database(database, TEST_PEPPER)
    seed_database(database, TEST_PEPPER)
    with database.connect() as connection:
        patient_count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        slot_count = connection.execute("SELECT COUNT(*) FROM available_slots").fetchone()[0]
    assert patient_count == 3
    assert slot_count == 7


def test_no_full_ssn_or_raw_last4_is_persisted(database: Database) -> None:
    with database.connect() as connection:
        patient_dump = connection.execute(
            "SELECT first_name, last_name, phone, last4_salt, last4_digest FROM patients"
        ).fetchall()
        medication_dump = connection.execute("SELECT name, pharmacy FROM medications").fetchall()
    assert all("3344" not in row["last4_salt"] for row in patient_dump)
    assert all("1020" not in row["last4_salt"] for row in patient_dump)
    assert all("9081" not in row["last4_salt"] for row in patient_dump)
    assert all("3344" not in row["last4_digest"] for row in patient_dump)
    assert all("1020" not in row["last4_digest"] for row in patient_dump)
    assert all("9081" not in row["last4_digest"] for row in patient_dump)
    assert len(medication_dump) == 4
