"""The production ``index_revision`` handler (M4c, ADR-0015).

The job's payload is exactly ``{"index_id": "<canonical UUID>"}``; the tenant comes only from
the job. One attempt, in order:

1. **Target read** (a short read-purpose fenced transaction): the index and its stored profile.
   The stored ``EmbeddingIdentity`` is rebuilt and its fingerprint verified before any provider
   is resolved.
2. **Already ready:** ``mark_index_ready`` in a ``finish=True`` block, which is M4b's no-op
   with a fresh ownership check; the job succeeds and nothing is written.
3. **Provider:** looked up by fingerprint in an immutable mapping fixed when the handler is
   built (production: only the offline ``HASH_IDENTITY``). The provider's identity must equal
   the stored identity. No live adapter, network or environment is used.
4. **Pages:** each page is read in its own short fenced transaction (at most 32 chunks with no
   embedding in this index, after a strictly increasing ordinal cursor). After that fence
   closes, the longest prefix within 128,000 UTF-8 bytes is kept and its text hashes verified.
   Then, with ``ctx.check()`` before and after and no transaction, lock or session open, it is
   embedded through ``embed_validated`` and converted by ``stored_embeddings``. Finally it is
   written by M4b's ``write_embeddings`` in a short fenced transaction. Rows committed earlier
   are reused without provider calls, and reused vectors are not re-verified.
5. **Finish:** ``mark_index_ready`` in a ``finish=True`` block, so readiness and job success
   commit together.

On a provider or validation failure, ``ctx.check()`` runs **before** the failure is classified,
so a cancellation or lease loss latched during the call takes precedence. Checks happen at
explicit boundaries only. They do not interrupt synchronous calls or guard every statement, and
a cancellation latched after the last check may not stop a non-finish transaction already under
way. Cancellation, lease loss and fence closure propagate untouched; the existing runtime
records ``worker_shutdown`` for a cancellation and nothing after lease loss. No exactly-once
provider call is claimed: an uncommitted page is computed again on retry.

Expected failures use the existing fixed codes. Nothing here logs, and errors never carry text,
vectors or IDs.
"""

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, cast

from evidenceguard_domain.chunks import content_sha256
from evidenceguard_domain.embedding_storage import StoredEmbedding, stored_embeddings
from evidenceguard_domain.embeddings import (
    EmbeddingIdentity,
    InvalidEmbeddingError,
    validate_identity,
)
from evidenceguard_domain.jobs import JobErrorCode, LeaseLostError
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing as index_store
from evidenceguard_persistence.embeddings import ProfileSnapshot
from evidenceguard_persistence.indexing import PendingChunk
from evidenceguard_persistence.jobs import FenceClosedError, JobLockTimeoutError
from evidenceguard_retrieval.embeddings import (
    HASH_IDENTITY,
    EmbeddingProvider,
    HashingEmbedder,
    embed_validated,
)
from evidenceguard_worker.context import (
    JobCancelledError,
    JobContext,
    PermanentJobError,
    RetryableJobError,
)
from evidenceguard_worker.registry import JobHandler

INDEX_REVISION_KIND = embedding_store.INDEX_REVISION_KIND
PAYLOAD_KEYS = frozenset({embedding_store.INDEX_ID_PAYLOAD_KEY})
PAGE_BYTES = 128_000
ProviderFactory = Callable[[], EmbeddingProvider]
SUPPORTED_PROVIDERS: Mapping[str, ProviderFactory] = MappingProxyType(
    {HASH_IDENTITY.fingerprint: HashingEmbedder}
)


class UnsupportedProfileError(Exception):
    """The stored profile is invalid, unsupported or not the provider's identity."""

    def __init__(self) -> None:
        super().__init__("the index profile is not supported")


class SourceIntegrityError(Exception):
    """A chunk's stored text no longer matches its stored digest."""

    def __init__(self) -> None:
        super().__init__("a chunk's text does not match its digest")


CONTROL_FLOW_ERRORS: tuple[type[Exception], ...] = (
    JobCancelledError,
    LeaseLostError,
    FenceClosedError,
)
PERMANENT_ERRORS: tuple[type[Exception], ...] = (
    embedding_store.IndexJobMismatchError,
    embedding_store.IndexNotFoundError,
    embedding_store.EmbeddingProfileMismatchError,
    embedding_store.EmbeddingSourceMismatchError,
    embedding_store.IndexIncompleteError,
    embedding_store.EmbeddingConflictError,
    embedding_store.EmbeddingStorageRejectedError,
    UnsupportedProfileError,
    SourceIntegrityError,
)


