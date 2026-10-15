"""The EvidenceGuard worker: a sequential runtime for durable PostgreSQL jobs (M3b, ADR-0008).

It claims jobs through the M3a job core, runs at most one handler at a time, renews the lease
with heartbeats and records outcomes only through the fence. Importing this package never reads
settings, connects to a database or installs signal handlers.

This package may import the domain, persistence, observability and retrieval packages (M3d adds
retrieval for the ``ingest_revision`` handler's chunker). It must not import
``evidenceguard_api``, and nothing else imports it.
"""
