"""PostgreSQL persistence for EvidenceGuard: settings, engine and sessions, schema, migrations.

Importing this package (or any of its modules) never connects to a database and never reads
database settings. Configuration is loaded only when ``load_database_settings`` is called.

This package must not import application packages (such as ``evidenceguard_api``).
"""
