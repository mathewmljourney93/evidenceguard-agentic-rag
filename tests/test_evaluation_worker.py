"""Database-independent tests of the M4e worker module's boundaries (Prompt 145 corrections;
ADR-0017): complete validation before any database access, the read boundary over the unchanged
``read_snapshot`` helper, vendor creation only after a successful transaction, and the corpus
reader's bounds before payload reads. Session factories, sessions and transactions are doubles;
nothing connects to a database."""

import dataclasses
import os
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

import evidenceguard_retrieval.evaluation.corpus as corpus_module
import evidenceguard_worker.evaluation as evaluation
from evidenceguard_persistence.vendors import DuplicateVendorSlugError
from evidenceguard_retrieval.embeddings import HashingEmbedder
from evidenceguard_retrieval.evaluation.corpus import (
    CLEAN,
    INJECTED,
    EvaluationError,
    build_suite,
)
from evidenceguard_worker.evaluation import (
    LoadedCorpus,
    LoadedRevision,
    TwoEpochState,
    evaluate,
    load_suite,
    run_fresh_two_epoch,
    verify_loaded,
)

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"
MARKER = "PRIVATE-BACKEND-DETAIL-7c1f"
CANARY_AES = b'quote = "LV-TB-CANARY-AES"'
RETENTION_R1 = (
    b'quote = "Customer data is retained for one hundred and eighty (180) days after termination."'
)


class Backend(Exception):
    """An ordinary driver-style failure whose message must never surface."""

    def __init__(self) -> None:
        super().__init__(MARKER)


def _sample_files() -> dict[str, bytes]:
    return {
        p.relative_to(SAMPLE).as_posix(): p.read_bytes() for p in SAMPLE.rglob("*") if p.is_file()
    }


def _with(path: str, old: bytes, new: bytes) -> dict[str, bytes]:
    files = _sample_files()
    assert files[path].count(old) == 1
    files[path] = files[path].replace(old, new)
    return files


