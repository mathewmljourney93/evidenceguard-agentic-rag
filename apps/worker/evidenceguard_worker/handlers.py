"""The production handler registry.

It is **empty in M3b**: there are no production handlers yet, so ``eg-worker`` exits with code 4
before reading database settings. M3d adds ``ingest_revision``. Test-only handlers live under
``tests/`` and are never packaged or registered here.
"""

from evidenceguard_worker.registry import HandlerRegistry


def production_registry() -> HandlerRegistry:
    return HandlerRegistry()
