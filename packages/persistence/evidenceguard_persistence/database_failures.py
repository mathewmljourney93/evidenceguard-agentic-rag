"""Bounded classification of database failures for M5d (ADR-0022).

Two classifiers, both returning only a fixed enum member and keeping no reference to the error:

- ``classify_database_failure`` for failures **before** ``COMMIT`` (statements, fetches, row
  processing): ``40001``, ``40P01``, ``55P03``, ``57014`` and ``23505`` on exactly
  ``uq_reviews_tenant_id_idempotency_key``; everything else is ``other``.
- ``classify_commit_failure`` for a failed ``COMMIT``: only exactly ``40001`` or ``40P01`` is a
  recognized retryable rejection; every other case, including ``08007``
  (``transaction_resolution_unknown``), ``40003`` (``statement_completion_unknown``), ``23505`` and
  missing or unreadable diagnostics, is ``unknown``.

Only instances of SQLAlchemy's ``DBAPIError`` are examined. Diagnostics are read inside one guard
that catches only ``Exception``: ``error.orig``, its ``sqlstate`` and, for ``23505`` only,
``error.orig.diag.constraint_name``, each recognized only as an exact ``str`` equal to an
allowlisted value. Messages, ``str()``/``repr()``, SQL, parameters, exception chains and
tracebacks are never read. Process control raised while reading an attribute propagates as the
same object. This bounds the classification of supported driver errors; it is not a sandbox
against malicious trusted in-process code.
"""

from enum import StrEnum

from sqlalchemy.exc import DBAPIError

REVIEW_KEY_CONSTRAINT = "uq_reviews_tenant_id_idempotency_key"


class DatabaseFailureCategory(StrEnum):
    SERIALIZATION_FAILURE = "serialization_failure"
    DEADLOCK_DETECTED = "deadlock_detected"
    LOCK_NOT_AVAILABLE = "lock_not_available"
    QUERY_CANCELED = "query_canceled"
    REVIEW_KEY_UNIQUE_VIOLATION = "review_key_unique_violation"
    OTHER = "other"


RETRYABLE_CATEGORIES = frozenset(
    {
        DatabaseFailureCategory.SERIALIZATION_FAILURE,
        DatabaseFailureCategory.DEADLOCK_DETECTED,
        DatabaseFailureCategory.LOCK_NOT_AVAILABLE,
        DatabaseFailureCategory.REVIEW_KEY_UNIQUE_VIOLATION,
    }
)


class CommitFailureResolution(StrEnum):
    REJECTED_RETRYABLE = "rejected_retryable"
    UNKNOWN = "unknown"


_BODY_STATES = {
    "40001": DatabaseFailureCategory.SERIALIZATION_FAILURE,
    "40P01": DatabaseFailureCategory.DEADLOCK_DETECTED,
    "55P03": DatabaseFailureCategory.LOCK_NOT_AVAILABLE,
    "57014": DatabaseFailureCategory.QUERY_CANCELED,
}
_UNIQUE_VIOLATION = "23505"
_COMMIT_REJECTIONS = frozenset({"40001", "40P01"})


def _sqlstate(error: object) -> str | None:
    """The exact ``str`` SQLSTATE of a ``DBAPIError``'s driver error, or ``None``."""
    if not isinstance(error, DBAPIError):
        return None
    found: list[str] = []
    try:
        value = getattr(error.orig, "sqlstate")  # noqa: B009 - attribute access is guarded
        if type(value) is str:
            found.append(value)
    except Exception:  # missing, malformed or raising diagnostics: conservative fallback
        pass
    return found[0] if found else None


def _is_review_key_constraint(error: DBAPIError) -> bool:
    matched: list[bool] = []
    try:
        name = getattr(getattr(error.orig, "diag"), "constraint_name")  # noqa: B009
        matched.append(type(name) is str and name == REVIEW_KEY_CONSTRAINT)
    except Exception:  # conservative fallback
        pass
    return bool(matched and matched[0])


def classify_database_failure(error: object) -> DatabaseFailureCategory:
    """Classify an ordinary exception the seam has just caught (before ``COMMIT``)."""
    state = _sqlstate(error)
    if state is None:
        return DatabaseFailureCategory.OTHER
    if state == _UNIQUE_VIOLATION:
        assert isinstance(error, DBAPIError)
        if _is_review_key_constraint(error):
            return DatabaseFailureCategory.REVIEW_KEY_UNIQUE_VIOLATION
        return DatabaseFailureCategory.OTHER
    return _BODY_STATES.get(state, DatabaseFailureCategory.OTHER)


def classify_commit_failure(error: object) -> CommitFailureResolution:
    """Classify an ordinary exception raised by ``COMMIT``."""
    if _sqlstate(error) in _COMMIT_REJECTIONS:
        return CommitFailureResolution.REJECTED_RETRYABLE
    return CommitFailureResolution.UNKNOWN
