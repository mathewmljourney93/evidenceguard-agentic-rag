"""Test-only retrieval-evaluation orchestration (M4e, ADR-0017).

There is no installed command: the PostgreSQL tests are the only callers, always against the
existing guarded disposable test databases. Three contracts:

1. ``run_fresh_two_epoch`` writes, through production seams only, in global phases: validate;
   refuse any existing corpus-tenant state; seed the demo tenants and create vendors; create,
   ingest and index every revision 1; capture and **retain** the ``initial`` snapshots while no
   later revision exists; apply later revisions in manifest order through real ingestion and
   indexing; capture ``final``. Job outcomes are read from the job, revision and index rows,
   never from the worker's exit code; each job allows at most two single-claim worker runs.
2. ``verify_loaded`` is **read-only**: one ``read_snapshot`` transaction (REPEATABLE READ, READ
   ONLY) reads every corpus-tenant record and compares it exactly with the corpus. It seeds,
   creates, enqueues, runs, captures and repairs nothing, and never recreates ``initial``.
3. ``evaluate`` reads stored chunks, resolves every anchor against them and runs the production
   ``search_snapshot`` for both retained epochs, building the report.

Every failure is a fixed ``EvaluationError``; ordinary exceptions from production seams are
converted outside the handler, keeping no message, cause or context. Retrieval errors keep only
their fixed M4d code as ``detail``. ``BaseException`` process control propagates unconverted.

Corrections (Prompt 145):

- Each entry point first re-derives the suite from its own source bytes through the complete
  pure validation (``anchors.revalidate``: schemas, references, and every anchor located and
  mapped to the pinned chunker's offline chunks), so a missing, ambiguous or unmappable anchor is
  refused before any freshness query, seed or creation, whatever ``Suite`` value was supplied.
- ``_read`` is the evaluation's read boundary over the unchanged ``read_snapshot`` helper: a
  session proxy records the first process-control exception raised by any session call or by
  a method of a result ``execute`` returned (Prompt 146: the helper's ``clock_timestamp()``
  ``scalar_one()``), so an ordinary rollback or close failure cannot replace it; a body's fixed
  refusal survives a cleanup failure; any other failure, including cleanup after a successful
  body, is a fresh fixed error and returns no result.
- ``ensure_vendor`` returns a created ID only after its transaction has exited successfully.
- ``load_suite`` checks every needed file's path, type and size, and the effective set's
  aggregate size, before reading any payload; each read is bounded by the size checked.
"""

import hashlib
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import allows_zero_vectors, profile_id
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    RetrievalError,
    RetrievalRequest,
    RetrievalSnapshot,
)
from evidenceguard_domain.revisions import RevisionContent
from evidenceguard_persistence import chunks as chunk_store
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence.accounts import (
    DEMO_TENANTS,
    DatabaseAdminStore,
    demo_tenant_id,
    demo_user_id,
)
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.document_views import create_upload, read_snapshot
from evidenceguard_persistence.models import (
    Document,
    DocumentRevision,
    EmbeddingIndex,
    EmbeddingProfile,
    Job,
    Tenant,
    User,
    UserRole,
)
from evidenceguard_persistence.models import Vendor as VendorRow
from evidenceguard_persistence.retrieval import capture_snapshot
from evidenceguard_persistence.vendors import (
    DuplicateVendorSlugError,
    create_vendor,
    list_vendors,
)
from evidenceguard_retrieval.chunking import CHUNKER_VERSION
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, EmbeddingProvider
from evidenceguard_retrieval.evaluation.anchors import (
    ChunkSpan,
    StoredChunkRow,
    chunk_set,
    resolve_anchor,
    revalidate,
    validate_suite,
    verify_manifest,
)
from evidenceguard_retrieval.evaluation.corpus import (
    CORPUS_FILE,
    EPOCHS,
    FINAL,
    INITIAL,
    MAX_FILE_SET_BYTES,
    VARIANTS,
    EvaluationError,
    RevisionRef,
    Suite,
    effective_paths,
    eligible_revision,
    expected_paths,
    file_limit,
    group_keys,
    parse_corpus,
    validation_paths,
    vendors_with_questions,
)
from evidenceguard_retrieval.evaluation.recall import (
    ChunkOwner,
    EvaluationReport,
    Failure,
    GroupContext,
    GroupReport,
    Profile,
    QuestionReport,
    QuestionRun,
    RankedItem,
    check_question,
    corpus_digest,
)
from evidenceguard_worker.handlers import production_registry
from evidenceguard_worker.ingest import INGEST_REVISION_KIND
from evidenceguard_worker.retrieval import search_snapshot
from evidenceguard_worker.runtime import DatabaseJobStore, Timings, run_worker

INDEX_REVISION_KIND = embedding_store.INDEX_REVISION_KIND
CORPUS_JOB_KINDS = (INGEST_REVISION_KIND, INDEX_REVISION_KIND)
WORKER_ID = "eg-retrieval-evaluation"
MAX_WORKER_RUNS = 2
PHASES = (
    "vendors",
    "first_upload",
    "r1_ingested",
    "r1_indexed",
    "initial_captured",
    "later_revisions",
    "final_captured",
)
_DEMO_SLUGS = frozenset(slug for slug, _ in DEMO_TENANTS)
_FAILED_JOB_STATES = frozenset({"failed", "dead"})
_PENDING_JOB_STATES = frozenset({"queued", "running"})


