"""Provider orchestration for snapshot retrieval (M4d, ADR-0016).

``search_snapshot`` and ``search_current`` are **trusted internal programming interfaces** for
the later review workflow (M5); no endpoint calls them. They never hold a database session while
the provider runs.

``search_snapshot``, in order:

1. pure validation (actor type, request and snapshot structure, role, the actor's tenant against
   the snapshot's), with no provider access or SQL;
2. the provider's ``identity`` property, read and validated in its own ``try`` and compared with
   the snapshot identity (``embed_validated`` reads it again itself and does not protect this
   first read);
3. one ``embed_validated(provider, request.queries, "query")`` call, with no session open;
4. ``query_vectors`` against the **snapshot** identity, which also rejects a provider whose
   identity changed between step 2 and the read inside ``embed_validated``;
5. ``retrieve_with_vectors`` with the validated batch, which validates it again independently.

Steps 2 to 4 catch ordinary ``Exception``s only, set a flag and raise the fixed
``RetrievalProviderError`` after the ``except`` block, so no provider exception is retained as
cause or context. ``BaseException`` subclasses that are not ``Exception`` propagate. There is no
``JobContext`` integration, cancellation protocol or retry; M5 must define how cancellation and
lease loss take precedence when a job handler calls these seams.

``search_current`` implements current-state search: pure validation (actor type, request,
vendor ID, role), the provider identity
(needed to pin the profile), a fresh ``capture_snapshot`` (its own transaction), then
``search_snapshot`` (the provider call, then a second transaction). Nothing is atomic across the
provider call and the transactions. Nothing here logs.
"""

from contextlib import suppress
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.embedding_storage import require_storable_identity
from evidenceguard_domain.embeddings import EmbeddingBatch, EmbeddingIdentity
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.retrieval import (
    InvalidRetrievalRequestError,
    RetrievalProviderError,
    RetrievalRequest,
    RetrievalResult,
    RetrievalSnapshot,
    revalidate_request,
)
from evidenceguard_persistence.retrieval import (
    RETRIEVAL_ROLES,
    capture_snapshot,
    check_retrieval_access,
    checked_query_vectors,
    retrieve_with_vectors,
)
from evidenceguard_retrieval.embeddings import EmbeddingProvider, embed_validated

__all__ = ["search_current", "search_snapshot"]


def _provider_identity(provider: EmbeddingProvider) -> EmbeddingIdentity:
    """The provider's validated, storable identity; any failure (including an exception from
    the property getter) raises ``RetrievalProviderError``."""
    identities: list[EmbeddingIdentity] = []
    with suppress(Exception):  # the fixed error is raised below, outside any handler
        identities.append(require_storable_identity(provider.identity))
    if not identities:
        raise RetrievalProviderError()
    return identities[0]


def _embed_queries(provider: EmbeddingProvider, request: RetrievalRequest) -> EmbeddingBatch:
    batches: list[EmbeddingBatch] = []
    with suppress(Exception):  # the fixed error is raised below, outside any handler
        batches.append(embed_validated(provider, request.queries, "query"))
    if not batches:
        raise RetrievalProviderError()
    return batches[0]


def search_snapshot(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    snapshot: RetrievalSnapshot,
    request: RetrievalRequest,
    provider: EmbeddingProvider,
) -> RetrievalResult:
    """Embed the queries with ``provider`` and retrieve within ``snapshot`` (see the module
    docstring)."""
    checked_snapshot, checked_request = check_retrieval_access(actor, snapshot, request)
    if _provider_identity(provider) != checked_snapshot.identity:
        raise RetrievalProviderError()
    batch = _embed_queries(provider, checked_request)
    checked_query_vectors(batch, checked_snapshot, checked_request)
    return retrieve_with_vectors(session_factory, actor, checked_snapshot, checked_request, batch)


def search_current(
    session_factory: sessionmaker[Session],
    actor: ActorContext,
    *,
    vendor_id: UUID,
    request: RetrievalRequest,
    provider: EmbeddingProvider,
) -> tuple[RetrievalSnapshot, RetrievalResult]:
    """Capture a fresh snapshot of the vendor's current eligible revisions, then search it."""
    if not isinstance(actor, ActorContext):
        raise TypeError("actor must be an ActorContext")
    checked_request = revalidate_request(request)
    if type(vendor_id) is not UUID:
        raise InvalidRetrievalRequestError()
    if actor.role not in RETRIEVAL_ROLES:
        raise PermissionDeniedError()
    identity = _provider_identity(provider)
    snapshot = capture_snapshot(session_factory, actor, vendor_id=vendor_id, identity=identity)
    result = search_snapshot(session_factory, actor, snapshot, checked_request, provider)
    return snapshot, result
