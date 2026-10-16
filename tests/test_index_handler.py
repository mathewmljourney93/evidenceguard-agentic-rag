"""The ``index_revision`` handler with scripted doubles (M4c, ADR-0015).

A fake ``JobContext`` records every fenced block and ``check()``; the persistence reads and
writes the handler calls are replaced by recorders, and providers are injected only through
``make_index_revision_handler``. The tests check the accepted protocol: the target read,
stored-identity verification before provider resolution, the immutable provider mapping, page
caps and cursor, hash verification, computation outside every fence with checks around it,
latched cancellation or lease loss winning over a provider failure, the failure mapping, and the
already-ready and write-refused paths. Real PostgreSQL execution and the runtime's recorded
outcomes are in ``test_indexing_postgres.py`` (CI only).
"""

import hashlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from evidenceguard_domain.embedding_storage import index_id, profile_id
from evidenceguard_domain.embeddings import EmbeddingBatch, EmbeddingIdentity, InputType
from evidenceguard_domain.jobs import (
    JobErrorCode,
    JobPayload,
    JobSnapshot,
    JobStatus,
    LeaseLostError,
)
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing as index_store
from evidenceguard_persistence.embeddings import IndexSnapshot, ProfileSnapshot
from evidenceguard_persistence.indexing import PendingChunk
from evidenceguard_persistence.jobs import FenceClosedError, FencedSession, JobLockTimeoutError
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_worker import indexing
from evidenceguard_worker.context import (
    HandlerFence,
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)

T0 = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
VERSION = "text-md-v1"
PROFILE = profile_id(TENANT, HASH_IDENTITY.fingerprint)
INDEX = index_id(TENANT, REVISION, VERSION, PROFILE)
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
TEXT_MARKER = "synthetic-private-chunk-text-marker"


def _job(payload: dict[str, str] | None = None) -> JobSnapshot:
    return JobSnapshot(
        id=UUID(int=7),
        tenant_id=TENANT,
        kind="index_revision",
        idempotency_key=str(INDEX),
        payload=JobPayload.from_mapping(payload or {"index_id": str(INDEX)}),
        status=JobStatus.RUNNING,
        attempt=1,
        max_attempts=3,
        run_after=T0,
        locked_by="worker-test",
        lease_expires_at=T0 + timedelta(seconds=60),
        created_at=T0,
        updated_at=T0,
    )


def _index(status: str = "building", chunk_count: int = 2) -> IndexSnapshot:
    return IndexSnapshot(
        id=INDEX,
        tenant_id=TENANT,
        revision_id=REVISION,
        chunker_version=VERSION,
        chunk_count=chunk_count,
        manifest_sha256="a" * 64,
        profile_id=PROFILE,
        dims=1024,
        allows_zero_vectors=True,
        status=status,
        vector_manifest_sha256="f" * 64 if status == "ready" else None,
        ready_at=T0 if status == "ready" else None,
    )


def _profile(**changes: Any) -> ProfileSnapshot:
    values: dict[str, Any] = {
        "id": PROFILE,
        "tenant_id": TENANT,
        "provider_id": "offline",
        "model_id": "fake-hash-v1",
        "algorithm_version": "ascii-word-sha256-v1",
        "dims": 1024,
        "normalization": "l2",
        "fingerprint": HASH_IDENTITY.fingerprint,
        "allows_zero_vectors": True,
    }
    values.update(changes)
    return ProfileSnapshot(**values)


def _chunk(ordinal: int, text: str | None = None) -> PendingChunk:
    body = text if text is not None else f"Chunk {ordinal} {TEXT_MARKER}."
    return PendingChunk(
        ordinal=ordinal,
        id=UUID(int=1000 + ordinal),
        text=body,
        content_sha256=hashlib.sha256(body.encode()).hexdigest(),
    )


# --- doubles ---------------------------------------------------------------------------------


@dataclass
class Script:
    events: list[str] = field(default_factory=list)
    index: IndexSnapshot = field(default_factory=_index)
    profile: ProfileSnapshot = field(default_factory=_profile)
    chunks: list[PendingChunk] = field(default_factory=lambda: [_chunk(0), _chunk(1)])
    written: list[tuple[UUID, ...]] = field(default_factory=list)
    reads: list[int] = field(default_factory=list)
    errors: dict[str, BaseException] = field(default_factory=dict)
    in_fence: bool = False
    latch_on_check: int | None = None
    latch_error: BaseException = field(default_factory=JobCancelledError)
    checks: int = 0
    latched: bool = False

    def raise_for(self, name: str) -> None:
        error = self.errors.pop(name, None)
        if error is not None:
            raise error