# --- values ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedRevision:
    ref: RevisionRef
    tenant_id: UUID
    vendor_id: UUID
    document_id: UUID
    revision_id: UUID


@dataclass(frozen=True)
class LoadedCorpus:
    """The logical-to-actual ID map of a loaded corpus."""

    revisions: Mapping[RevisionRef, LoadedRevision]
    vendors: Mapping[tuple[str, str], UUID]


@dataclass(frozen=True)
class TwoEpochState:
    """A fresh run's loaded map and its retained, never persisted, snapshots by
    ``(tenant, vendor, epoch)``."""

    loaded: LoadedCorpus
    snapshots: Mapping[tuple[str, str, str], RetrievalSnapshot]


# --- failure conversion -----------------------------------------------------------------------


def _guard[T](code: str, call: Callable[[], T]) -> T:
    """Run ``call``; keep our own fixed ``EvaluationError``, map an M4d ``RetrievalError`` to
    ``retrieval_failed`` with its fixed code, and any other ordinary exception to ``code``. The
    new error is raised outside the handler, so nothing of the original is retained."""
    results: list[T] = []
    own: tuple[str, str | None] | None = None
    retrieval: str | None = None
    failed = False
    try:
        results.append(call())
    except EvaluationError as error:
        own = (error.code, error.detail)
    except RetrievalError as error:
        retrieval = error.code
    except Exception:
        failed = True
    if own is not None:
        raise EvaluationError(own[0], detail=own[1])
    if retrieval is not None:
        raise EvaluationError("retrieval_failed", detail=retrieval)
    if failed:
        raise EvaluationError(code)
    return results[0]


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EvaluationError(code)


def _validated(suite: Suite) -> Suite:
    """The complete pure validation, re-derived from ``suite``'s own source bytes; nothing the
    caller's ``Suite`` value asserts is trusted (``corpus_invalid`` if it differs)."""
    return _guard("corpus_invalid", lambda: revalidate(suite))


# --- reading the corpus files -------------------------------------------------------------------


def _is_symlink(path: Path) -> bool:
    return stat.S_ISLNK(os.lstat(path).st_mode)


def _checked_path(root: Path, relative: str) -> Path:
    """A manifest-derived path whose every component is a non-symlink, which is a regular file
    and whose resolved path is under the resolved root. Reads no content."""
    path = root
    for part in relative.split("/"):
        path = path / part
        _require(path.exists() or path.is_symlink(), "corpus_file_missing")
        _require(not _is_symlink(path), "corpus_path_invalid")
    _require(stat.S_ISREG(os.lstat(path).st_mode), "corpus_path_invalid")
    _require(path.resolve().is_relative_to(root.resolve()), "corpus_path_invalid")
    return path


def _file_size(path: Path) -> int:
    """The size the file system reports for ``path`` (``lstat``; no content read)."""
    return os.lstat(path).st_size


