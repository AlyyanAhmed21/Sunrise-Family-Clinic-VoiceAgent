import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    dob TEXT NOT NULL,
    phone TEXT NOT NULL,
    last4_salt TEXT NOT NULL,
    last4_digest TEXT NOT NULL,
    next_appointment TEXT,
    lab_results_status TEXT NOT NULL,
    balance_due REAL NOT NULL CHECK (balance_due >= 0)
);
CREATE TABLE IF NOT EXISTS medications (
    medication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    name TEXT NOT NULL,
    refills_remaining INTEGER NOT NULL CHECK (refills_remaining >= 0),
    last_filled TEXT NOT NULL,
    pharmacy TEXT NOT NULL,
    UNIQUE(patient_id, name),
    FOREIGN KEY(patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    specialty TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS available_slots (
    slot_id TEXT PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    start_at TEXT NOT NULL,
    available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0,1)),
    FOREIGN KEY(doctor_name) REFERENCES doctors(name)
);
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_name TEXT NOT NULL,
    start_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('scheduled','cancelled')),
    FOREIGN KEY(patient_id) REFERENCES patients(patient_id),
    FOREIGN KEY(doctor_name) REFERENCES doctors(name)
);
CREATE TABLE IF NOT EXISTS call_sessions (
    call_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('open','closed')),
    verified_patient_id TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts BETWEEN 0 AND 3),
    unparsed_attempts INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('open','locked','closed')),
    simulated_time TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(verified_patient_id) REFERENCES patients(patient_id)
);
CREATE TABLE IF NOT EXISTS patient_requests (
    request_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    patient_id TEXT,
    request_type TEXT NOT NULL CHECK (
        request_type IN ('refill','booking','callback','message','transfer')
    ),
    created_at TEXT NOT NULL,
    masked_summary TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open','completed','cancelled')),
    FOREIGN KEY(call_id) REFERENCES call_sessions(call_id),
    FOREIGN KEY(patient_id) REFERENCES patients(patient_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    record_id TEXT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success','failure','locked'))
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def create_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()