class FakeContext:
    def __init__(self, script: Script, job: JobSnapshot) -> None:
        self._script = script
        self.job = job

    def check(self) -> None:
        script = self._script
        script.checks += 1
        script.events.append("check")
        if script.latch_on_check == script.checks:
            script.latched = True
        if script.latched:
            raise script.latch_error

    @contextmanager
    def fenced(self, *, finish: bool = False) -> Iterator[HandlerFence]:
        script = self._script
        self.check()  # like JobContext: before opening the transaction ...
        script.events.append("open_finish" if finish else "open")
        script.in_fence = True
        try:
            self.check()  # ... and again after acquiring the job lock
            yield HandlerFence(cast(FencedSession, object()), self.job)
            if finish:
                self.check()
                script.events.append("succeed")
            script.events.append("commit")
        except BaseException:
            script.events.append("rollback")
            raise
        finally:
            script.in_fence = False


class RecordingProvider:
    """The offline embedder, recording calls and asserting they happen outside every fence."""

    def __init__(
        self,
        script: Script,
        identity: EmbeddingIdentity = HASH_IDENTITY,
        on_call: Callable[[], None] | None = None,
        fail: bool = False,
    ) -> None:
        self._script = script
        self._identity = identity
        self._on_call = on_call
        self._fail = fail
        self.calls: list[tuple[str, ...]] = []

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        assert not self._script.in_fence, "provider computation must run outside every fence"
        self._script.events.append("provider")
        self.calls.append(texts)
        if self._on_call is not None:
            self._on_call()
        if self._fail:
            raise RuntimeError(f"provider failure with {TEXT_MARKER}")
        return HashingEmbedder().embed(texts, input_type)


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    state = Script()

    def load_index_target(session: Any, job: JobSnapshot) -> Any:
        assert state.in_fence
        state.events.append("read_target")
        state.raise_for("read_target")
        return state.index, state.profile

    def pending_chunks(session: Any, job: JobSnapshot, index: Any, *, after_ordinal: int) -> Any:
        assert state.in_fence
        state.events.append("read_page")
        state.reads.append(after_ordinal)
        state.raise_for("read_page")
        done = {chunk_id for batch in state.written for chunk_id in batch}
        return tuple(
            chunk
            for chunk in state.chunks
            if chunk.ordinal > after_ordinal and chunk.id not in done
        )[:32]

    def write_embeddings(session: Any, job: JobSnapshot, identity: Any, rows: Any) -> None:
        assert state.in_fence
        state.events.append("write")
        state.raise_for("write")
        state.written.append(tuple(row.chunk_id for row in rows))

    def mark_index_ready(session: Any, job: JobSnapshot, identity: Any) -> Any:
        assert state.in_fence
        state.events.append("mark_ready")
        state.raise_for("mark_ready")
        return state.index

    monkeypatch.setattr(index_store, "load_index_target", load_index_target)
    monkeypatch.setattr(index_store, "pending_chunks", pending_chunks)
    monkeypatch.setattr(embedding_store, "write_embeddings", write_embeddings)
    monkeypatch.setattr(embedding_store, "mark_index_ready", mark_index_ready)
    return state


def _run(
    script: Script,
    provider: Any = None,
    providers: Mapping[str, Any] | None = None,
    job: JobSnapshot | None = None,
) -> Any:
    chosen = provider if provider is not None else RecordingProvider(script)
    mapping = providers if providers is not None else {HASH_IDENTITY.fingerprint: lambda: chosen}
    handler = indexing.make_index_revision_handler(mapping)
    handler(cast(JobContext, FakeContext(script, job or _job())))
    return chosen


# --- the normal path ---------------------------------------------------------------------------


def test_a_building_index_is_read_embedded_written_and_finished(script: Script) -> None:
    provider = _run(script)

    assert script.events == [
        "check", "open", "check", "read_target", "commit",
        "check", "open", "check", "read_page", "commit",
        "check", "provider", "check",
        "check", "open", "check", "write", "commit",
        "check", "open", "check", "read_page", "commit",
        "check", "open_finish", "check", "mark_ready", "check", "succeed", "commit",
    ]  # fmt: skip
    assert provider.calls == [tuple(chunk.text for chunk in script.chunks)]
    assert script.written == [tuple(chunk.id for chunk in script.chunks)]
    assert script.reads == [-1, 1]


