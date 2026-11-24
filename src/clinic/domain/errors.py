class DomainError(Exception):
    """Base class for expected clinic-domain failures."""


class UnauthorizedPatientAccess(DomainError):
    """A patient record was requested without trusted verification."""


class VerificationLocked(DomainError):
    """Further verification is blocked after the third failure."""
