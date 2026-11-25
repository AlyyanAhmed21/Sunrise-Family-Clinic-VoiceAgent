class DomainError(Exception):
    """Base class for expected clinic-domain failures."""


class UnauthorizedPatientAccess(DomainError):
    """A patient record was requested without trusted verification."""


class VerificationLocked(DomainError):
    """Further verification is blocked after the third failure."""


class UnknownCallSession(DomainError):
    """The trusted call identifier does not map to an active session."""


class ClinicClosed(DomainError):
    """Patient-specific service is unavailable outside clinic hours."""


class PatientRecordUnavailable(DomainError):
    """The verified patient's record is unavailable."""


class InvalidStateTransition(DomainError):
    """The requested operation is not valid for the current server-side state."""


class PersistenceFailure(DomainError):
    """Persistence failed without exposing database details to the caller."""