def test_an_already_ready_index_finishes_without_reading_pages_or_a_provider(
    script: Script,
) -> None:
    script.index = _index("ready")
    provider = _run(script)
    assert provider.calls == []
    assert script.events == [
        "check", "open", "check", "read_target", "commit",
        "check", "open_finish", "check", "mark_ready", "check", "succeed", "commit",
    ]  # fmt: skip


def test_pages_respect_both_caps_and_the_cursor_follows_the_kept_prefix(script: Script) -> None:
    # 40 chunks of 4,000 code points (3,999 four-byte characters plus one digit: 15,997 UTF-8
    # bytes each, within M4a's per-input limits): only 8 fit in 128,000 bytes.
    script.chunks = [_chunk(i, "😀" * 3999 + str(i % 10)) for i in range(40)]
    script.index = _index(chunk_count=40)
    provider = _run(script)

    assert [len(call) for call in provider.calls] == [8, 8, 8, 8, 8]
    for call in provider.calls:
        assert sum(len(text.encode("utf-8")) for text in call) <= indexing.PAGE_BYTES
    assert script.reads == [-1, 7, 15, 23, 31, 39]  # last kept ordinal, never a discarded one


def test_at_most_32_chunks_per_page() -> None:
    page = tuple(_chunk(i, "x") for i in range(40))
    assert len(indexing.page_prefix(page[:32])) == 32
    assert indexing.page_prefix(()) == ()


def test_the_byte_boundary_is_inclusive_with_multibyte_text() -> None:
    exact = [_chunk(0, "é" * 64000)]  # exactly 128,000 UTF-8 bytes
    assert len(indexing.page_prefix(exact)) == 1
    over = [_chunk(0, "é" * 63999), _chunk(1, "ab"), _chunk(2, "c")]  # 127,998 + 2 + 1
    assert [c.ordinal for c in indexing.page_prefix(over)] == [0, 1]


def test_committed_rows_are_not_recomputed(script: Script) -> None:
    script.written = [(script.chunks[0].id,)]  # committed by an earlier attempt
    provider = _run(script)
    assert provider.calls == [(script.chunks[1].text,)]


def test_a_write_refused_because_the_index_became_ready_finishes_with_the_no_op(
    script: Script,
) -> None:
    script.errors["write"] = embedding_store.EmbeddingWriteRefusedError()
    _run(script)
    position = script.events.index("write")
    assert script.events[position:] == [
        "write", "rollback",
        "check", "open_finish", "check", "mark_ready", "check", "succeed", "commit",
    ]  # fmt: skip
    assert script.written == []


# --- identity and provider selection --------------------------------------------------------


def test_the_production_mapping_contains_only_the_offline_identity() -> None:
    assert dict(indexing.SUPPORTED_PROVIDERS) == {HASH_IDENTITY.fingerprint: HashingEmbedder}
    with pytest.raises(TypeError):
        indexing.SUPPORTED_PROVIDERS["x"] = HashingEmbedder  # type: ignore[index]


def test_the_mapping_is_copied_when_the_handler_is_built(script: Script) -> None:
    provider = RecordingProvider(script)
    mapping: dict[str, Any] = {HASH_IDENTITY.fingerprint: lambda: provider}
    handler = indexing.make_index_revision_handler(mapping)
    mapping.clear()  # later mutation has no effect
    handler(cast(JobContext, FakeContext(script, _job())))
    assert provider.calls != []


@pytest.mark.parametrize(
    "mapping", [{1: HashingEmbedder}, {HASH_IDENTITY.fingerprint: "not callable"}]
)
def test_an_invalid_mapping_is_refused_when_the_handler_is_built(mapping: Any) -> None:
    with pytest.raises(TypeError):
        indexing.make_index_revision_handler(mapping)


@pytest.mark.parametrize(
    "profile",
    [
        _profile(fingerprint="0" * 64),  # stored fields do not hash to the stored fingerprint
        _profile(normalization="none"),
        _profile(dims=0),
    ],
)
def test_the_stored_identity_is_verified_before_any_provider_is_resolved(
    script: Script, profile: ProfileSnapshot
) -> None:
    script.profile = profile
    built: list[str] = []

    def factory() -> Any:
        built.append("built")
        return RecordingProvider(script)

    with pytest.raises(PermanentJobError) as info:
        _run(script, providers={HASH_IDENTITY.fingerprint: factory, "0" * 64: factory})
    assert info.value.code is JobErrorCode.PERMANENT_FAILURE
    assert built == [] and "read_page" not in script.events


