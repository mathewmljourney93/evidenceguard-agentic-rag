"""The production ``ingest_revision`` handler (M3d, ADR-0010).

The job's payload is exactly ``{"revision_id": "<canonical UUID>"}``; the tenant comes only from
the job. One attempt, in order:

1. **Status read** (one fenced transaction): read the revision's status; if it is ``pending`` or
   ``processing``, ``start_processing`` (a no-op when already processing) and load the verified
   source. The block commits.
2. **Already failed:** raise ``PermanentJobError`` at once. Nothing is parsed again (this closes
   the permanent-failure crash gap on reclaim).
3. **Already settled** (``active`` or ``superseded``): a duplicate activation in a
   ``finish=True`` block, M3c's no-op, so the job completes without parsing or writing.
4. **Parse** outside every transaction and lock, with ``ctx.check()`` before and after.
5. **Write** the chunk-set row, then each bounded batch, each in its own fenced transaction
   under the shared lock protocol (``evidenceguard_persistence.chunks``).
6. **Finish:** ``activate_revision`` in a ``finish=True`` block with ``before_settle`` bound to
   this attempt's ``ExpectedChunkSet``, so activation and the job's success commit together.

A ``ChunkWriteRefusedError`` or ``InvalidRevisionTransitionError`` means the revision settled or
failed meanwhile. The refusing block rolled back; the handler re-reads the status once in a new
fenced transaction and takes the failed or settled branch. It never fails a revision that is
already settled or failed.

**Permanent failures** use the existing two-transaction protocol: ``fail_revision`` commits in a
block that does not raise, and only **after** that block does the handler raise
``PermanentJobError(PERMANENT_FAILURE)``. The worker's cancellation, lease-loss and
uncertain-commit handling is unchanged: those errors propagate untouched.

Nothing here logs; the runtime records outcomes with fixed codes. Errors never carry content.
"""

from functools import partial
from typing import NoReturn

from evidenceguard_domain.chunks import Chunk, ExpectedChunkSet, batches
from evidenceguard_domain.jobs import JobErrorCode
from evidenceguard_domain.revisions import (
    SETTLED_STATUSES,
    InvalidRevisionContentError,
    InvalidRevisionTransitionError,
    RevisionFailureCode,
    RevisionStatus,
)
from evidenceguard_persistence import chunks as chunk_store
from evidenceguard_persistence import documents as revision_store
from evidenceguard_persistence.chunks import RevisionSource
from evidenceguard_persistence.jobs import JobLockTimeoutError
from evidenceguard_retrieval import chunking
from evidenceguard_worker.context import JobContext, PermanentJobError, RetryableJobError

INGEST_REVISION_KIND = "ingest_revision"
PAYLOAD_KEYS = frozenset({chunk_store.REVISION_ID_PAYLOAD_KEY})
UNSETTLED_STATUSES = frozenset({RevisionStatus.PENDING, RevisionStatus.PROCESSING})


def ingest_revision(ctx: JobContext) -> None:
    """Chunk the job's revision and activate it (see the module docstring)."""
    if frozenset(ctx.job.payload.as_dict()) != PAYLOAD_KEYS:
        raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
    try:
        _ingest(ctx)
    except revision_store.RevisionNotFoundError:  # including another tenant's revision ID
        raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE) from None
    except JobLockTimeoutError:
        raise RetryableJobError(JobErrorCode.RETRYABLE_FAILURE) from None


def _ingest(ctx: JobContext) -> None:
    try:
        _attempt(ctx)
        return
    except (chunk_store.ChunkWriteRefusedError, InvalidRevisionTransitionError):
        pass  # the revision settled or failed meanwhile; the refusing block rolled back
    status = _read_status(ctx)
    if status is RevisionStatus.FAILED:
        raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
    if status in SETTLED_STATUSES:
        _complete_settled(ctx)
        return
    # Not reachable under M3c's rules: a settled or failed status never returns to processing.
    raise RetryableJobError(JobErrorCode.RETRYABLE_FAILURE)


def _attempt(ctx: JobContext) -> None:
    source: RevisionSource | None = None
    integrity_failed = False
    try:
        with ctx.fenced() as fence:
            status = chunk_store.read_revision_status(fence.session, fence.job)
            if status in UNSETTLED_STATUSES:
                revision_store.start_processing(fence.session, fence.job)
                source = chunk_store.load_revision_source(fence.session, fence.job)
    except InvalidRevisionContentError:
        integrity_failed = True
    if integrity_failed:
        _fail(ctx, RevisionFailureCode.CONTENT_INTEGRITY_FAILED)
    if status is RevisionStatus.FAILED:
        raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
    if source is None:  # active or superseded
        _complete_settled(ctx)
        return

    chunks = _parse(ctx, source)
    expected = ExpectedChunkSet.of(chunks)

    conflict = False
    try:
        ctx.check()
        with ctx.fenced() as fence:
            chunk_store.write_chunk_set(fence.session, fence.job, expected)
        for batch in batches(chunks):
            ctx.check()
            with ctx.fenced() as fence:
                chunk_store.write_chunks(fence.session, fence.job, batch)
    except chunk_store.ChunkConflictError:
        conflict = True
    if conflict:
        _fail(ctx, RevisionFailureCode.CHUNK_CONFLICT)

    complete = partial(chunk_store.require_complete_chunk_set, expected=expected)
    try:
        with ctx.fenced(finish=True) as fence:
            revision_store.activate_revision(fence.session, fence.job, before_settle=complete)
    except chunk_store.ChunkSetIncompleteError:
        raise RetryableJobError(JobErrorCode.RETRYABLE_FAILURE) from None


def _parse(ctx: JobContext, source: RevisionSource) -> tuple[Chunk, ...]:
    """Pure parsing, outside every transaction and lock."""
    ctx.check()
    code: RevisionFailureCode
    try:
        chunks = chunking.chunk_revision(
            source.content, tenant_id=ctx.job.tenant_id, revision_id=source.revision_id
        )
    except chunking.EmptyDocumentError:
        code = RevisionFailureCode.EMPTY_DOCUMENT
    except chunking.ChunkLimitExceededError:
        code = RevisionFailureCode.CHUNK_LIMIT_EXCEEDED
    except Exception:  # an unexpected parser exception is a bug, never retried
        code = RevisionFailureCode.INGESTION_FAILED
    else:
        ctx.check()
        return chunks
    _fail(ctx, code)


def _fail(ctx: JobContext, code: RevisionFailureCode) -> NoReturn:
    """Commit the revision's failure in a block that does not raise, then fail the job."""
    with ctx.fenced() as fence:
        revision_store.fail_revision(fence.session, fence.job, code)
    raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)


def _read_status(ctx: JobContext) -> RevisionStatus:
    with ctx.fenced() as fence:
        return chunk_store.read_revision_status(fence.session, fence.job)


def _complete_settled(ctx: JobContext) -> None:
    """M3c's duplicate activation: no write, and the job succeeds in the same transaction."""
    with ctx.fenced(finish=True) as fence:
        revision_store.activate_revision(fence.session, fence.job)