def make_index_revision_handler(
    providers: Mapping[str, ProviderFactory] = SUPPORTED_PROVIDERS,
) -> JobHandler:
    """Build the handler around an immutable copy of ``providers`` (fingerprint → factory)."""
    copied = dict(providers)
    for fingerprint, factory in copied.items():
        if type(fingerprint) is not str or not callable(factory):
            raise TypeError("providers must map fingerprints to provider factories")
    frozen: Mapping[str, ProviderFactory] = MappingProxyType(copied)

    def index_revision(ctx: JobContext) -> None:
        """Embed the job's index and mark it ready (see the module docstring)."""
        if frozenset(ctx.job.payload.as_dict()) != PAYLOAD_KEYS:
            raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
        try:
            _attempt(ctx, frozen)
        except PERMANENT_ERRORS:
            raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE) from None
        except JobLockTimeoutError:
            raise RetryableJobError(JobErrorCode.RETRYABLE_FAILURE) from None

    return index_revision


def page_prefix(
    page: Sequence[PendingChunk], max_bytes: int = PAGE_BYTES
) -> tuple[PendingChunk, ...]:
    """The longest prefix of ``page`` whose UTF-8 total is at most ``max_bytes``. One chunk is
    at most 16,000 bytes, so a non-empty page always keeps at least one chunk."""
    kept: list[PendingChunk] = []
    total = 0
    for chunk in page:
        size = len(chunk.text.encode("utf-8"))
        if total + size > max_bytes:
            break
        kept.append(chunk)
        total += size
    return tuple(kept)


def stored_identity(profile: ProfileSnapshot) -> EmbeddingIdentity:
    """Rebuild the stored identity and verify it against the stored fingerprint."""
    invalid = False
    try:
        identity = EmbeddingIdentity(
            profile.provider_id,
            profile.model_id,
            profile.algorithm_version,
            profile.dims,
            cast(Any, profile.normalization),  # validated by the constructor
        )
    except InvalidEmbeddingError:
        invalid = True
    if invalid or identity.fingerprint != profile.fingerprint:
        raise UnsupportedProfileError()
    return identity


def resolve_provider(
    providers: Mapping[str, ProviderFactory], identity: EmbeddingIdentity
) -> EmbeddingProvider:
    """The provider for a verified stored identity, or ``UnsupportedProfileError``.

    Cancellation, lease loss and fence closure raised by the factory or the identity property
    propagate unchanged, as does any ``BaseException`` that is not an ``Exception``. Any other
    failure becomes the fixed ``UnsupportedProfileError``, raised outside the handler so the
    original exception is never chained."""
    factory = providers.get(identity.fingerprint)
    if factory is None:
        raise UnsupportedProfileError()
    mismatch = False
    try:
        provider = factory()
        mismatch = validate_identity(provider.identity) != identity
    except CONTROL_FLOW_ERRORS:
        raise
    except Exception:  # an ordinary factory or identity failure: fixed and private
        mismatch = True
    if mismatch:
        raise UnsupportedProfileError()
    return provider


def _attempt(ctx: JobContext, providers: Mapping[str, ProviderFactory]) -> None:
    with ctx.fenced() as fence:
        index, profile = index_store.load_index_target(fence.session, fence.job)
    identity = stored_identity(profile)
    if index.status == embedding_store.READY:
        _finish(ctx, identity)
        return
    unsupported = False
    try:
        provider = resolve_provider(providers, identity)
    except UnsupportedProfileError:
        unsupported = True
    if unsupported:
        ctx.check()  # a cancellation or lease loss latched meanwhile wins over classification
        raise UnsupportedProfileError()

    after = -1
    while True:
        with ctx.fenced() as fence:
            page = index_store.pending_chunks(fence.session, fence.job, index, after_ordinal=after)
        if not page:
            break
        kept = page_prefix(page)
        if any(content_sha256(chunk.text) != chunk.content_sha256 for chunk in kept):
            raise SourceIntegrityError()
        rows = _embed(ctx, provider, identity, kept)
        try:
            with ctx.fenced() as fence:
                embedding_store.write_embeddings(fence.session, fence.job, identity, rows)
        except embedding_store.EmbeddingWriteRefusedError:
            break  # another attempt made the index ready: finish with the no-op
        after = kept[-1].ordinal
    _finish(ctx, identity)


def _embed(
    ctx: JobContext,
    provider: EmbeddingProvider,
    identity: EmbeddingIdentity,
    kept: Sequence[PendingChunk],
) -> tuple[StoredEmbedding, ...]:
    """Compute one page outside every transaction; latched cancellation or lease loss wins."""
    ctx.check()
    failed = False
    rows: tuple[StoredEmbedding, ...] = ()
    try:
        batch = embed_validated(provider, tuple(chunk.text for chunk in kept), "document")
        rows = stored_embeddings(
            batch,
            identity=identity,
            chunks=[(chunk.id, chunk.content_sha256) for chunk in kept],
        )
    except InvalidEmbeddingError:
        failed = True
    ctx.check()  # before classifying a failure, and after a success
    if failed:
        raise PermanentJobError(JobErrorCode.PERMANENT_FAILURE)
    return rows


def _finish(ctx: JobContext, identity: EmbeddingIdentity) -> None:
    with ctx.fenced(finish=True) as fence:
        embedding_store.mark_index_ready(fence.session, fence.job, identity)


index_revision = make_index_revision_handler()
