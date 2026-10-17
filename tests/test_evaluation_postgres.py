"""PostgreSQL integration tests for the M4e corpus loader, read-only verifier and evaluation
(ADR-0017).

They use the guarded disposable-database fixtures from ``conftest.py`` and are skipped without
``EG_TEST_DATABASE_URL`` (required in CI). Every connection carries a server-side
``statement_timeout``. The corpus is loaded only through ``run_fresh_two_epoch``, which uses the
production seams (``seed_demo``, ``create_vendor``, ``create_upload``, the real worker and
``enqueue_index_revision``) with the offline hash profile. Partial states come only from the
orchestrator's ``stop_after`` phase hook or from the legitimate seams named in each test, never
from DML on terminal rows. Recall values are reported, never asserted.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_domain.embeddings import EmbeddingIdentity
from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.retrieval import RetrievalRequest
from evidenceguard_domain.revisions import MediaType, RevisionContent
from evidenceguard_persistence import embeddings as embedding_store
from evidenceguard_persistence import indexing
from evidenceguard_persistence.accounts import DatabaseAdminStore, demo_tenant_id, demo_user_id
from evidenceguard_persistence.db import create_session_factory, transaction
from evidenceguard_persistence.document_views import create_upload
from evidenceguard_persistence.models import Base, DocumentRevision, UserRole
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder
from evidenceguard_retrieval.evaluation.corpus import (
    CLEAN,
    FINAL,
    INITIAL,
    INJECTED,
    EvaluationError,
    RevisionRef,
    Suite,
    build_suite,
)
from evidenceguard_retrieval.evaluation.recall import report_bytes, require_passing
from evidenceguard_worker.evaluation import (
    PHASES,
    TwoEpochState,
    evaluate,
    load_suite,
    run_fresh_two_epoch,
    verify_loaded,
)
from evidenceguard_worker.retrieval import search_snapshot

pytestmark = pytest.mark.integration

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"
SECOND_IDENTITY = EmbeddingIdentity("offline", "fake-hash-v2", "ascii-word-sha256-v1", 1024, "l2")
_WRITES = ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE", "MERGE")


@pytest.fixture
def engine(migrated: Engine, test_database_url: URL) -> Iterator[Engine]:
    bounded = create_engine(
        test_database_url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=20000"},
    )
    try:
        yield bounded
    finally:
        bounded.dispose()


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture(scope="module")
def clean() -> Suite:
    return load_suite(SAMPLE, CLEAN)


def _reset(engine: Engine, config: Config) -> None:
    """Reset the already validated disposable database between two loads in one test, exactly
    as the ``empty_database`` and ``migrated`` fixtures do."""
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(config, "head")


def _rows(engine: Engine) -> dict[str, list[str]]:
    """Every row of every table, as sorted ``repr`` strings (vectors included)."""
    with engine.connect() as connection:
        return {
            table.name: sorted(repr(tuple(row)) for row in connection.execute(select(table)))
            for table in Base.metadata.sorted_tables
        }


def _actor(tenant: str) -> ActorContext:
    """The seeded reviewer of a demo tenant."""
    return ActorContext(
        tenant_id=demo_tenant_id(tenant),
        actor_id=demo_user_id(tenant, UserRole.REVIEWER),
        role=Role.REVIEWER,
    )


def _code(call: Any) -> str:
    with pytest.raises(EvaluationError) as raised:
        call()
    return raised.value.code


def _sample_files() -> dict[str, bytes]:
    return {
        p.relative_to(SAMPLE).as_posix(): p.read_bytes() for p in SAMPLE.rglob("*") if p.is_file()
    }


def _revision_rows(engine: Engine) -> dict[Any, Any]:
    with engine.connect() as connection:
        return {
            row.id: row
            for row in connection.execute(
                select(
                    DocumentRevision.id,
                    DocumentRevision.revision_no,
                    DocumentRevision.status,
                    DocumentRevision.created_at,
                    DocumentRevision.activated_at,
                )
            )
        }


def _structure(suite: Suite, state: TwoEpochState, report_json: dict[str, Any]) -> Any:
    return (
        sorted(str(ref) for ref in state.loaded.revisions),
        sorted(state.snapshots),
        [
            (
                g["tenant"],
                g["vendor"],
                g["epoch"],
                g["counts"],
                [(q["id"], q["gold_count"]) for q in g["questions"]],
            )
            for g in report_json["groups"]
        ],
        len(suite.anchors),
    )


# --- the fresh run, evaluation and the verifier on a complete load ------------------------------


def test_the_fresh_run_loads_both_epochs_and_evaluates(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    state = run_fresh_two_epoch(factory, clean)
    revisions = _revision_rows(engine)
    loaded = state.loaded.revisions
    assert set(loaded) == set(clean.corpus.revision_refs())
    for ref, value in loaded.items():
        document = clean.corpus.document(ref)
        assert document is not None
        expected = "active" if ref.n == document.latest else "superseded"
        assert revisions[value.revision_id].status == expected

    later = [revisions[v.revision_id] for ref, v in loaded.items() if ref.n > 1]
    assert later, "the corpus must contain later revisions"
    for (tenant, vendor, epoch), snapshot in state.snapshots.items():
        bound = {b.revision_id for b in snapshot.bindings}
        refs = {ref for ref, v in loaded.items() if v.revision_id in bound}
        assert {(r.tenant, r.vendor) for r in refs} == {(tenant, vendor)}
        if epoch == INITIAL:
            assert all(ref.n == 1 for ref in refs)
            # Captured while every r1 was active and before any later revision existed.
            assert all(snapshot.captured_at < row.created_at for row in later)
        else:
            for ref in refs:
                document = clean.corpus.document(ref)
                assert document is not None and ref.n == document.latest
            assert all(snapshot.captured_at > row.activated_at for row in later)

    report = evaluate(factory, clean, state, HashingEmbedder())
    require_passing(report)
    body = json.loads(report_bytes(report))
    assert body["status"] == "ok" and body["variant"] == CLEAN
    assert body["contract_failures"] == [] and body["isolation_failures"] == []
    for group in body["groups"]:
        for question in group["questions"]:
            for entry in question["ranked"]:
                assert entry["ref"] is not None
                tenant, vendor, rest = entry["ref"].split("/")
                assert (tenant, vendor) == (group["tenant"], group["vendor"])
                key, n = rest.split("@r")
                document = clean.corpus.document(RevisionRef(tenant, vendor, key, int(n)))
                assert document is not None
                assert int(n) == (1 if group["epoch"] == INITIAL else document.latest)

    # Repeated retrieval from the same retained snapshots gives identical bytes.
    assert report_bytes(evaluate(factory, clean, state, HashingEmbedder())) == report_bytes(report)

    # The k = 5 result is the prefix of the k = 8 result.
    key = ("halverson-freight", "lumenvale-cloud", FINAL)
    question = next(q for q in clean.questions() if q.id == "RET-01" and q.tenant == key[0])
    actor = _actor(key[0])
    ranked = {
        k: [
            item.chunk_id
            for item in search_snapshot(
                factory,
                actor,
                state.snapshots[key],
                RetrievalRequest(question.search_queries, k=k),
                HashingEmbedder(),
            ).items
        ]
        for k in (5, 8)
    }
    assert ranked[5] == ranked[8][:5]


def test_the_verifier_accepts_a_complete_load_and_writes_nothing(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    DatabaseAdminStore(factory).seed_demo()  # a seeded-only database is a valid fresh start
    state = run_fresh_two_epoch(factory, clean)
    before = _rows(engine)
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        loaded = verify_loaded(factory, clean)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert _rows(engine) == before
    assert loaded.revisions == state.loaded.revisions
    assert loaded.vendors == state.loaded.vendors
    assert any("READ ONLY" in s.upper() for s in statements)
    assert not [s for s in statements if s.lstrip().upper().startswith(_WRITES)]
    assert not hasattr(loaded, "snapshots")  # no initial epoch is ever captured or reported


def test_production_seams_reuse_a_complete_corpus_without_changes(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    state = run_fresh_two_epoch(factory, clean)
    before = _rows(engine)
    DatabaseAdminStore(factory).seed_demo()
    for ref, loaded in sorted(state.loaded.revisions.items()):
        document = clean.corpus.document(ref)
        assert document is not None
        revision = document.revisions[ref.n - 1]
        actor = _actor(ref.tenant)
        with transaction(factory) as session:
            record = create_upload(
                session,
                actor,
                vendor_id=loaded.vendor_id,
                document_key=document.key,
                title=document.title,
                source_type=document.source_type,
                content=RevisionContent.from_bytes(
                    clean.texts[ref].encode("utf-8"), document.media_type
                ),
                version_label=revision.version_label,
                effective_date=revision.effective_date,
            )
        assert record.created is False and record.revision_id == loaded.revision_id
        with transaction(factory) as session:
            result = indexing.enqueue_index_revision(
                session, actor, revision_id=loaded.revision_id, identity=HASH_IDENTITY
            )
        assert result.outcome is indexing.EnqueueOutcome.READY
    assert _rows(engine) == before


def test_the_injected_variant_loads_and_evaluates_in_a_fresh_database(
    factory: sessionmaker[Session],
) -> None:
    injected = load_suite(SAMPLE, INJECTED)
    state = run_fresh_two_epoch(factory, injected)
    report = evaluate(factory, injected, state, HashingEmbedder())
    require_passing(report)
    body = json.loads(report_bytes(report))
    assert body["variant"] == INJECTED and body["status"] == "ok"
    assert "SYSTEM NOTE" not in report_bytes(report).decode()


def test_two_fresh_loads_are_structurally_equal(
    engine: Engine, factory: sessionmaker[Session], config: Config, clean: Suite
) -> None:
    first = run_fresh_two_epoch(factory, clean)
    first_json = json.loads(report_bytes(evaluate(factory, clean, first, HashingEmbedder())))
    _reset(engine, config)
    second = run_fresh_two_epoch(factory, clean)
    second_json = json.loads(report_bytes(evaluate(factory, clean, second, HashingEmbedder())))
    assert _structure(clean, first, first_json) == _structure(clean, second, second_json)


# --- verifier refusals, each leaving every row unchanged ----------------------------------------


def _refuses(engine: Engine, factory: sessionmaker[Session], suite: Suite) -> str:
    before = _rows(engine)
    code = _code(lambda: verify_loaded(factory, suite))
    assert _rows(engine) == before
    return code


def test_the_verifier_refuses_an_empty_and_a_seeded_only_database(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    assert _refuses(engine, factory, clean) == "corpus_state_incomplete"
    DatabaseAdminStore(factory).seed_demo()
    assert _refuses(engine, factory, clean) == "corpus_state_incomplete"


STOPPED = {
    "vendors": {"corpus_state_incomplete"},
    "first_upload": {"corpus_state_unsettled"},
    "r1_ingested": {"corpus_state_incomplete"},
    "r1_indexed": {"corpus_state_incomplete"},
    "initial_captured": {"corpus_state_incomplete"},
    "later_revisions": None,  # complete: the verifier accepts it
}


@pytest.mark.parametrize("phase", list(STOPPED))
def test_the_verifier_refuses_stopped_runs_and_the_fresh_run_refuses_them(
    engine: Engine, factory: sessionmaker[Session], clean: Suite, phase: str
) -> None:
    assert phase in PHASES
    assert _code(lambda: run_fresh_two_epoch(factory, clean, stop_after=phase)) == (
        "corpus_run_stopped"
    )
    expected = STOPPED[phase]
    if expected is None:
        verify_loaded(factory, clean)
    else:
        assert _refuses(engine, factory, clean) in expected
    before = _rows(engine)
    assert _code(lambda: run_fresh_two_epoch(factory, clean)) == "corpus_state_not_fresh"
    assert _rows(engine) == before


def _modified(path: str, old: bytes, new: bytes) -> Suite:
    files = _sample_files()
    assert files[path].count(old) == 1
    files[path] = files[path].replace(old, new)
    return build_suite(CLEAN, files)


def test_the_verifier_refuses_conflicting_metadata_and_content(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    run_fresh_two_epoch(factory, clean)
    retitled = _modified("corpus.toml", b'"Lumenvale Quarterly Newsletter"', b'"Newsletter"')
    assert _refuses(engine, factory, retitled) == "corpus_conflict"
    path = "documents/halverson-freight/lumenvale-cloud/company-newsletter@r1.md"
    files = _sample_files()
    files[path] = files[path] + b"\nOne more fictional sentence.\n"
    assert _refuses(engine, factory, build_suite(CLEAN, files)) == "corpus_conflict"


def test_the_verifier_refuses_an_extra_document(
    engine: Engine, factory: sessionmaker[Session], clean: Suite
) -> None:
    state = run_fresh_two_epoch(factory, clean)
    actor = _actor("halverson-freight")
    with transaction(factory) as session:
        create_upload(
            session,
            actor,
            vendor_id=state.loaded.vendors[("halverson-freight", "lumenvale-cloud")],
            document_key="unlisted-note",
            title="Unlisted Note",
            source_type=SourceType.VENDOR_STATEMENT,
            content=RevisionContent.from_bytes(
                b"A fictional unlisted note.\n", MediaType.TEXT_PLAIN
            ),
            version_label=None,
            effective_date=None,
        )
    assert _refuses(engine, factory, clean) == "corpus_state_unexpected"


def test_an_extra_profile_is_refused_by_the_verifier_and_the_fresh_run(
    engine: Engine, factory: sessionmaker[Session], clean: Suite, config: Config
) -> None:
    run_fresh_two_epoch(factory, clean)
    with transaction(factory) as session:
        embedding_store.ensure_profile(session, demo_tenant_id("marisol-clinics"), SECOND_IDENTITY)
    assert _refuses(engine, factory, clean) == "corpus_state_unexpected"

    _reset(engine, config)
    DatabaseAdminStore(factory).seed_demo()
    with transaction(factory) as session:
        embedding_store.ensure_profile(
            session, demo_tenant_id("halverson-freight"), SECOND_IDENTITY
        )
    before = _rows(engine)
    assert _code(lambda: run_fresh_two_epoch(factory, clean)) == "corpus_state_not_fresh"
    assert _rows(engine) == before


def test_logical_references_map_to_distinct_actual_revisions(
    factory: sessionmaker[Session], clean: Suite
) -> None:
    state = run_fresh_two_epoch(factory, clean)
    ids = [v.revision_id for v in state.loaded.revisions.values()]
    assert len(set(ids)) == len(ids) == 12
    r1 = state.loaded.revisions[
        RevisionRef("halverson-freight", "lumenvale-cloud", "data-retention-policy", 1)
    ]
    r2 = state.loaded.revisions[
        RevisionRef("halverson-freight", "lumenvale-cloud", "data-retention-policy", 2)
    ]
    assert r1.document_id == r2.document_id and r1.revision_id != r2.revision_id