def _read_exact(path: Path, size: int) -> bytes:
    """Read at most ``size + 1`` bytes from ``path`` (opened without following a final symlink
    where the platform supports it, and re-checked as a regular file), requiring exactly
    ``size`` (``corpus_file_changed`` otherwise)."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        _require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), "corpus_path_invalid")
        data = handle.read(size + 1)
    _require(len(data) == size, "corpus_file_changed")
    return data


def _read_bounded(root: Path, relative: str) -> bytes:
    path = _checked_path(root, relative)
    size = _file_size(path)
    _require(size <= file_limit(relative), "corpus_too_large")
    return _read_exact(path, size)


def _present_files(root: Path) -> set[str]:
    """Every entry under the three content directories, refusing symlinks and non-regular
    files."""
    found: set[str] = set()
    for top in ("documents", "variants", "ground_truth"):
        base = root / top
        if not (base.exists() or base.is_symlink()):
            continue
        _require(not _is_symlink(base) and base.is_dir(), "corpus_path_invalid")
        for directory, subdirectories, names in os.walk(base, followlinks=False):
            for name in subdirectories:
                _require(not _is_symlink(Path(directory) / name), "corpus_path_invalid")
            for name in names:
                path = Path(directory) / name
                _require(stat.S_ISREG(os.lstat(path).st_mode), "corpus_path_invalid")
                found.add(path.relative_to(root).as_posix())
    return found


def load_suite(root: Path, variant: str) -> Suite:
    """Read and completely validate one variant of the corpus under ``root`` (no database work).

    Bounds, in order: ``corpus.toml`` is size-checked (64 KiB) before its bounded read; then,
    before any other payload read, every file ``validation_paths`` names is checked (path,
    regular file, per-file bound) and the effective set's reported sizes, including
    ``corpus.toml``, must total at most ``MAX_FILE_SET_BYTES`` (4 MiB). For the injected variant
    the replaced clean documents are also read; each is bounded per file (256 KiB) and they are
    outside the effective-set total, so a read never exceeds 4 MiB plus 256 KiB per replacement.
    Each read takes at most the checked size plus one byte and must return exactly that size;
    the actual effective total is checked again after reading."""

    def load() -> Suite:
        _require(root.is_dir() and not _is_symlink(root), "corpus_path_invalid")
        _require(variant in VARIANTS, "corpus_variant_invalid")
        corpus_bytes = _read_bounded(root, CORPUS_FILE)
        corpus = parse_corpus(corpus_bytes)
        _require(_present_files(root) <= expected_paths(corpus), "corpus_unexpected_file")
        effective = set(effective_paths(corpus, variant))
        checked: dict[str, tuple[Path, int]] = {}
        for relative in validation_paths(corpus, variant):
            if relative == CORPUS_FILE:
                continue
            path = _checked_path(root, relative)
            size = _file_size(path)
            _require(size <= file_limit(relative), "corpus_too_large")
            checked[relative] = (path, size)
        reported = len(corpus_bytes) + sum(
            size for relative, (_, size) in checked.items() if relative in effective
        )
        _require(reported <= MAX_FILE_SET_BYTES, "corpus_too_large")
        files: dict[str, bytes] = {CORPUS_FILE: corpus_bytes}
        for relative, (path, size) in checked.items():
            files[relative] = _read_exact(path, size)
        actual = sum(len(files[relative]) for relative in effective)
        _require(actual <= MAX_FILE_SET_BYTES, "corpus_too_large")
        return validate_suite(variant, files)

    return _guard("corpus_read_failed", load)


# --- shared helpers -------------------------------------------------------------------------------


def _actor(tenant: str) -> ActorContext:
    _require(tenant in _DEMO_SLUGS, "corpus_invalid")
    return ActorContext(
        tenant_id=demo_tenant_id(tenant),
        actor_id=demo_user_id(tenant, UserRole.REVIEWER),
        role=Role.REVIEWER,
    )


def _tenant_ids(suite: Suite) -> list[UUID]:
    return [demo_tenant_id(t.slug) for t in suite.corpus.tenants]


def _count(session: Session, model: Any, tenant_ids: list[UUID], *extra: Any) -> int:
    count: int = session.execute(
        select(func.count()).select_from(model).where(model.tenant_id.in_(tenant_ids), *extra)
    ).scalar_one()
    return count


def _corpus_state_counts(session: Session, tenant_ids: list[UUID]) -> dict[str, int]:
    return {
        "vendors": _count(session, VendorRow, tenant_ids),
        "documents": _count(session, Document, tenant_ids),
        "revisions": _count(session, DocumentRevision, tenant_ids),
        "profiles": _count(session, EmbeddingProfile, tenant_ids),
        "indexes": _count(session, EmbeddingIndex, tenant_ids),
        "jobs": _count(session, Job, tenant_ids, Job.kind.in_(CORPUS_JOB_KINDS)),
    }


def _job_status(session: Session, tenant_id: UUID, kind: str, key: str) -> str | None:
    status: str | None = session.execute(
        select(Job.status).where(
            Job.tenant_id == tenant_id, Job.kind == kind, Job.idempotency_key == key
        )
    ).scalar_one_or_none()
    return status


class _ReadPending:
    """What one ``_read`` observed: the first process-control exception from any session call,
    the body's fixed refusal, its value, and whether it failed operationally."""

    def __init__(self) -> None:
        self.control: BaseException | None = None
        self.refusal: tuple[str, str | None, Mapping[str, int] | None] | None = None
        self.values: list[Any] = []
        self.operational = False

    def record(self, control: BaseException) -> None:
        if self.control is None:
            self.control = control


def _recording(attribute: Any, pending: _ReadPending) -> Any:
    """``attribute`` itself if not callable; otherwise a wrapper recording a non-``Exception``
    it raises before re-raising it."""
    if not callable(attribute):
        return attribute

    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return attribute(*args, **kwargs)
        except Exception:
            raise
        except BaseException as control:
            pending.record(control)
            raise

    return call


class _RecordingResult:
    """A proxy for a result returned by ``execute`` whose method calls record process control
    the same way (Prompt 145 review: the helper's ``clock_timestamp()`` setup consumes its
    result with ``scalar_one()`` after ``execute`` has returned). Iteration is passed through
    unwrapped; consuming results is the body's, and the body boundary records it."""

    def __init__(self, result: Any, pending: _ReadPending) -> None:
        self._result = result
        self._pending = pending

    def __getattr__(self, name: str) -> Any:
        return _recording(getattr(self._result, name), self._pending)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._result)


class _RecordingSession:
    """A session proxy recording the first non-``Exception`` raised by any session call (the
    helper's setup statements, the body's calls, rollback and close) or by a method of a result
    ``execute`` returned, so that an ordinary cleanup failure replacing it in flight cannot hide
    it."""

    def __init__(self, session: Session, pending: _ReadPending) -> None:
        self._session = session
        self._pending = pending

    def __getattr__(self, name: str) -> Any:
        attribute = _recording(getattr(self._session, name), self._pending)
        if name != "execute":
            return attribute
        pending = self._pending

        def execute(*args: Any, **kwargs: Any) -> _RecordingResult:
            return _RecordingResult(attribute(*args, **kwargs), pending)

        return execute


