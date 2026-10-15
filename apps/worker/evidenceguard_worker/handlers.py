"""The production handler registry.

M3d registers the first production handler, ``ingest_revision`` (ADR-0010). An empty registry
still makes ``eg-worker`` exit with code 4 before reading database settings, but only when one is
injected (tests). Test-only handlers live under ``tests/`` and are never packaged or registered
here.
"""

from evidenceguard_worker.ingest import INGEST_REVISION_KIND, ingest_revision
from evidenceguard_worker.registry import HandlerRegistry


def production_registry() -> HandlerRegistry:
    return HandlerRegistry([(INGEST_REVISION_KIND, ingest_revision)])
