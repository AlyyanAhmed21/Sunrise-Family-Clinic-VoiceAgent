from datetime import UTC, datetime

from clinic.models import CallMode, CallSession
from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLiteSessionRepository


def test_session_round_trip(database: Database) -> None:
    repository = SQLiteSessionRepository(database)
    session = CallSession(
        call_id="call-1",
        mode=CallMode.OPEN,
        updated_at=datetime.now(UTC),
    )
    repository.create(session)
    stored = repository.get("call-1")
    assert stored is not None
    assert stored.call_id == "call-1"
    assert stored.mode == CallMode.OPEN