def _read[T](
    factory: sessionmaker[Session],
    body: Callable[[Session], T],
    code: str = "corpus_read_failed",
) -> T:
    """Run ``body`` in one unchanged ``read_snapshot`` transaction (REPEATABLE READ, READ ONLY).

    Outcomes, in precedence order: a recorded process-control exception is re-raised as the
    same object even if cleanup then failed; a fixed ``EvaluationError`` refusal from the body
    is re-raised fresh (code, detail and counts only) even if cleanup failed; any other failure
    (session setup, the helper's statements, the body, rollback or close, including cleanup
    after a successful body) is a fresh ``EvaluationError(code)`` and returns nothing."""
    pending = _ReadPending()
    environment_failed = False

    def recording_factory() -> Session:
        return cast(Session, _RecordingSession(factory(), pending))

    try:
        with read_snapshot(cast(sessionmaker[Session], recording_factory)) as (session, _now):
            try:
                value = body(session)
            except EvaluationError as refusal:
                pending.refusal = (refusal.code, refusal.detail, refusal.counts)
            except Exception:
                pending.operational = True
            except BaseException as control:
                pending.record(control)
                raise
            else:
                pending.values.append(value)
    except Exception:
        environment_failed = True
    if pending.control is not None:
        interrupted, pending.control = pending.control, None
        raise interrupted
    if pending.refusal is not None:
        refused_code, detail, counts = pending.refusal
        raise EvaluationError(refused_code, detail=detail, counts=counts)
    if pending.operational or environment_failed or not pending.values:
        raise EvaluationError(code)
    result: T = pending.values[0]
    return result


# --- 1. the fresh two-epoch run ---------------------------------------------------------------