def test_an_unsupported_profile_fails_permanently(script: Script) -> None:
    script.profile = _profile(
        provider_id="voyage",
        model_id="voyage-4-lite",
        algorithm_version="adapter-v1",
        fingerprint=LIVE.fingerprint,
        allows_zero_vectors=False,
    )
    with pytest.raises(PermanentJobError):
        _run(script)  # the mapping has only the offline identity
    assert "read_page" not in script.events


def test_a_provider_with_another_identity_fails_permanently(script: Script) -> None:
    with pytest.raises(PermanentJobError):
        _run(script, provider=RecordingProvider(script, identity=LIVE))
    assert "read_page" not in script.events


def test_a_broken_provider_factory_fails_permanently(script: Script) -> None:
    def factory() -> Any:
        raise RuntimeError(TEXT_MARKER)

    with pytest.raises(PermanentJobError) as info:
        _run(script, providers={HASH_IDENTITY.fingerprint: factory})
    assert TEXT_MARKER not in str(info.value)


# --- source integrity and failures -----------------------------------------------------------


def test_a_text_hash_mismatch_fails_before_any_provider_call(script: Script) -> None:
    bad = PendingChunk(ordinal=0, id=UUID(int=1000), text="changed", content_sha256="a" * 64)
    script.chunks = [bad]
    provider = RecordingProvider(script)
    with pytest.raises(PermanentJobError):
        _run(script, provider=provider)
    assert provider.calls == [] and script.written == []


def test_a_payload_without_exactly_index_id_fails_before_any_fence(script: Script) -> None:
    with pytest.raises(PermanentJobError):
        _run(script, job=_job({"index_id": str(INDEX), "revision_id": str(REVISION)}))
    assert script.events == []


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("read_target", embedding_store.IndexJobMismatchError()),
        ("read_target", embedding_store.IndexNotFoundError()),
        ("write", embedding_store.EmbeddingProfileMismatchError()),
        ("write", embedding_store.EmbeddingSourceMismatchError()),
        ("write", embedding_store.EmbeddingConflictError()),
        ("write", embedding_store.EmbeddingStorageRejectedError()),
        ("mark_ready", embedding_store.IndexIncompleteError()),
    ],
)
def test_expected_failures_are_permanent_with_the_existing_code(
    script: Script, stage: str, error: Exception
) -> None:
    script.errors[stage] = error
    with pytest.raises(PermanentJobError) as info:
        _run(script)
    assert info.value.code is JobErrorCode.PERMANENT_FAILURE
    assert "succeed" not in script.events


@pytest.mark.parametrize("stage", ["read_target", "read_page", "write", "mark_ready"])
def test_a_lock_timeout_is_retryable(script: Script, stage: str) -> None:
    script.errors[stage] = JobLockTimeoutError()
    with pytest.raises(RetryableJobError) as info:
        _run(script)
    assert info.value.code is JobErrorCode.RETRYABLE_FAILURE


@pytest.mark.parametrize(
    "error", [LeaseLostError(), JobCancelledError(), FenceClosedError(), RuntimeError("bug")]
)
def test_control_flow_and_unexpected_errors_propagate_untouched(
    script: Script, error: BaseException
) -> None:
    script.errors["write"] = error
    with pytest.raises(type(error)):
        _run(script)


def test_an_invalid_provider_output_is_permanent_and_private(script: Script) -> None:
    with pytest.raises(PermanentJobError) as info:
        _run(script, provider=RecordingProvider(script, fail=True))
    assert TEXT_MARKER not in str(info.value)
    assert script.written == []


# --- cancellation and lease-loss boundaries ---------------------------------------------------


def _check_index(script: Script, marker: str) -> int:
    """The 1-based number of the ``check`` immediately before ``marker`` first occurs."""
    position = script.events.index(marker)
    return script.events[:position].count("check")


def test_a_cancellation_before_provider_work_stops_before_the_call(script: Script) -> None:
    # Checks 1-4 belong to the two read fences; check 5 is the one just before the provider.
    script.latch_on_check = 5
    provider = RecordingProvider(script)
    with pytest.raises(JobCancelledError):
        _run(script, provider=provider)
    assert provider.calls == [] and script.written == []


