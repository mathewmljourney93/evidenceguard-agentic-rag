"""Index enqueue, bounded backfill and the indexing handler's reads (M4c, ADR-0015).

**Enqueue** (``enqueue_index_revision``) runs in the **caller's** READ COMMITTED transaction and
never commits. The tenant comes only from the validated actor, whose role must be reviewer,
approver or admin. It runs M4b's ``ensure_profile`` and ``create_index``, then M3a's ``enqueue`` of
the canonical ``index_revision`` job: payload exactly ``{"index_id": …}`` and idempotency key
``str(index.id)``. Both commit together or roll back together. The outcome is an observation
within this transaction, not a promise about the job's state after commit:

- ``ready``: the index is ready; no job is enqueued;
- ``pending``: the canonical job is queued or running, whether this call created it (a building
  index with no job gets it) or it already existed. M3a's ``enqueue`` does not report creation,
  and nothing here infers it;
- ``stalled``: the index is building and its canonical job is terminal. The job is returned
  unchanged: it is never reset, rescheduled or replaced.

``JobIdempotencyConflictError`` and the M4b conflict errors propagate; the caller's transaction
must then roll back. Under stronger isolation the database may also raise serialization
failures, which propagate.

**Backfill** (``backfill_index_revisions``) validates every input first. It then selects one
bounded, tenant-scoped page of revisions that are ``active`` at the selection observation, with a
chunk set and without a ``ready`` index for the profile, ordered by revision ID after the cursor.
Each selected revision is enqueued in its **own** transaction. Only the named expected domain
failures become ``ineligible`` or ``conflict`` items, after that item's transaction rolled back
(so they carry no index ID). Any other failure propagates and ends the operation; items already
committed stay committed. A selected revision superseded before its own transaction may still
be indexed: it was activated and its chunks are immutable.

**Handler reads** (``load_index_target``, ``pending_chunks``) take M3a's ``FencedSession`` and the
fence's ``JobSnapshot`` and are called in short read-purpose fenced transactions (ordinary
fenced transactions holding the job-row lock, not ``READ ONLY`` transactions). They apply M4b's
job binding and every statement is scoped by tenant, revision, chunker version and index. They
take no index row lock: the fields read are immutable.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, Table, and_, exists, select
from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embedding_storage import (
    MAX_WRITE_BATCH,
    profile_id,
    require_storable_identity,
)
from evidenceguard_domain.embeddings import EmbeddingIdentity
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.jobs import (
    JobIdempotencyConflictError,
    JobPayload,
    JobSnapshot,
    JobStatus,
)
from evidenceguard_persistence.chunks import CHUNKS
from evidenceguard_persistence.db import transaction
from evidenceguard_persistence.documents import REVISIONS
from evidenceguard_persistence.embeddings import (
    EMBEDDINGS,
    INDEX_FIELDS,
    INDEX_ID_PAYLOAD_KEY,
    INDEX_REVISION_KIND,
    INDEXES,
    PROFILE_FIELDS,
    READY,
    EmbeddingProfileConflictError,
    IndexConflictError,
    IndexJobMismatchError,
    IndexNotFoundError,
    IndexSnapshot,
    IndexSourceNotEligibleError,
    ProfileSnapshot,
    create_index,
    ensure_profile,
    index_statement,
    profile_statement,
)
from evidenceguard_persistence.jobs import FencedSession, enqueue
from evidenceguard_persistence.models import ChunkSet

CHUNK_SETS = cast(Table, ChunkSet.__table__)
INDEXING_ROLES = frozenset({Role.REVIEWER, Role.APPROVER, Role.ADMIN})
DEFAULT_BACKFILL_LIMIT = 50
MAX_BACKFILL_LIMIT = 100
PAGE_CHUNKS = MAX_WRITE_BATCH  # 32: also M4a's provider batch limit
PENDING_JOB_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


class EnqueueOutcome(StrEnum):
    PENDING = "pending"
    READY = "ready"
    STALLED = "stalled"


class BackfillOutcome(StrEnum):
    PENDING = "pending"
    READY = "ready"
    STALLED = "stalled"
    INELIGIBLE = "ineligible"
    CONFLICT = "conflict"


class InvalidBackfillRequestError(ValueError):
    """A backfill limit or cursor is invalid. Nothing was read or written."""

    def __init__(self) -> None:
        super().__init__("the backfill limit or cursor is invalid")


@dataclass(frozen=True)
class IndexEnqueueResult:
    index: IndexSnapshot
    job: JobSnapshot | None
    outcome: EnqueueOutcome


@dataclass(frozen=True)
class BackfillItem:
    revision_id: UUID
    index_id: UUID | None
    outcome: BackfillOutcome


@dataclass(frozen=True)
class BackfillPage:
    items: tuple[BackfillItem, ...]
    next_after: UUID | None


@dataclass(frozen=True, repr=False)
class PendingChunk:
    """One chunk still to embed. ``repr`` never shows the text."""

    ordinal: int
    id: UUID
    text: str
    content_sha256: str

    def __repr__(self) -> str:
        return f"PendingChunk(ordinal={self.ordinal}, id={self.id})"

    __str__ = __repr__


# --- enqueue -------------------------------------------------------------------------------------


def _require_actor(actor: ActorContext) -> None:
    if not isinstance(actor, ActorContext):
        raise TypeError("actor must be an ActorContext")
    if actor.role not in INDEXING_ROLES:
        raise PermissionDeniedError()


def enqueue_index_revision(
    session: Session, actor: ActorContext, *, revision_id: UUID, identity: EmbeddingIdentity
) -> IndexEnqueueResult:
    """Create (or find) the revision's index for ``identity`` and its canonical job, in the
    caller's transaction (see the module docstring)."""
    _require_actor(actor)
    if type(revision_id) is not UUID:
        raise TypeError("revision_id must be a UUID")
    checked = require_storable_identity(identity)
    profile = ensure_profile(session, actor.tenant_id, checked)
    index = create_index(session, actor.tenant_id, revision_id, profile)
    if index.status == READY:
        return IndexEnqueueResult(index=index, job=None, outcome=EnqueueOutcome.READY)
    job = enqueue(
        session,
        actor,
        kind=INDEX_REVISION_KIND,
        idempotency_key=str(index.id),
        payload=JobPayload.from_mapping({INDEX_ID_PAYLOAD_KEY: str(index.id)}),
    )
    outcome = (
        EnqueueOutcome.PENDING if job.status in PENDING_JOB_STATUSES else EnqueueOutcome.STALLED
    )
    return IndexEnqueueResult(index=index, job=job, outcome=outcome)