class _FreshRun:
    def __init__(
        self,
        factory: sessionmaker[Session],
        suite: Suite,
        timings: Timings | None,
        stop_after: str | None,
    ) -> None:
        _require(stop_after is None or stop_after in PHASES, "invalid_phase")
        self.factory = factory
        self.suite = suite
        self.timings = timings
        self.stop_after = stop_after
        self.vendors: dict[tuple[str, str], UUID] = {}
        self.revisions: dict[RevisionRef, LoadedRevision] = {}

    def phase_done(self, name: str) -> None:
        if self.stop_after == name:
            raise EvaluationError("corpus_run_stopped")

    def run_job(self, tenant_id: UUID, kind: str, key: str) -> None:
        for _ in range(MAX_WORKER_RUNS):
            _guard(
                "corpus_worker_failed",
                lambda: run_worker(
                    DatabaseJobStore(self.factory),
                    production_registry(),
                    worker_id=WORKER_ID,
                    timings=self.timings,
                    once=True,
                ),
            )
            status = _read(self.factory, lambda s: _job_status(s, tenant_id, kind, key))
            if status == "succeeded":
                return
            _require(status not in _FAILED_JOB_STATES, "corpus_job_failed")
        raise EvaluationError("corpus_job_not_settled")

    def revision_status(self, revision_id: UUID) -> str:
        def body(session: Session) -> str:
            status: str = session.execute(
                select(DocumentRevision.status).where(DocumentRevision.id == revision_id)
            ).scalar_one()
            return status

        return _read(self.factory, body)

    def ensure_vendor(self, tenant: str, vendor: str, name: str) -> UUID:
        actor = _actor(tenant)

        def lookup() -> dict[str, tuple[UUID, str]]:
            with transaction(self.factory) as session:
                page = list_vendors(session, actor, limit=100, offset=0)
            return {v.slug: (v.id, v.name) for v in page.items}

        existing = _guard("corpus_vendor_failed", lookup).get(vendor)
        if existing is None:
            committed: UUID | None = None
            duplicate = False
            try:
                with transaction(self.factory) as session:  # rolls back on any failure
                    candidate = create_vendor(session, actor, slug=vendor, name=name).id
                # Reached only after the transaction context exited without raising: commit,
                # flush and cleanup all succeeded.
                committed = candidate
            except DuplicateVendorSlugError:
                duplicate = True  # rolled back; the concurrent vendor is re-read below
            except Exception:
                pass  # any other ordinary failure: never a successful creation
            if committed is not None:
                return committed
            _require(duplicate, "corpus_vendor_failed")
            existing = _guard("corpus_vendor_failed", lookup).get(vendor)
            _require(existing is not None, "corpus_vendor_failed")
        assert existing is not None
        _require(existing[1] == name, "corpus_conflict")
        return existing[0]

    def upload(self, ref: RevisionRef) -> LoadedRevision:
        document = self.suite.corpus.document(ref)
        assert document is not None
        revision = document.revisions[ref.n - 1]
        actor = _actor(ref.tenant)
        vendor_id = self.vendors[(ref.tenant, ref.vendor)]
        content = RevisionContent.from_bytes(
            self.suite.texts[ref].encode("utf-8"), document.media_type
        )

        def create() -> tuple[bool, UUID, UUID]:
            with transaction(self.factory) as session:
                record = create_upload(
                    session,
                    actor,
                    vendor_id=vendor_id,
                    document_key=document.key,
                    title=document.title,
                    source_type=document.source_type,
                    content=content,
                    version_label=revision.version_label,
                    effective_date=revision.effective_date,
                )
            return record.created, record.document_id, record.revision_id

        created, document_id, revision_id = _guard("corpus_upload_failed", create)
        _require(created, "corpus_conflict")
        return LoadedRevision(ref, actor.tenant_id, vendor_id, document_id, revision_id)

    def ingest(self, loaded: LoadedRevision) -> None:
        self.run_job(loaded.tenant_id, INGEST_REVISION_KIND, str(loaded.revision_id))
        status = self.revision_status(loaded.revision_id)
        _require(status != "failed", "corpus_revision_failed")
        _require(status == "active", "corpus_state_unsettled")

    def index(self, loaded: LoadedRevision) -> None:
        actor = _actor(loaded.ref.tenant)

        def enqueue() -> indexing.IndexEnqueueResult:
            with transaction(self.factory) as session:
                return indexing.enqueue_index_revision(
                    session, actor, revision_id=loaded.revision_id, identity=HASH_IDENTITY
                )

        result = _guard("corpus_index_failed", enqueue)
        _require(result.outcome is not indexing.EnqueueOutcome.STALLED, "corpus_index_not_ready")
        if result.outcome is indexing.EnqueueOutcome.PENDING:
            self.run_job(loaded.tenant_id, INDEX_REVISION_KIND, str(result.index.id))

        def status(session: Session) -> str | None:
            value: str | None = session.execute(
                select(EmbeddingIndex.status).where(EmbeddingIndex.id == result.index.id)
            ).scalar_one_or_none()
            return value

        ready = _read(self.factory, status)
        _require(ready == "ready", "corpus_index_not_ready")

    def capture(self, tenant: str, vendor: str, epoch: str) -> RetrievalSnapshot:
        actor = _actor(tenant)
        snapshot = _guard(
            "corpus_capture_failed",
            lambda: capture_snapshot(
                self.factory,
                actor,
                vendor_id=self.vendors[(tenant, vendor)],
                identity=HASH_IDENTITY,
            ),
        )
        expected = set()
        for t in self.suite.corpus.tenants:
            for v in t.vendors:
                if (t.slug, v.slug) != (tenant, vendor):
                    continue
                for d in v.documents:
                    ref = RevisionRef(tenant, vendor, d.key, eligible_revision(d, epoch))
                    expected.add(self.revisions[ref].revision_id)
        bound = {binding.revision_id for binding in snapshot.bindings}
        _require(bound == expected, "corpus_capture_mismatch")
        return snapshot

    def run(self) -> TwoEpochState:
        tenant_ids = _tenant_ids(self.suite)
        counts = _read(self.factory, lambda s: _corpus_state_counts(s, tenant_ids))
        _require(not any(counts.values()), "corpus_state_not_fresh")

        _guard("corpus_seed_failed", lambda: DatabaseAdminStore(self.factory).seed_demo())
        for tenant in self.suite.corpus.tenants:
            for vendor in tenant.vendors:
                self.vendors[(tenant.slug, vendor.slug)] = self.ensure_vendor(
                    tenant.slug, vendor.slug, vendor.name
                )
        self.phase_done("vendors")

        firsts = [ref for ref in self.suite.corpus.revision_refs() if ref.n == 1]
        for position, ref in enumerate(firsts):
            loaded = self.upload(ref)
            self.revisions[ref] = loaded
            if position == 0:
                self.phase_done("first_upload")
            self.ingest(loaded)
        self.phase_done("r1_ingested")
        for ref in firsts:
            self.index(self.revisions[ref])
        self.phase_done("r1_indexed")

        snapshots: dict[tuple[str, str, str], RetrievalSnapshot] = {}
        for tenant_slug, vendor_slug in vendors_with_questions(self.suite):
            snapshots[(tenant_slug, vendor_slug, INITIAL)] = self.capture(
                tenant_slug, vendor_slug, INITIAL
            )
        self.phase_done("initial_captured")

        later = sorted(
            (ref for ref in self.suite.corpus.revision_refs() if ref.n > 1),
            key=lambda r: (r.n, r.tenant, r.vendor, r.document),
        )
        for ref in later:
            loaded = self.upload(ref)
            self.revisions[ref] = loaded
            self.ingest(loaded)
            previous = self.revisions[RevisionRef(ref.tenant, ref.vendor, ref.document, ref.n - 1)]
            _require(
                self.revision_status(previous.revision_id) == "superseded",
                "corpus_state_unsettled",
            )
            self.index(loaded)
        self.phase_done("later_revisions")

        for tenant_slug, vendor_slug in vendors_with_questions(self.suite):
            snapshots[(tenant_slug, vendor_slug, FINAL)] = self.capture(
                tenant_slug, vendor_slug, FINAL
            )
        self.phase_done("final_captured")
        return TwoEpochState(LoadedCorpus(dict(self.revisions), dict(self.vendors)), snapshots)


def run_fresh_two_epoch(
    session_factory: sessionmaker[Session],
    suite: Suite,
    *,
    timings: Timings | None = None,
    stop_after: str | None = None,
) -> TwoEpochState:
    """Load ``suite`` into a fresh database and capture both epochs (see the module docstring).
    ``stop_after`` (a ``PHASES`` name) is a test hook that stops after that phase with
    ``corpus_run_stopped``, leaving the rows committed so far. The suite is completely
    re-validated from its own bytes before any database access."""
    checked = _validated(suite)
    return _FreshRun(session_factory, checked, timings, stop_after).run()


