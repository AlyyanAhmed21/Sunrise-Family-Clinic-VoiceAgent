from clinic.models import CallSession
from clinic.persistence.repositories import SessionRepository


def create_session(repository: SessionRepository, session: CallSession) -> CallSession:
    existing = repository.get(session.call_id)
    if existing is not None:
        return existing
    repository.create(session)
    return session