# --- backfill -----------------------------------------------------------------------------------


def backfill_selection_statement(
    tenant_id: UUID, profile: UUID, *, limit: int, after: UUID | None
) -> Select[Any]:
    """Active revisions of the tenant with a chunk set and no ready index for the profile."""
    ready = exists().where(
        INDEXES.c.tenant_id == REVISIONS.c.tenant_id,
        INDEXES.c.revision_id == REVISIONS.c.id,
        INDEXES.c.profile_id == profile,
        INDEXES.c.status == READY,
    )
    statement = (
        select(REVISIONS.c.id)
        .select_from(
            REVISIONS.join(
                CHUNK_SETS,
                and_(
                    CHUNK_SETS.c.tenant_id == REVISIONS.c.tenant_id,
                    CHUNK_SETS.c.revision_id == REVISIONS.c.id,
                ),
            )
        )
        .where(REVISIONS.c.tenant_id == tenant_id, REVISIONS.c.status == "active", ~ready)
        .order_by(REVISIONS.c.id)
        .limit(limit)
    )
    if after is not None:
        statement = statement.where(REVISIONS.c.id > after)
    return statement


def backfill_index_revisions(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    *,
    identity: EmbeddingIdentity,
    limit: int = DEFAULT_BACKFILL_LIMIT,
    after: UUID | None = None,
) -> BackfillPage:
    """Enqueue indexing for one bounded page of the tenant's active revisions (see the module
    docstring). Each item commits on its own; there is no all-page atomicity."""
    _require_actor(actor)
    checked = require_storable_identity(identity)
    if type(limit) is not int or not 1 <= limit <= MAX_BACKFILL_LIMIT:
        raise InvalidBackfillRequestError()
    if after is not None and type(after) is not UUID:
        raise InvalidBackfillRequestError()

    target_profile = profile_id(actor.tenant_id, checked.fingerprint)
    with transaction(session_factory) as session:
        selected = list(
            session.scalars(
                backfill_selection_statement(
                    actor.tenant_id, target_profile, limit=limit, after=after
                )
            )
        )

    items: list[BackfillItem] = []
    for revision_id in selected:
        outcome: BackfillOutcome
        index: UUID | None = None
        try:
            with transaction(session_factory) as session:
                result = enqueue_index_revision(
                    session, actor, revision_id=revision_id, identity=checked
                )
        except IndexSourceNotEligibleError:
            outcome = BackfillOutcome.INELIGIBLE
        except (JobIdempotencyConflictError, EmbeddingProfileConflictError, IndexConflictError):
            outcome = BackfillOutcome.CONFLICT
        else:
            outcome = BackfillOutcome(result.outcome.value)
            index = result.index.id
        items.append(BackfillItem(revision_id=revision_id, index_id=index, outcome=outcome))
    next_after = selected[-1] if len(selected) == limit else None
    return BackfillPage(items=tuple(items), next_after=next_after)