def _copy(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "corpus"
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def _code(call: Any) -> str:
    with pytest.raises(EvaluationError) as raised:
        call()
    return raised.value.code


def _private(error: BaseException) -> None:
    text = "".join(traceback.format_exception(error))
    assert MARKER not in text and MARKER not in repr(error)
    assert error.__cause__ is None and error.__context__ is None


@pytest.fixture(scope="module")
def clean() -> Any:
    return load_suite(SAMPLE, CLEAN)


class RefusingFactory:
    """A session factory that records and refuses every access."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Session:
        self.calls += 1
        raise AssertionError("the database must not be touched")


# --- Finding A: complete validation before any database access --------------------------------


def test_load_suite_rejects_a_quote_absent_from_its_source(tmp_path: Path) -> None:
    gt = "ground_truth/halverson-freight.toml"
    files = _with(gt, RETENTION_R1, b'quote = "Customer data is retained forever."')
    assert _code(lambda: load_suite(_copy(tmp_path, files), CLEAN)) == "anchor_not_found"


def test_load_suite_rejects_an_invalid_anchor_used_only_as_forbidden_evidence(
    tmp_path: Path,
) -> None:
    # The Marisol AES canary is only ever a forbidden reference (Halverson's ENC-01).
    files = _with("ground_truth/marisol-clinics.toml", CANARY_AES, b'quote = "LV-TB-CANARY-XYZ"')
    for variant in (CLEAN, INJECTED):
        assert _code(lambda v=variant: load_suite(_copy(tmp_path / v, files), v)) == (
            "anchor_not_found"
        )


def test_a_schema_valid_suite_with_an_unmappable_anchor_never_reaches_the_database() -> None:
    gt = "ground_truth/halverson-freight.toml"
    suite = build_suite(CLEAN, _with(gt, RETENTION_R1, b'quote = "Customer data is retained."'))
    factory = RefusingFactory()
    session_factory = cast(sessionmaker[Session], factory)
    assert _code(lambda: run_fresh_two_epoch(session_factory, suite)) == "anchor_not_found"
    assert _code(lambda: verify_loaded(session_factory, suite)) == "anchor_not_found"
    assert factory.calls == 0


def test_a_supplied_suite_value_is_re_derived_not_trusted(clean: Any) -> None:
    ref = next(iter(sorted(clean.texts)))
    tampered = dataclasses.replace(clean, texts={**clean.texts, ref: "Tampered text.\n"})
    factory = RefusingFactory()
    session_factory = cast(sessionmaker[Session], factory)
    assert _code(lambda: run_fresh_two_epoch(session_factory, tampered)) == "corpus_invalid"
    assert factory.calls == 0


# --- Finding C: the read boundary -----------------------------------------------------------------


class _Result:
    """A result whose ``scalar_one`` raises ``failure`` (if any) after ``execute`` returned."""

    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure

    def scalar_one(self) -> datetime:
        if self.failure is not None:
            raise self.failure
        return datetime(2026, 10, 17, tzinfo=UTC)

    def scalar_one_or_none(self) -> None:
        return None

    def first(self) -> None:
        return None

    def __iter__(self) -> Iterator[Any]:
        return iter(())


class FakeSession:
    """Classifies its statements as the helper's two setup statements, then the body's."""

    def __init__(self, plan: "Plan") -> None:
        self.plan = plan
        self.executed = 0

    def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.executed += 1
        stage = {1: "set", 2: "clock"}.get(self.executed, "body")
        self.plan.log.append(stage)
        failure = self.plan.raises.get(stage)
        if failure is not None:
            raise failure
        return _Result(self.plan.result_raises.get(stage))

    def rollback(self) -> None:
        self.plan.log.append("rollback")
        if self.plan.rollback is not None:
            raise self.plan.rollback

    def close(self) -> None:
        self.plan.log.append("close")
        if self.plan.close is not None:
            raise self.plan.close


@dataclasses.dataclass
class Plan:
    raises: dict[str, BaseException] = dataclasses.field(default_factory=dict)
    rollback: BaseException | None = None
    close: BaseException | None = None
    result_raises: dict[str, BaseException] = dataclasses.field(default_factory=dict)
    log: list[str] = dataclasses.field(default_factory=list)

    def factory(self) -> sessionmaker[Session]:
        return cast(sessionmaker[Session], lambda: FakeSession(self))


def _plan(cleanup: str, raises: dict[str, BaseException] | None = None) -> Plan:
    rollback, close = {
        "none": (None, None),
        "rollback": (Backend(), None),
        "close": (None, Backend()),
        "both": (Backend(), Backend()),
    }[cleanup]
    return Plan(raises=raises or {}, rollback=rollback, close=close)


def _executes_once(session: Session) -> str:
    session.execute(cast(Any, "SELECT 1"))
    return "value"


CONTROLS = [KeyboardInterrupt, lambda: SystemExit(3)]


@pytest.mark.parametrize("cleanup", ["none", "rollback", "close", "both"])
@pytest.mark.parametrize("stage", ["set", "clock", "body"])
@pytest.mark.parametrize("make", CONTROLS, ids=["KeyboardInterrupt", "SystemExit"])
def test_process_control_survives_cleanup_failure(make: Any, stage: str, cleanup: str) -> None:
    control = make()
    plan = _plan(cleanup, {stage: control})
    with pytest.raises(BaseException) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value is control
    assert plan.log[-2:] == ["rollback", "close"]


@pytest.mark.parametrize(
    ("rollback", "close"),
    [
        ("control", None),
        ("control", "ordinary"),
        (None, "control"),
        ("ordinary", "control"),
    ],
)
def test_process_control_raised_by_cleanup_itself_propagates(
    rollback: str | None, close: str | None
) -> None:
    control = KeyboardInterrupt()
    pick = {"control": control, "ordinary": Backend(), None: None}
    plan = Plan(rollback=pick[rollback], close=pick[close])
    with pytest.raises(BaseException) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value is control


@pytest.mark.parametrize("cleanup", ["none", "rollback", "close", "both"])
def test_a_semantic_refusal_survives_cleanup_failure(cleanup: str) -> None:
    def refuse(session: Session) -> str:
        raise EvaluationError("corpus_conflict")

    plan = _plan(cleanup)
    with pytest.raises(EvaluationError) as raised:
        evaluation._read(plan.factory(), refuse)
    assert raised.value.code == "corpus_conflict"
    _private(raised.value)


@pytest.mark.parametrize("cleanup", ["none", "rollback", "close", "both"])
@pytest.mark.parametrize("stage", ["set", "clock", "body"])
def test_ordinary_failures_are_fixed_and_private(stage: str, cleanup: str) -> None:
    plan = _plan(cleanup, {stage: Backend()})
    with pytest.raises(EvaluationError) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value.code == "corpus_read_failed"
    _private(raised.value)


@pytest.mark.parametrize("cleanup", ["rollback", "close", "both"])
def test_a_successful_body_with_failed_cleanup_returns_nothing(cleanup: str) -> None:
    plan = _plan(cleanup)
    with pytest.raises(EvaluationError) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value.code == "corpus_read_failed"
    _private(raised.value)


def test_a_successful_read_returns_its_value() -> None:
    plan = Plan()
    assert evaluation._read(plan.factory(), _executes_once) == "value"
    assert plan.log == ["set", "clock", "body", "rollback", "close"]


def _state(suite: Any) -> TwoEpochState:
    revisions = {
        ref: LoadedRevision(ref, uuid4(), uuid4(), uuid4(), uuid4()) for ref in suite.texts
    }
    return TwoEpochState(LoadedCorpus(revisions, {}), {})


def _entry_points(suite: Any) -> dict[str, Any]:
    return {
        "verify_loaded": lambda f: verify_loaded(f, suite),
        "run_fresh_two_epoch": lambda f: run_fresh_two_epoch(f, suite),
        "evaluate": lambda f: evaluate(f, suite, _state(suite), HashingEmbedder()),
    }


@pytest.mark.parametrize("entry", ["verify_loaded", "run_fresh_two_epoch", "evaluate"])
@pytest.mark.parametrize("make", CONTROLS, ids=["KeyboardInterrupt", "SystemExit"])
def test_entry_points_keep_process_control_through_rollback_failure(
    clean: Any, entry: str, make: Any
) -> None:
    control = make()
    plan = Plan(raises={"set": control}, rollback=Backend())
    with pytest.raises(BaseException) as raised:
        _entry_points(clean)[entry](plan.factory())
    assert raised.value is control


@pytest.mark.parametrize("entry", ["verify_loaded", "run_fresh_two_epoch", "evaluate"])
def test_entry_points_keep_private_fixed_errors_through_cleanup_failure(
    clean: Any, entry: str
) -> None:
    plan = Plan(raises={"body": Backend()}, rollback=Backend(), close=Backend())
    with pytest.raises(EvaluationError) as raised:
        _entry_points(clean)[entry](plan.factory())
    assert raised.value.code == "corpus_read_failed"
    _private(raised.value)


def test_the_verifiers_refusal_survives_rollback_failure(clean: Any) -> None:
    # No tenant row: the verifier's first check refuses; the rollback then fails.
    plan = Plan(rollback=Backend())
    with pytest.raises(EvaluationError) as raised:
        verify_loaded(plan.factory(), clean)
    assert raised.value.code == "corpus_state_incomplete"
    _private(raised.value)


# --- Prompt 146: process control from the setup clock result -------------------------------------


def _clock_result(cleanup: str, failure: BaseException) -> Plan:
    plan = _plan(cleanup)
    plan.result_raises = {"clock": failure}
    return plan


@pytest.mark.parametrize("cleanup", ["none", "rollback", "close", "both"])
@pytest.mark.parametrize("make", CONTROLS, ids=["KeyboardInterrupt", "SystemExit"])
def test_process_control_from_the_clock_result_survives_cleanup_failure(
    make: Any, cleanup: str
) -> None:
    control = make()
    plan = _clock_result(cleanup, control)
    with pytest.raises(BaseException) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value is control
    assert plan.log == ["set", "clock", "rollback", "close"]  # execute returned; no body ran


@pytest.mark.parametrize("cleanup", ["none", "rollback", "close", "both"])
def test_an_ordinary_clock_result_failure_is_fixed_and_private(cleanup: str) -> None:
    plan = _clock_result(cleanup, Backend())
    with pytest.raises(EvaluationError) as raised:
        evaluation._read(plan.factory(), _executes_once)
    assert raised.value.code == "corpus_read_failed"
    _private(raised.value)


@pytest.mark.parametrize("entry", ["verify_loaded", "run_fresh_two_epoch", "evaluate"])
@pytest.mark.parametrize("make", CONTROLS, ids=["KeyboardInterrupt", "SystemExit"])
def test_entry_points_keep_clock_result_process_control_through_rollback_failure(
    clean: Any, entry: str, make: Any
) -> None:
    control = make()
    plan = _clock_result("rollback", control)
    with pytest.raises(BaseException) as raised:
        _entry_points(clean)[entry](plan.factory())
    assert raised.value is control


def test_results_remain_usable_through_the_proxy() -> None:
    def consume(session: Session) -> tuple[Any, ...]:
        result = session.execute(cast(Any, "SELECT 1"))
        rows = list(result)
        return (result.first(), result.scalar_one_or_none(), result.scalar_one(), rows)

    plan = Plan()
    assert evaluation._read(plan.factory(), consume) == (
        None,
        None,
        datetime(2026, 10, 17, tzinfo=UTC),
        [],
    )
    assert plan.log == ["set", "clock", "body", "rollback", "close"]


# --- Finding B: vendor identity only after a successful transaction -------------------------------


class Vendors:
    """Doubles for ``transaction``, ``create_vendor`` and ``list_vendors``."""

    def __init__(
        self,
        *,
        create: BaseException | None = None,
        commit: BaseException | None = None,
        reread: list[tuple[str, str]] | None = None,
    ) -> None:
        self.create_failure = create
        self.commit_failure = commit
        self.reread = reread
        self.created_id = UUID(int=42)
        self.created = False
        self.lookups = 0
        self.log: list[str] = []

    @contextmanager
    def transaction(self, factory: Any) -> Iterator[object]:
        self.log.append("begin")
        try:
            yield object()
        except BaseException:
            self.log.append("rollback")
            raise
        if self.created and self.commit_failure is not None:
            self.log.append("commit-failed")
            failure, self.commit_failure = self.commit_failure, None
            raise failure
        self.log.append("commit")

    def create_vendor(self, session: Any, actor: Any, *, slug: str, name: str) -> Any:
        self.log.append("create")
        if self.create_failure is not None:
            raise self.create_failure
        self.created = True
        return SimpleNamespace(id=self.created_id)

    def list_vendors(self, session: Any, actor: Any, *, limit: int, offset: int) -> Any:
        self.lookups += 1
        items: list[Any] = []
        if self.lookups > 1 and self.reread is not None:
            items = [
                SimpleNamespace(slug=slug, id=UUID(int=7), name=name) for slug, name in self.reread
            ]
        return SimpleNamespace(items=items)


def _ensure(monkeypatch: pytest.MonkeyPatch, suite: Any, doubles: Vendors) -> UUID:
    monkeypatch.setattr(evaluation, "transaction", doubles.transaction)
    monkeypatch.setattr(evaluation, "create_vendor", doubles.create_vendor)
    monkeypatch.setattr(evaluation, "list_vendors", doubles.list_vendors)
    run = evaluation._FreshRun(cast(sessionmaker[Session], RefusingFactory()), suite, None, None)
    return run.ensure_vendor("halverson-freight", "lumenvale-cloud", "Lumenvale Cloud")


def test_a_created_vendor_is_returned_after_commit(
    monkeypatch: pytest.MonkeyPatch, clean: Any
) -> None:
    doubles = Vendors()
    assert _ensure(monkeypatch, clean, doubles) == doubles.created_id
    assert doubles.log[-3:] == ["begin", "create", "commit"]


def test_a_create_failure_is_fixed_and_private(monkeypatch: pytest.MonkeyPatch, clean: Any) -> None:
    with pytest.raises(EvaluationError) as raised:
        _ensure(monkeypatch, clean, Vendors(create=Backend()))
    assert raised.value.code == "corpus_vendor_failed"
    _private(raised.value)


def test_a_commit_failure_after_create_is_not_a_creation(
    monkeypatch: pytest.MonkeyPatch, clean: Any
) -> None:
    doubles = Vendors(commit=Backend())
    with pytest.raises(EvaluationError) as raised:
        _ensure(monkeypatch, clean, doubles)
    assert raised.value.code == "corpus_vendor_failed"
    assert "commit-failed" in doubles.log
    _private(raised.value)


def test_a_duplicate_slug_rolls_back_and_re_reads_a_matching_vendor(
    monkeypatch: pytest.MonkeyPatch, clean: Any
) -> None:
    doubles = Vendors(
        create=DuplicateVendorSlugError(), reread=[("lumenvale-cloud", "Lumenvale Cloud")]
    )
    assert _ensure(monkeypatch, clean, doubles) == UUID(int=7)
    assert doubles.log == ["begin", "commit", "begin", "create", "rollback", "begin", "commit"]
    assert doubles.lookups == 2


@pytest.mark.parametrize(
    ("reread", "code"),
    [([("lumenvale-cloud", "Someone Else")], "corpus_conflict"), ([], "corpus_vendor_failed")],
)
def test_a_duplicate_slug_with_a_mismatched_or_missing_re_read_is_refused(
    monkeypatch: pytest.MonkeyPatch, clean: Any, reread: list[tuple[str, str]], code: str
) -> None:
    doubles = Vendors(create=DuplicateVendorSlugError(), reread=reread)
    with pytest.raises(EvaluationError) as raised:
        _ensure(monkeypatch, clean, doubles)
    assert raised.value.code == code
    _private(raised.value)


@pytest.mark.parametrize("where", ["create", "commit"])
@pytest.mark.parametrize("make", CONTROLS, ids=["KeyboardInterrupt", "SystemExit"])
def test_process_control_during_vendor_creation_propagates(
    monkeypatch: pytest.MonkeyPatch, clean: Any, make: Any, where: str
) -> None:
    control = make()
    doubles = Vendors(**{where: control})
    with pytest.raises(BaseException) as raised:
        _ensure(monkeypatch, clean, doubles)
    assert raised.value is control
    assert doubles.lookups == 1  # never treated as a duplicate


# --- Finding D: aggregate and per-file bounds before payload reads --------------------------------


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Names of the files whose content is read, by ``os.open`` or ``Path.read_bytes``."""
    seen: list[str] = []
    real_open, real_read_bytes = os.open, Path.read_bytes

    def recording_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        seen.append(Path(path).name)
        return real_open(path, flags, *args, **kwargs)

    def recording_read_bytes(self: Path) -> bytes:
        seen.append(self.name)
        return real_read_bytes(self)

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    return seen


def _budget(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    monkeypatch.setattr(corpus_module, "MAX_FILE_SET_BYTES", value)
    monkeypatch.setattr(evaluation, "MAX_FILE_SET_BYTES", value, raising=False)


@pytest.mark.parametrize("variant", [CLEAN, INJECTED])
def test_an_over_budget_file_set_is_rejected_before_payload_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reads: list[str], variant: str
) -> None:
    root = _copy(tmp_path, _sample_files())
    total = sum(len(data) for _, data in load_suite(root, variant).effective_files)
    _budget(monkeypatch, total - 1)
    reads.clear()
    assert _code(lambda: load_suite(root, variant)) == "corpus_too_large"
    assert reads == ["corpus.toml"]


def test_the_injected_budget_covers_the_effective_set_not_the_extra_clean_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy(tmp_path, _sample_files())
    suite = load_suite(root, INJECTED)
    total = sum(len(data) for _, data in suite.effective_files)
    assert len(suite.source_files) == len(suite.effective_files) + 1
    _budget(monkeypatch, total)
    assert load_suite(root, INJECTED).variant == INJECTED


def test_an_oversized_file_is_rejected_before_it_is_read(tmp_path: Path, reads: list[str]) -> None:
    root = _copy(tmp_path, _sample_files())
    target = root / "documents/halverson-freight/lumenvale-cloud/subprocessors@r1.md"
    target.write_bytes(b"x" * (256 * 1024 + 1))
    reads.clear()
    assert _code(lambda: load_suite(root, CLEAN)) == "corpus_too_large"
    assert target.name not in reads


def test_a_file_larger_than_its_reported_size_fails_within_its_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy(tmp_path, _sample_files())
    target = (root / "documents/halverson-freight/lumenvale-cloud/subprocessors@r1.md").resolve()
    real_lstat = os.lstat

    def understated(path: Any, *args: Any, **kwargs: Any) -> Any:
        info = real_lstat(path, *args, **kwargs)
        if Path(path).resolve() == target:
            return SimpleNamespace(st_mode=info.st_mode, st_size=info.st_size - 10)
        return info

    monkeypatch.setattr(os, "lstat", understated)
    assert _code(lambda: load_suite(root, CLEAN)) == "corpus_file_changed"


def test_a_bounded_read_requests_at_most_one_byte_past_the_checked_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.md"
    big.write_bytes(b"y" * (1024 * 1024))
    requested: list[int] = []
    real_fdopen = os.fdopen

    class Recording:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> "Recording":
            return self

        def __exit__(self, *exc: object) -> None:
            self.handle.close()

        def fileno(self) -> int:
            return int(self.handle.fileno())

        def read(self, n: int) -> bytes:
            requested.append(n)
            return bytes(self.handle.read(n))

    monkeypatch.setattr(os, "fdopen", lambda fd, mode: Recording(real_fdopen(fd, mode)))
    assert _code(lambda: evaluation._read_exact(big, 10)) == "corpus_file_changed"
    assert requested == [11]


@pytest.mark.parametrize("variant", [CLEAN, INJECTED])
def test_a_normal_corpus_still_loads(tmp_path: Path, variant: str) -> None:
    suite = load_suite(_copy(tmp_path, _sample_files()), variant)
    assert suite.variant == variant and len(suite.texts) == 12
