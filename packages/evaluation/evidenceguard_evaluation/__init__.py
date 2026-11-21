"""Evaluation harness for EvidenceGuard (M7, ADR-0029).

Pure building blocks of the ``eg-eval`` command: the owner's selection file, model prices, the
budget guard, run records, metrics, the contract-suite scripts, the report and the argument
parser. This package may import the other packages, never the apps; the database, seeding and
review execution live in the worker's composition root ``evidenceguard_worker.evaluation_run``.

Nothing here reads a provider key, opens a network connection or chooses a model.
"""
