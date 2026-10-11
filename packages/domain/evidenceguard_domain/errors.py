"""Explicit domain errors raised by report transitions."""


class DomainError(Exception):
    """Base class for rule violations in domain transitions."""


class TenantMismatchError(DomainError):
    """The actor or content belongs to a different tenant than the report."""


class PermissionDeniedError(DomainError):
    """The actor's role does not allow this action."""


class StaleRevisionError(DomainError):
    """The request names a revision that is not the current one."""


class ContentHashMismatchError(DomainError):
    """The request's content hash does not match the current revision."""


class InvalidTransitionError(DomainError):
    """The report's state does not allow this action."""


class NotExportableError(InvalidTransitionError):
    """Only finalized reports can be exported."""


class DecisionConflictError(InvalidTransitionError):
    """The decision is already recorded, but this request differs in actor or comment.

    Only an identical retry is idempotent. A changed request is refused rather than silently
    discarded or recorded as a duplicate decision.
    """