# --- handler reads ----------------------------------------------------------------------------


def _payload_index_id(job: JobSnapshot) -> UUID:
    if job.kind != INDEX_REVISION_KIND:
        raise IndexJobMismatchError()
    payload = job.payload.as_dict()
    if set(payload) != {INDEX_ID_PAYLOAD_KEY}:
        raise IndexJobMismatchError()
    return UUID(payload[INDEX_ID_PAYLOAD_KEY])


def load_index_target(
    session: FencedSession, job: JobSnapshot
) -> tuple[IndexSnapshot, ProfileSnapshot]:
    """The job's index and its stored profile, read within the job's tenant without a lock."""
    index_id = _payload_index_id(job)
    row = session.execute(index_statement(job.tenant_id, index_id)).first()
    if row is None:
        raise IndexNotFoundError()
    index = IndexSnapshot(**{name: row._mapping[name] for name in INDEX_FIELDS})
    if index.tenant_id != job.tenant_id:
        raise IndexNotFoundError()
    profile_row = session.execute(profile_statement(index.tenant_id, index.profile_id)).first()
    if profile_row is None:
        raise IndexNotFoundError()
    profile = ProfileSnapshot(**{name: profile_row._mapping[name] for name in PROFILE_FIELDS})
    return index, profile


def pending_chunks_statement(index: IndexSnapshot, *, after_ordinal: int) -> Select[Any]:
    embedded = exists().where(
        EMBEDDINGS.c.tenant_id == CHUNKS.c.tenant_id,
        EMBEDDINGS.c.index_id == index.id,
        EMBEDDINGS.c.chunk_id == CHUNKS.c.id,
    )
    return (
        select(CHUNKS.c.ordinal, CHUNKS.c.id, CHUNKS.c.text, CHUNKS.c.content_sha256)
        .where(
            CHUNKS.c.tenant_id == index.tenant_id,
            CHUNKS.c.revision_id == index.revision_id,
            CHUNKS.c.chunker_version == index.chunker_version,
            CHUNKS.c.ordinal > after_ordinal,
            ~embedded,
        )
        .order_by(CHUNKS.c.ordinal)
        .limit(PAGE_CHUNKS)
    )


def pending_chunks(
    session: FencedSession, job: JobSnapshot, index: IndexSnapshot, *, after_ordinal: int
) -> tuple[PendingChunk, ...]:
    """Up to 32 chunks of the index's revision with no embedding in this index and an ordinal
    above ``after_ordinal``, in ordinal order."""
    if _payload_index_id(job) != index.id or index.tenant_id != job.tenant_id:
        raise IndexJobMismatchError()
    if type(after_ordinal) is not int or after_ordinal < -1:
        raise ValueError("after_ordinal must be an integer of at least -1")
    rows = session.execute(pending_chunks_statement(index, after_ordinal=after_ordinal))
    return tuple(
        PendingChunk(
            ordinal=row.ordinal, id=row.id, text=row.text, content_sha256=row.content_sha256
        )
        for row in rows
    )
