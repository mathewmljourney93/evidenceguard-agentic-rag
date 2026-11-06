"""G15: the first-process-control rule of ``transaction()`` (M5g-E3, ADR-0025).

Every combination of body, commit, rollback and close outcomes is driven through the real helper
with a scripted session. Expected results come from two independent oracles written here: the
E3 decision table (the first ``BaseException`` that is not an ``Exception`` wins by identity) and,
for ordinary-only failures, a verbatim copy of the helper as published before M5g (the object it
selected and the calls it made). No database is used.
"""

import itertools
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from evidenceguard_persistence.db import transaction

Outcome = str  # "ok", "ordinary" or a process-control class name
CONTROLS: dict[str, type[BaseException]] = {
    "KeyboardInterrupt": KeyboardInterrupt,
    "SystemExit": SystemExit,
    "GeneratorExit": GeneratorExit,
}
OUTCOMES = ("ok", "ordinary", *CONTROLS)


class Ordinary(Exception):
    """An ordinary failure carrying a label (never inspected by the helper)."""


def make(label: str, outcome: Outcome) -> BaseException | None:
    if outcome == "ok":
        return None
    if outcome == "ordinary":
        return Ordinary(label)
    return CONTROLS[outcome]()


class Session:
    def __init__(self, script: dict[str, BaseException | None]) -> None:
        self.script = script
        self.calls: list[str] = []

    def _call(self, name: str) -> None:
        self.calls.append(name)
        error = self.script.get(name)
        if error is not None:
            raise error

    def commit(self) -> None:
        self._call("commit")

    def rollback(self) -> None:
        self._call("rollback")

    def close(self) -> None:
        self._call("close")


def run(helper: Any, session: Session, body: BaseException | None) -> BaseException | None:
    try:
        with helper(lambda: session):
            if body is not None:
                raise body
    except BaseException as escaped:  # handed to the assertions
        return escaped
    return None


@contextmanager
def published_helper(session_factory: Any) -> Iterator[Any]:
    """The ``transaction()`` helper exactly as published before M5g (the ordinary oracle)."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def expected(
    body: BaseException | None,
    commit: BaseException | None,
    rollback: BaseException | None,
    close: BaseException | None,
) -> tuple[BaseException | None, list[str]]:
    """The E3 decision table: calls in order, then the first process-control object, else the
    last ordinary failure."""
    calls: list[str] = []
    failures: list[BaseException] = []
    if body is not None:
        failures.append(body)
    else:
        calls.append("commit")
        if commit is not None:
            failures.append(commit)
    if failures:
        calls.append("rollback")
        if rollback is not None:
            failures.append(rollback)
    calls.append("close")
    if close is not None:
        failures.append(close)
    controls = [f for f in failures if not isinstance(f, Exception)]
    if controls:
        return controls[0], calls
    return (failures[-1] if failures else None), calls


COMBINATIONS = list(itertools.product(OUTCOMES, repeat=4))


@pytest.mark.parametrize(("body", "commit", "rollback", "close"), COMBINATIONS)
def test_every_phase_combination_follows_the_first_process_control_rule(
    body: Outcome, commit: Outcome, rollback: Outcome, close: Outcome
) -> None:
    errors = {
        "body": make("body", body),
        "commit": make("commit", commit),
        "rollback": make("rollback", rollback),
        "close": make("close", close),
    }
    session = Session({k: v for k, v in errors.items() if k != "body"})
    raised = run(transaction, session, errors["body"])
    want, calls = expected(errors["body"], errors["commit"], errors["rollback"], errors["close"])
    assert raised is want  # identity, not equality
    assert session.calls == calls
    assert session.calls.count("commit") <= 1 and session.calls.count("rollback") <= 1
    assert session.calls.count("close") == 1


ORDINARY_ONLY = list(itertools.product(("ok", "ordinary"), repeat=4))


@pytest.mark.parametrize(("body", "commit", "rollback", "close"), ORDINARY_ONLY)
def test_without_process_control_the_published_helper_selection_is_unchanged(
    body: Outcome, commit: Outcome, rollback: Outcome, close: Outcome
) -> None:
    errors = {name: make(name, value) for name, value in zip(
        ("body", "commit", "rollback", "close"), (body, commit, rollback, close), strict=True
    )}  # fmt: skip
    script = {k: v for k, v in errors.items() if k != "body"}
    new_session, old_session = Session(script), Session(script)
    new = run(transaction, new_session, errors["body"])
    old = run(published_helper, old_session, errors["body"])
    assert new is old
    assert new_session.calls == old_session.calls


def test_the_ordinary_only_matrix_has_the_sixteen_reviewed_combinations() -> None:
    assert len(ORDINARY_ONLY) == 16 and len(COMBINATIONS) == 625


def test_a_fixed_error_raised_outside_handlers_keeps_no_cause_or_context() -> None:
    class Fixed(Exception):
        def __init__(self) -> None:
            super().__init__("fixed")

    error = Fixed()
    session = Session({})
    assert run(transaction, session, error) is error
    assert error.__cause__ is None and error.__context__ is None
    assert session.calls == ["rollback", "close"]


@pytest.mark.parametrize("failure", [Ordinary("construction"), *(c() for c in CONTROLS.values())])
def test_a_failed_session_construction_makes_no_lifecycle_call(failure: BaseException) -> None:
    attempted: list[str] = []

    def factory() -> Any:
        attempted.append("factory")
        raise failure

    with pytest.raises(type(failure)) as raised, transaction(cast(Any, factory)):
        attempted.append("body")
    assert raised.value is failure
    assert attempted == ["factory"]  # no body, commit, rollback or close


def test_generator_exit_thrown_at_the_yield_is_re_raised_as_the_same_object() -> None:
    # contextlib must hand back the same GeneratorExit object the generator re-raises.
    control = GeneratorExit()
    session = Session({"rollback": Ordinary("rollback"), "close": KeyboardInterrupt()})
    assert run(transaction, session, control) is control
    assert session.calls == ["rollback", "close"]


def test_a_committed_transaction_whose_close_raises_raises_after_the_commit() -> None:
    session = Session({"close": Ordinary("close")})
    raised = run(transaction, session, None)
    assert isinstance(raised, Ordinary) and session.calls == ["commit", "close"]


def test_the_published_helper_lost_the_first_process_control_object() -> None:
    # The limit G15 removes (M5g-E): a rollback failure replaced the body's control object.
    control = KeyboardInterrupt()
    replacement = Ordinary("rollback")
    old = run(published_helper, Session({"rollback": replacement}), control)
    assert old is replacement
    assert run(transaction, Session({"rollback": Ordinary("rollback")}), control) is control
