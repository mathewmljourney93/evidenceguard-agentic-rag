"""Bounded database-failure classification (``database_failures``, M5d-B4/C5, ADR-0022).

Driver errors are fakes wrapped in SQLAlchemy's ``DBAPIError``; no database or network is used.
"""

from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from evidenceguard_persistence.database_failures import (
    RETRYABLE_CATEGORIES,
    REVIEW_KEY_CONSTRAINT,
    CommitFailureResolution,
    DatabaseFailureCategory,
    classify_commit_failure,
    classify_database_failure,
)

Category = DatabaseFailureCategory
Resolution = CommitFailureResolution


class Diag:
    def __init__(self, constraint_name: object) -> None:
        self.constraint_name = constraint_name


class DriverError(Exception):
    def __init__(self, sqlstate: object = None, constraint: object = None) -> None:
        super().__init__("driver message with SECRET-TEXT")
        self.sqlstate = sqlstate
        self.diag = Diag(constraint)


class NoDiagnostics(Exception):
    pass


class Stop(KeyboardInterrupt):
    pass


def wrapped(orig: object, kind: type[DBAPIError] = OperationalError) -> DBAPIError:
    return kind("SELECT 1", {"secret": "SECRET-PARAM"}, orig)  # type: ignore[arg-type]


def failure(sqlstate: object, constraint: object = None) -> DBAPIError:
    return wrapped(DriverError(sqlstate, constraint))


def test_retryable_categories_are_exactly_the_accepted_set() -> None:
    assert {
        Category.SERIALIZATION_FAILURE,
        Category.DEADLOCK_DETECTED,
        Category.LOCK_NOT_AVAILABLE,
        Category.REVIEW_KEY_UNIQUE_VIOLATION,
    } == RETRYABLE_CATEGORIES
    assert REVIEW_KEY_CONSTRAINT == "uq_reviews_tenant_id_idempotency_key"


@pytest.mark.parametrize(
    ("sqlstate", "expected"),
    [
        ("40001", Category.SERIALIZATION_FAILURE),
        ("40P01", Category.DEADLOCK_DETECTED),
        ("55P03", Category.LOCK_NOT_AVAILABLE),
        ("57014", Category.QUERY_CANCELED),
        ("08007", Category.OTHER),
        ("40003", Category.OTHER),
        ("42P01", Category.OTHER),
        ("40p01", Category.OTHER),  # exact match only
        (" 40001", Category.OTHER),
        ("", Category.OTHER),
        (None, Category.OTHER),
        (40001, Category.OTHER),
        (b"40001", Category.OTHER),
    ],
)
def test_body_failures_are_classified_by_exact_sqlstate(sqlstate: object, expected: Any) -> None:
    assert classify_database_failure(failure(sqlstate)) is expected


def test_unique_violation_counts_only_on_the_review_key_constraint() -> None:
    review_key = wrapped(DriverError("23505", REVIEW_KEY_CONSTRAINT), IntegrityError)
    assert classify_database_failure(review_key) is Category.REVIEW_KEY_UNIQUE_VIOLATION
    for constraint in (
        "uq_jobs_kind_idempotency_key",
        "pk_reviews",
        REVIEW_KEY_CONSTRAINT.upper(),
        None,
        42,
    ):
        assert classify_database_failure(failure("23505", constraint)) is Category.OTHER

    class StrSubclass(str):
        pass

    subclass = failure("23505", StrSubclass(REVIEW_KEY_CONSTRAINT))
    assert classify_database_failure(subclass) is Category.OTHER
    without_diag = DriverError("23505")
    del without_diag.diag
    assert classify_database_failure(wrapped(without_diag)) is Category.OTHER


def test_the_review_key_constraint_never_makes_another_sqlstate_retryable() -> None:
    assert classify_database_failure(failure("23503", REVIEW_KEY_CONSTRAINT)) is Category.OTHER


@pytest.mark.parametrize(
    "error",
    [
        Exception("40001"),
        DriverError("40001"),  # the right attributes but not a DBAPIError
        "40001",
        None,
        wrapped(NoDiagnostics()),
        wrapped(None),
    ],
)
def test_non_dbapi_or_diagnostic_free_errors_are_other(error: object) -> None:
    assert classify_database_failure(error) is Category.OTHER
    assert classify_commit_failure(error) is Resolution.UNKNOWN


def test_raising_diagnostics_fall_back_conservatively() -> None:
    class Raising(Exception):
        @property
        def sqlstate(self) -> str:
            raise RuntimeError("diagnostics unavailable")

    class RaisingDiag(Exception):
        sqlstate = "23505"

        @property
        def diag(self) -> object:
            raise ValueError("no diag")

    assert classify_database_failure(wrapped(Raising())) is Category.OTHER
    assert classify_commit_failure(wrapped(Raising())) is Resolution.UNKNOWN
    assert classify_database_failure(wrapped(RaisingDiag())) is Category.OTHER


def test_process_control_while_reading_diagnostics_propagates_as_the_same_object() -> None:
    marker = Stop()

    class Interrupting(Exception):
        @property
        def sqlstate(self) -> str:
            raise marker

    class InterruptingDiag(Exception):
        sqlstate = "23505"

        @property
        def diag(self) -> object:
            raise marker

    for classify in (classify_database_failure, classify_commit_failure):
        with pytest.raises(Stop) as caught:
            classify(wrapped(Interrupting()))
        assert caught.value is marker
    with pytest.raises(Stop) as caught:
        classify_database_failure(wrapped(InterruptingDiag()))
    assert caught.value is marker


@pytest.mark.parametrize(
    ("sqlstate", "constraint", "expected"),
    [
        ("40001", None, Resolution.REJECTED_RETRYABLE),
        ("40P01", None, Resolution.REJECTED_RETRYABLE),
        ("08007", None, Resolution.UNKNOWN),  # transaction_resolution_unknown
        ("40003", None, Resolution.UNKNOWN),  # statement_completion_unknown
        ("23505", REVIEW_KEY_CONSTRAINT, Resolution.UNKNOWN),
        ("55P03", None, Resolution.UNKNOWN),
        ("57014", None, Resolution.UNKNOWN),
        ("08006", None, Resolution.UNKNOWN),
        (None, None, Resolution.UNKNOWN),
        ("40p01", None, Resolution.UNKNOWN),
    ],
)
def test_commit_failures_are_retryable_only_for_exact_serialization_or_deadlock(
    sqlstate: object, constraint: object, expected: Any
) -> None:
    assert classify_commit_failure(failure(sqlstate, constraint)) is expected


def test_classification_reads_no_message_sql_parameters_or_chain() -> None:
    class Loud(DriverError):
        def __str__(self) -> str:
            raise AssertionError("message read")

        def __repr__(self) -> str:
            raise AssertionError("repr read")

    error = wrapped(Loud("40001"))
    error.__cause__ = RuntimeError("chained")
    assert classify_database_failure(error) is Category.SERIALIZATION_FAILURE
    assert classify_commit_failure(error) is Resolution.REJECTED_RETRYABLE