@pytest.mark.parametrize("latch", [JobCancelledError(), LeaseLostError()])
def test_a_latch_during_a_successful_call_prevents_the_write(
    script: Script, latch: BaseException
) -> None:
    script.latch_error = latch

    def latch_now() -> None:
        script.latched = True

    with pytest.raises(type(latch)):
        _run(script, provider=RecordingProvider(script, on_call=latch_now))
    assert script.written == [] and "write" not in script.events


@pytest.mark.parametrize("latch", [JobCancelledError(), LeaseLostError()])
def test_a_latch_during_a_failing_call_wins_over_the_failure(
    script: Script, latch: BaseException
) -> None:
    script.latch_error = latch

    def latch_now() -> None:
        script.latched = True

    with pytest.raises(type(latch)):  # not PermanentJobError
        _run(script, provider=RecordingProvider(script, on_call=latch_now, fail=True))


def test_a_latch_at_the_write_boundary_prevents_the_write(script: Script) -> None:
    script.latch_on_check = 7  # the fenced write's entry check
    with pytest.raises(JobCancelledError):
        _run(script)
    assert "write" not in script.events and script.written == []


def test_a_latch_at_the_finish_boundary_prevents_success(script: Script) -> None:
    script.latch_on_check = 11  # the finish block's entry check
    with pytest.raises(JobCancelledError):
        _run(script)
    assert "mark_ready" not in script.events and "succeed" not in script.events
    assert script.written != []  # the earlier committed page stays committed


# --- provider-resolution control flow (Prompt 126) ---------------------------------------------

CONTROL_FLOW = [JobCancelledError(), LeaseLostError(), FenceClosedError()]


class _IdentityRaises:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    @property
    def identity(self) -> EmbeddingIdentity:
        raise self._error

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        raise AssertionError("never called")


def _chain(error: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


@pytest.mark.parametrize("error", CONTROL_FLOW, ids=lambda e: type(e).__name__)
def test_control_flow_from_the_provider_factory_propagates_unchanged(
    script: Script, error: BaseException
) -> None:
    def factory() -> Any:
        raise error

    with pytest.raises(type(error)) as info:
        _run(script, providers={HASH_IDENTITY.fingerprint: factory})
    assert info.value is error
    assert "read_page" not in script.events and "succeed" not in script.events


@pytest.mark.parametrize("error", CONTROL_FLOW, ids=lambda e: type(e).__name__)
def test_control_flow_from_the_provider_identity_propagates_unchanged(
    script: Script, error: BaseException
) -> None:
    with pytest.raises(type(error)) as info:
        _run(script, providers={HASH_IDENTITY.fingerprint: lambda: _IdentityRaises(error)})
    assert info.value is error
    assert "read_page" not in script.events and "succeed" not in script.events


@pytest.mark.parametrize(
    "latch", [JobCancelledError(), LeaseLostError()], ids=lambda e: type(e).__name__
)
@pytest.mark.parametrize("stage", ["factory", "identity"])
def test_a_latch_during_resolution_wins_over_the_ordinary_failure(
    script: Script, latch: BaseException, stage: str
) -> None:
    script.latch_error = latch

    def fail_after_latch() -> Any:
        script.latched = True
        raise RuntimeError(TEXT_MARKER)

    class LatchingIdentity(_IdentityRaises):
        @property
        def identity(self) -> EmbeddingIdentity:
            fail_after_latch()
            raise AssertionError("unreachable")

    factory = fail_after_latch if stage == "factory" else (lambda: LatchingIdentity(latch))
    with pytest.raises(type(latch)):  # not PermanentJobError
        _run(script, providers={HASH_IDENTITY.fingerprint: factory})
    assert "read_page" not in script.events
    assert script.written == [] and "succeed" not in script.events


@pytest.mark.parametrize("stage", ["factory", "identity"])
def test_an_ordinary_resolution_failure_is_a_fixed_private_permanent_failure(
    script: Script, stage: str
) -> None:
    import traceback

    failure = RuntimeError(TEXT_MARKER)

    def raising_factory() -> Any:
        raise failure

    factory = raising_factory if stage == "factory" else (lambda: _IdentityRaises(failure))
    with pytest.raises(PermanentJobError) as info:
        _run(script, providers={HASH_IDENTITY.fingerprint: factory})

    assert info.value.code is JobErrorCode.PERMANENT_FAILURE
    chain = _chain(info.value)
    assert failure not in chain
    assert all(TEXT_MARKER not in str(item) for item in chain)
    assert TEXT_MARKER not in "".join(traceback.format_exception(info.value))
    assert "read_page" not in script.events and "succeed" not in script.events
