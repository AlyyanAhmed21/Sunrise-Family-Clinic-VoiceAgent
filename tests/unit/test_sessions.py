from datetime import UTC, datetime, timedelta

from clinic.models import CallMode, CallSession
from clinic.persistence.db import Database
from clinic.persistence.repositories import SQLiteSessionRepository


def test_session_round_trip(database: Database) -> None:
    repository = SQLiteSessionRepository(database)
    session = CallSession(
        call_id="call-1",
        mode=CallMode.OPEN,
        pending_refill_token_digest="token-digest",
        pending_refill_medication="Lisinopril 10mg",
        pending_refill_pharmacy="CVS Main St",
        pending_refill_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        updated_at=datetime.now(UTC),
    )
    repository.create(session)
    stored = repository.get("call-1")
    assert stored is not None
    assert stored.call_id == "call-1"
    assert stored.mode == CallMode.OPEN
    assert stored.pending_refill_token_digest == "token-digest"
    assert stored.pending_refill_medication == "Lisinopril 10mg"
    assert stored.pending_refill_pharmacy == "CVS Main St"