# --- 2. the read-only verifier ----------------------------------------------------------------


def _verify(session: Session, suite: Suite) -> LoadedCorpus:
    corpus = suite.corpus
    revisions: dict[RevisionRef, LoadedRevision] = {}
    vendors: dict[tuple[str, str], UUID] = {}
    fingerprint = HASH_IDENTITY.fingerprint

    for tenant in corpus.tenants:
        tid = demo_tenant_id(tenant.slug)
        _require(
            session.execute(select(Tenant.id).where(Tenant.id == tid)).first() is not None,
            "corpus_state_incomplete",
        )
        reviewer = session.execute(
            select(User.role).where(
                User.tenant_id == tid, User.id == demo_user_id(tenant.slug, UserRole.REVIEWER)
            )
        ).scalar_one_or_none()
        _require(reviewer == UserRole.REVIEWER.value, "corpus_state_incomplete")

        stored_vendors = {
            row.slug: row
            for row in session.execute(
                select(VendorRow.id, VendorRow.slug, VendorRow.name).where(
                    VendorRow.tenant_id == tid
                )
            )
        }
        expected_vendors = {v.slug for v in tenant.vendors}
        _require(expected_vendors <= set(stored_vendors), "corpus_state_incomplete")
        _require(set(stored_vendors) <= expected_vendors, "corpus_state_unexpected")

        documents = list(
            session.execute(
                select(
                    Document.id,
                    Document.vendor_id,
                    Document.document_key,
                    Document.title,
                    Document.source_type,
                    Document.authenticity,
                    Document.latest_revision_no,
                    Document.active_revision_id,
                ).where(Document.tenant_id == tid)
            )
        )
        by_key = {(row.vendor_id, row.document_key): row for row in documents}
        expected_documents = 0
        for vendor in tenant.vendors:
            stored = stored_vendors[vendor.slug]
            _require(stored.name == vendor.name, "corpus_conflict")
            vendors[(tenant.slug, vendor.slug)] = stored.id
            for document in vendor.documents:
                expected_documents += 1
                row = by_key.get((stored.id, document.key))
                _require(row is not None, "corpus_state_incomplete")
                assert row is not None
                _require(
                    row.title == document.title
                    and row.source_type == document.source_type.value
                    and row.authenticity == "not_established",
                    "corpus_conflict",
                )
                stored_revisions = list(
                    session.execute(
                        select(
                            DocumentRevision.id,
                            DocumentRevision.revision_no,
                            DocumentRevision.status,
                            DocumentRevision.media_type,
                            DocumentRevision.version_label,
                            DocumentRevision.effective_date,
                            DocumentRevision.sha256,
                            DocumentRevision.byte_size,
                            DocumentRevision.content_text,
                        )
                        .where(
                            DocumentRevision.tenant_id == tid,
                            DocumentRevision.document_id == row.id,
                        )
                        .order_by(DocumentRevision.revision_no)
                    )
                )
                numbers = [r.revision_no for r in stored_revisions]
                expected_numbers = [r.n for r in document.revisions]
                _require(
                    numbers == expected_numbers,
                    "corpus_state_unexpected"
                    if len(numbers) > len(expected_numbers)
                    else "corpus_state_incomplete",
                )
                _require(row.latest_revision_no == document.latest, "corpus_conflict")
                for revision, stored_revision in zip(
                    document.revisions, stored_revisions, strict=True
                ):
                    ref = RevisionRef(tenant.slug, vendor.slug, document.key, revision.n)
                    data = suite.texts[ref].encode("utf-8")
                    _require(
                        stored_revision.sha256 == hashlib.sha256(data).hexdigest()
                        and stored_revision.byte_size == len(data)
                        and stored_revision.content_text == suite.texts[ref]
                        and stored_revision.media_type == document.media_type.value
                        and stored_revision.version_label == revision.version_label
                        and stored_revision.effective_date == revision.effective_date,
                        "corpus_conflict",
                    )
                    expected_status = "active" if revision.n == document.latest else "superseded"
                    _require(stored_revision.status == expected_status, "corpus_state_unsettled")
                    revisions[ref] = LoadedRevision(ref, tid, stored.id, row.id, stored_revision.id)
                _require(
                    row.active_revision_id == stored_revisions[-1].id, "corpus_state_unsettled"
                )
        _require(len(documents) == expected_documents, "corpus_state_unexpected")

        profiles = list(
            session.execute(
                select(
                    EmbeddingProfile.id,
                    EmbeddingProfile.provider_id,
                    EmbeddingProfile.model_id,
                    EmbeddingProfile.algorithm_version,
                    EmbeddingProfile.dims,
                    EmbeddingProfile.normalization,
                    EmbeddingProfile.fingerprint,
                    EmbeddingProfile.allows_zero_vectors,
                ).where(EmbeddingProfile.tenant_id == tid)
            )
        )
        matching = [p for p in profiles if p.fingerprint == fingerprint]
        _require(bool(matching), "corpus_state_incomplete")
        profile = matching[0]
        _require(
            profile.id == profile_id(tid, fingerprint)
            and profile.provider_id == HASH_IDENTITY.provider_id
            and profile.model_id == HASH_IDENTITY.model_id
            and profile.algorithm_version == HASH_IDENTITY.algorithm_version
            and profile.dims == HASH_IDENTITY.dims
            and profile.normalization == HASH_IDENTITY.normalization
            and profile.allows_zero_vectors == allows_zero_vectors(HASH_IDENTITY),
            "corpus_conflict",
        )
        _require(len(profiles) == 1, "corpus_state_unexpected")

        tenant_revisions = {r.revision_id for r in revisions.values() if r.tenant_id == tid}
        indexes = list(
            session.execute(select(EmbeddingIndex.__table__).where(EmbeddingIndex.tenant_id == tid))
        )
        by_revision = {row.revision_id: row for row in indexes}
        _require(tenant_revisions <= set(by_revision), "corpus_index_not_ready")
        _require(len(indexes) == len(tenant_revisions), "corpus_state_unexpected")
        index_ids: set[str] = set()
        for revision_id in tenant_revisions:
            index_row = by_revision[revision_id]
            snapshot = embedding_store.IndexSnapshot(
                **{name: index_row._mapping[name] for name in embedding_store.INDEX_FIELDS}
            )
            chunk_set_row = session.execute(
                chunk_store.chunk_set_statement(tid, revision_id)
            ).first()
            _require(chunk_set_row is not None, "corpus_state_incomplete")
            assert chunk_set_row is not None
            embedded = session.execute(
                embedding_store.embedding_count_statement(snapshot)
            ).scalar_one()
            _require(
                index_row.profile_id == profile.id
                and index_row.status == "ready"
                and index_row.vector_manifest_sha256 is not None
                and index_row.chunker_version == chunk_set_row.chunker_version
                and index_row.chunk_count == chunk_set_row.chunk_count
                and embedded == chunk_set_row.chunk_count,
                "corpus_index_not_ready",
            )
            index_ids.add(str(index_row.id))

        jobs = list(
            session.execute(
                select(Job.kind, Job.idempotency_key, Job.status).where(
                    Job.tenant_id == tid, Job.kind.in_(CORPUS_JOB_KINDS)
                )
            )
        )
        ingest_keys = {str(r) for r in tenant_revisions}
        expected_jobs = {(INGEST_REVISION_KIND, k) for k in ingest_keys} | {
            (INDEX_REVISION_KIND, k) for k in index_ids
        }
        stored_jobs = {(job.kind, job.idempotency_key): job.status for job in jobs}
        _require(expected_jobs <= set(stored_jobs), "corpus_job_not_settled")
        _require(set(stored_jobs) <= expected_jobs, "corpus_state_unexpected")
        for status in stored_jobs.values():
            _require(status not in _FAILED_JOB_STATES, "corpus_job_failed")
            _require(status == "succeeded", "corpus_job_not_settled")

    for ref, loaded in revisions.items():
        stored_document = corpus.document(ref)
        assert stored_document is not None
        _manifest_spans(session, loaded, suite.texts[ref], stored_document.media_type)
    return LoadedCorpus(revisions, vendors)


