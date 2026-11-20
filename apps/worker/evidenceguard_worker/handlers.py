"""The production handler registry.

M3d registers the first production handler, ``ingest_revision`` (ADR-0010); M4c adds
``index_revision`` (ADR-0015). W8 (ADR-0027) adds the review job kind, but only when the caller
passes a review handler: ``eg-worker`` builds one only from a fully valid review configuration,
so ``production_registry()`` without an argument still has exactly the two kinds. An empty
registry still makes ``eg-worker`` exit with code 4 before reading database settings, but only
when one is injected (tests). Test-only handlers live under ``tests/`` and are never packaged or
registered here.
"""

from evidenceguard_domain.reviews import REVIEW_JOB_KIND
from evidenceguard_worker.indexing import INDEX_REVISION_KIND, index_revision
from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry, JobHandler


def production_registry(review_handler: JobHandler | None = None) -> HandlerRegistry:
    handlers: list[tuple[str, JobHandler]] = [
        (INGEST_REVISION_KIND, ingest_revision),
        (INDEX_REVISION_KIND, index_revision),
    ]
    if review_handler is not None:
        handlers.append((REVIEW_JOB_KIND, review_handler))
    return HandlerRegistry(handlers)
