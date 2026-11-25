from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinic.config import Settings
from clinic.persistence.db import Database
from clinic.persistence.seed import seed_database


def _database() -> Database:
    settings = Settings()
    database = Database(settings.database_path)
    database.create_schema()
    return database


def show_requests() -> None:
    with _database().connect() as connection:
        rows = connection.execute(
            """
            SELECT request_id, patient_id, subject_reference, request_type,
                   created_at, masked_summary, medication_name, pharmacy,
                   status, outcome, callback_name, callback_phone
            FROM patient_requests ORDER BY created_at DESC
            """
        ).fetchall()
    output = []
    for row in rows:
        record = dict(row)
        record["callback_name"] = (
            "[REDACTED_CALLBACK_NAME]" if record.get("callback_name") else None
        )
        record["callback_phone"] = (
            "[REDACTED_CALLBACK_PHONE]" if record.get("callback_phone") else None
        )
        output.append(record)
    print(json.dumps(output, indent=2))


def show_audit() -> None:
    with _database().connect() as connection:
        rows = connection.execute(
            """
            SELECT audit_id, call_id, actor, record_id, timestamp, action, outcome
            FROM audit_events ORDER BY timestamp DESC
            """
        ).fetchall()
    print(json.dumps([dict(row) for row in rows], indent=2))


def reset_demo() -> None:
    database = _database()
    with database.transaction() as connection:
        connection.execute("DELETE FROM patient_requests")
        connection.execute("DELETE FROM audit_events")
        connection.execute("DELETE FROM call_sessions")
        connection.execute("DELETE FROM appointments WHERE appointment_id NOT LIKE 'fixture-%'")
        connection.execute("DELETE FROM patients WHERE patient_id LIKE 'NEW-%'")
        connection.execute("UPDATE available_slots SET available = 1")
    outbox = Path("data/outbox")
    if outbox.exists():
        for artifact in outbox.glob("*.json"):
            artifact.unlink()
    print("Demo data reset. Seed patients and fixture appointments were preserved.")


def seed() -> None:
    """Create the schema and load the synthetic patients and slots (idempotent)."""
    settings = Settings()
    seed_database(_database(), settings.require_hash_pepper())
    print(f"Synthetic clinic data is ready in {settings.database_path}.")


COMMANDS = {
    "seed": seed,
    "show-requests": show_requests,
    "show-audit": show_audit,
    "reset-demo": reset_demo,
}


def main() -> None:
    """Developer-only operations. Not reachable from a call or the HTTP API."""
    parser = argparse.ArgumentParser(description="Sunrise Family Clinic operator commands")
    parser.add_argument("command", choices=COMMANDS)
    COMMANDS[parser.parse_args().command]()


if __name__ == "__main__":
    main()
