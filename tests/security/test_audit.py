from datetime import UTC, datetime

from clinic.audit import AuditLogger
from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLiteAuditRepository


def test_audit_does_not_store_submitted_values(database: Database) -> None:
    logger = AuditLogger(SQLiteAuditRepository(database))
    event = logger.record(
        call_id="call-audit",
        action="verification_attempt",
        outcome="failure",
        timestamp=datetime.now(UTC),
    )
    dumped = event.model_dump_json()
    assert "3344" not in dumped
    assert "1985-03-14" not in dumped
    assert "failed_field" not in dumped