def _manifest_spans(
    session: Session, loaded: LoadedRevision, text: str, media_type: Any
) -> tuple[ChunkSpan, ...]:
    chunk_set_row = session.execute(
        chunk_store.chunk_set_statement(loaded.tenant_id, loaded.revision_id)
    ).first()
    _require(chunk_set_row is not None, "corpus_state_incomplete")
    assert chunk_set_row is not None
    rows = [
        StoredChunkRow(
            id=row.id,
            ordinal=row.ordinal,
            content_sha256=row.content_sha256,
            section_path=tuple(row.section_path),
            is_table=row.is_table,
            line_start=row.line_start,
            line_end=row.line_end,
            char_start=row.char_start,
            char_end=row.char_end,
            header_line_start=row.header_line_start,
            header_line_end=row.header_line_end,
            header_char_start=row.header_char_start,
            header_char_end=row.header_char_end,
        )
        for row in session.execute(
            chunk_store.manifest_rows_statement(
                loaded.tenant_id, loaded.revision_id, chunk_set_row.chunker_version
            )
        )
    ]
    _require(len(rows) == chunk_set_row.chunk_count, "mapping_manifest_mismatch")
    return verify_manifest(
        text=text,
        media_type=media_type,
        tenant_id=loaded.tenant_id,
        revision_id=loaded.revision_id,
        chunker_version=chunk_set_row.chunker_version,
        stored_manifest_sha256=chunk_set_row.manifest_sha256,
        rows=rows,
    )


def verify_loaded(session_factory: sessionmaker[Session], suite: Suite) -> LoadedCorpus:
    """Verify an already loaded corpus without writing anything (see the module docstring)."""
    checked = _validated(suite)
    return _read(session_factory, lambda session: _verify(session, checked))


# --- 3. evaluation ----------------------------------------------------------------------------


