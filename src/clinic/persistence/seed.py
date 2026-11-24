import json
import re
import secrets
from pathlib import Path

from clinic.persistence.db import Database
from clinic.security.hashing import hash_last4


def seed_database(database: Database, pepper: str) -> None:
    if not pepper:
        raise RuntimeError("HASH_PEPPER is required for seeding")
    patient_path = Path("data/seed/patients.json")
    slot_path = Path("data/seed/slots.json")
    patients = json.loads(patient_path.read_text(encoding="utf-8"))["patients"]
    slots = json.loads(slot_path.read_text(encoding="utf-8"))["available_slots"]
    database.create_schema()
    with database.transaction() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO doctors (name, specialty) VALUES (?, ?)",
            ("Dr. Patel", "Family Medicine"),
        )
        connection.execute(
            "INSERT OR IGNORE INTO doctors (name, specialty) VALUES (?, ?)",
            ("Dr. Lee", "Internal Medicine"),
        )
        for fixture in patients:
            salt = connection.execute(
                "SELECT last4_salt FROM patients WHERE patient_id = ?",
                (fixture["patient_id"],),
            ).fetchone()
            if salt is None:
                stored_salt = secrets.token_hex(16)
                digest = hash_last4(fixture["ssn_last4"], stored_salt, pepper)
                connection.execute(
                    """
                    INSERT INTO patients (
                        patient_id, first_name, last_name, dob, phone,
                        last4_salt, last4_digest, next_appointment,
                        lab_results_status, balance_due
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fixture["patient_id"],
                        fixture["first_name"],
                        fixture["last_name"],
                        fixture["dob"],
                        fixture["phone"],
                        stored_salt,
                        digest,
                        fixture["next_appointment"],
                        fixture["lab_results_status"],
                        fixture["balance_due"],
                    ),
                )
            for medication in fixture["medications"]:
                connection.execute(
                    """
                    INSERT INTO medications (
                        patient_id, name, refills_remaining, last_filled, pharmacy
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(patient_id, name) DO UPDATE SET
                        refills_remaining=excluded.refills_remaining,
                        last_filled=excluded.last_filled,
                        pharmacy=excluded.pharmacy
                    """,
                    (
                        fixture["patient_id"],
                        medication["name"],
                        medication["refills_remaining"],
                        medication["last_filled"],
                        medication["pharmacy"],
                    ),
                )
        for slot_group in slots:
            for time_text in slot_group["times"]:
                hour, minute = (
                    int(part)
                    for part in time_text.replace("AM", "").replace("PM", "").strip().split(":")
                )
                if "PM" in time_text and hour != 12:
                    hour += 12
                if "AM" in time_text and hour == 12:
                    hour = 0
                start_at = f"{slot_group['date']}T{hour:02d}:{minute:02d}:00"
                slot_id = f"{slot_group['doctor']}-{slot_group['date']}-{hour:02d}{minute:02d}"
                connection.execute(
                    """
                    INSERT INTO available_slots (slot_id, doctor_name, start_at, available)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(slot_id) DO NOTHING
                    """,
                    (slot_id, slot_group["doctor"], start_at),
                )
        for fixture in patients:
            appointment_text = fixture["next_appointment"]
            if appointment_text is None:
                continue
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", appointment_text)
            time_match = re.search(r"(\d{1,2}:\d{2}\s+[AP]M)", appointment_text)
            doctor_match = re.search(r"(Dr\. [A-Za-z]+)", appointment_text)
            if date_match and time_match and doctor_match:
                time_text = time_match.group(1)
                hour, minute = (
                    int(part)
                    for part in time_text.replace("AM", "").replace("PM", "").strip().split(":")
                )
                if "PM" in time_text and hour != 12:
                    hour += 12
                if "AM" in time_text and hour == 12:
                    hour = 0
                start_at = f"{date_match.group(1)}T{hour:02d}:{minute:02d}:00"
                appointment_id = f"fixture-{fixture['patient_id']}"
                connection.execute(
                    """
                    INSERT INTO appointments (
                        appointment_id, patient_id, doctor_name, start_at, status
                    ) VALUES (?, ?, ?, ?, 'scheduled')
                    ON CONFLICT(appointment_id) DO NOTHING
                    """,
                    (
                        appointment_id,
                        fixture["patient_id"],
                        doctor_match.group(1),
                        start_at,
                    ),
                )
