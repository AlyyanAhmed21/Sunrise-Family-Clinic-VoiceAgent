from datetime import datetime
from uuid import uuid4

from clinic.models import AuditEvent
from clinic.persistence.repositories import AuditRepository


class AuditLogger:
    def __init__(self, repository: AuditRepository) -> None:
        self.repository = repository

    def record(
        self,
        *,
        call_id: str,
        action: str,
        outcome: str,
        record_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEvent:
        if outcome not in {"success", "failure", "locked"}:
            raise ValueError("invalid audit outcome")
        event = AuditEvent(
            audit_id=str(uuid4()),
            call_id=call_id,
            actor="caller",
            record_id=record_id,
            timestamp=timestamp or datetime.now().astimezone(),
            action=action,
            outcome=outcome,  # type: ignore[arg-type]
        )
        self.repository.save(event)
        return event