def _stored_spans(
    factory: sessionmaker[Session], suite: Suite, loaded: LoadedCorpus
) -> dict[RevisionRef, tuple[ChunkSpan, ...]]:
    def body(session: Session) -> dict[RevisionRef, tuple[ChunkSpan, ...]]:
        spans: dict[RevisionRef, tuple[ChunkSpan, ...]] = {}
        for ref, revision in sorted(loaded.revisions.items()):
            document = suite.corpus.document(ref)
            assert document is not None
            content: str | None = session.execute(
                select(DocumentRevision.content_text).where(
                    DocumentRevision.tenant_id == revision.tenant_id,
                    DocumentRevision.id == revision.revision_id,
                )
            ).scalar_one_or_none()
            _require(content == suite.texts[ref], "corpus_conflict")
            spans[ref] = _manifest_spans(session, revision, suite.texts[ref], document.media_type)
        return spans

    return _read(factory, body)


def evaluate(
    session_factory: sessionmaker[Session],
    suite: Suite,
    state: TwoEpochState,
    provider: EmbeddingProvider,
) -> EvaluationReport:
    """Resolve the ground truth against stored chunks and run the production retrieval for both
    retained epochs (see the module docstring)."""
    suite = _validated(suite)
    loaded = state.loaded
    _require(set(loaded.revisions) == set(suite.corpus.revision_refs()), "corpus_state_incomplete")
    spans = _stored_spans(session_factory, suite, loaded)

    anchor_chunks = {
        ref: chunk_set(resolve_anchor(anchor, suite.texts[ref.revision], spans[ref.revision]))
        for ref, anchor in sorted(suite.anchors.items())
    }
    owners: dict[UUID, ChunkOwner] = {}
    revision_chunks: dict[UUID, frozenset[UUID]] = {}
    for ref, chunk_spans in spans.items():
        ids = frozenset(span.chunk_id for span in chunk_spans)
        revision_chunks[loaded.revisions[ref].revision_id] = ids
        for chunk_id in ids:
            owners[chunk_id] = ChunkOwner(ref.tenant, ref.vendor, str(ref))

    keys = group_keys(suite)
    _require(all(key in state.snapshots for key in keys), "corpus_state_incomplete")
    first = state.snapshots[keys[0]]
    for key in keys:
        snapshot = state.snapshots[key]
        _require(
            snapshot.identity == first.identity
            and snapshot.config.config_sha256 == first.config.config_sha256
            and snapshot.config.config_sha256 == RETRIEVAL_CONFIG_V1.config_sha256,
            "profile_mismatch",
        )

    groups: list[GroupReport] = []
    contract: list[Failure] = []
    isolation: list[Failure] = []
    for tenant, vendor, epoch in keys:
        snapshot = state.snapshots[(tenant, vendor, epoch)]
        snapshot_chunks = frozenset().union(
            *(revision_chunks[b.revision_id] for b in snapshot.bindings)
        )
        context = GroupContext(
            tenant,
            vendor,
            epoch,
            snapshot.sha256,
            snapshot.identity.fingerprint,
            snapshot.config.config_sha256,
            snapshot_chunks,
            owners,
        )
        actor = _actor(tenant)
        questions: list[QuestionReport] = []
        for question in sorted(
            (q for q in suite.questions() if (q.tenant, q.vendor) == (tenant, vendor)),
            key=lambda q: q.id,
        ):
            case = question.case_for(epoch)
            if case is None:
                continue
            gold = frozenset().union(*(anchor_chunks[r] for r in case.gold))
            forbidden = frozenset().union(*(anchor_chunks[r] for r in case.forbidden))
            _require(gold <= snapshot_chunks, "gold_not_in_snapshot")
            _require(not gold & forbidden, "gold_forbidden_conflict")
            canaries = tuple(
                suite.anchors[r].quote for r in case.forbidden if r.revision.tenant != tenant
            )
            request = RetrievalRequest(question.search_queries, k=8)
            result = _guard(
                "retrieval_failed",
                partial(search_snapshot, session_factory, actor, snapshot, request, provider),
            )
            run = QuestionRun(
                question.id,
                tuple(
                    RankedItem(position, item.chunk_id, item.fused_rank)
                    for position, item in enumerate(result.items, start=1)
                ),
                result.snapshot_sha256,
                result.profile_fingerprint,
                result.config_sha256,
                {item.chunk_id: item.evidence.text for item in result.items},
                gold,
                forbidden,
                canaries,
            )
            report, contract_failures, isolation_failures = check_question(context, run)
            questions.append(report)
            contract.extend(contract_failures)
            isolation.extend(isolation_failures)
        groups.append(GroupReport(tenant, vendor, epoch, snapshot.sha256, tuple(questions)))

    identity = first.identity
    return EvaluationReport(
        suite.variant,
        corpus_digest(suite.variant, suite.effective_files),
        CHUNKER_VERSION,
        first.config.config_sha256,
        Profile(
            identity.provider_id,
            identity.model_id,
            identity.algorithm_version,
            identity.dims,
            identity.fingerprint,
            first.profile_label,
        ),
        tuple(groups),
        tuple(contract),
        tuple(isolation),
    )


__all__ = [
    "EPOCHS",
    "PHASES",
    "LoadedCorpus",
    "LoadedRevision",
    "TwoEpochState",
    "evaluate",
    "load_suite",
    "run_fresh_two_epoch",
    "verify_loaded",
]
