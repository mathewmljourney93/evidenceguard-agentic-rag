"""Retrieval values, canonical digests, query-vector conversion and pure fusion
(``evidenceguard_domain.retrieval``, M4d, ADR-0016), without a database.

Every expected canonical byte string, digest and derived UUID below was computed independently of
the module under test: the JSON literals were written by hand with sorted keys, hashed with
``hashlib``, and the UUIDs derived with ``uuid5`` from the fixed namespace literals. Fusion
expectations are hand-computed ``Fraction`` sums. These tests do not establish that PostgreSQL
ranks or filters correctly; ``test_retrieval_postgres.py`` does that against a real database.
"""

import dataclasses
import hashlib
import math
from datetime import UTC, date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Any
from uuid import UUID, uuid5

import pytest

from evidenceguard_domain import retrieval
from evidenceguard_domain.embeddings import (
    LEXICAL_HASH_LABEL,
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InvalidEmbeddingError,
)
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    ChannelHit,
    ChannelList,
    ChunkEvidence,
    FusedChunk,
    InvalidRetrievalRequestError,
    InvalidSnapshotError,
    PendingExclusions,
    RetrievalConfig,
    RetrievalRequest,
    RetrievalResult,
    RetrievalSnapshot,
    RetrievedChunk,
    RevisionBinding,
    SourceSpan,
    canonical_bytes,
    canonical_timestamp,
    fuse,
    query_vectors,
    revalidate_snapshot,
    vector_skipped,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder

TENANT = UUID("11111111-1111-4111-8111-111111111111")
VENDOR = UUID("22222222-2222-4222-8222-222222222222")
REV_A = UUID("33333333-3333-4333-8333-333333333333")
DOC_A = UUID("44444444-4444-4444-8444-444444444444")
REV_B = UUID("55555555-5555-4555-8555-555555555555")
DOC_B = UUID("66666666-6666-4666-8666-666666666666")
EXCLUDED = UUID("77777777-7777-4777-8777-777777777777")
VERSION = "md-v1"
HASH_FINGERPRINT = "ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376"
# uuid5(UUID("b6e99a93-…"), f"{TENANT}:{HASH_FINGERPRINT}") and the index IDs, by hand.
PROFILE = UUID("477f51ad-4553-52dc-af0e-bff10231d3ed")
INDEX_A = UUID("5b7601bd-c104-574b-afc4-8e43c3da8ecc")
INDEX_B = UUID("8eaf5c5b-c8a6-5fda-af5a-7d2071c6a86d")
CAPTURED = datetime(2026, 10, 17, 9, 30, 15, 120000, tzinfo=timezone(timedelta(hours=2)))
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
MARKER = "PRIVATE-MARKER-7f3a"
CHUNK_1 = UUID(int=1)

CONFIG_BYTES = (
    b'{"canonical":"eg-retrieval-canonical-v1","channel_limit":20,"default_k":8,'
    b'"kind":"retrieval_config","lexical_normalization":0,"lexical_query":"websearch_to_tsquery",'
    b'"lexical_score":"ts_rank_cd","max_k":20,"rrf_constant":60,"text_search_config":"simple",'
    b'"vector_operator":"cosine_distance","version":"hybrid-rrf-v1"}'
)
CONFIG_SHA256 = "d1859e0b781951cd00bdc33eba80023593391a3e16e572334a477bc692de7196"

SNAPSHOT_BYTES = (
    b'{"bindings":['
    b'{"chunk_count":2,"chunker_version":"md-v1","document_id":"44444444-4444-4444-8444-444444444444",'
    b'"index_id":"5b7601bd-c104-574b-afc4-8e43c3da8ecc","manifest_sha256":"' + b"a" * 64 + b'",'
    b'"revision_id":"33333333-3333-4333-8333-333333333333","vector_manifest_sha256":"'
    + b"b"
    * 64
    + b'"},'
    b'{"chunk_count":3,"chunker_version":"md-v1","document_id":"66666666-6666-4666-8666-666666666666",'
    b'"index_id":"8eaf5c5b-c8a6-5fda-af5a-7d2071c6a86d","manifest_sha256":"' + b"c" * 64 + b'",'
    b'"revision_id":"55555555-5555-4555-8555-555555555555","vector_manifest_sha256":"'
    + b"d"
    * 64
    + b'"}],'
    b'"canonical":"eg-retrieval-canonical-v1","captured_at":"2026-10-17T07:30:15.120000Z",'
    b'"config_sha256":"d1859e0b781951cd00bdc33eba80023593391a3e16e572334a477bc692de7196",'
    b'"exclusions":{"count":1,"revision_ids":["77777777-7777-4777-8777-777777777777"],'
    b'"truncated":false},'
    b'"kind":"retrieval_snapshot",'
    b'"profile":{"algorithm_version":"ascii-word-sha256-v1","dims":1024,'
    b'"fingerprint":"ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376",'
    b'"model_id":"fake-hash-v1","normalization":"l2",'
    b'"profile_id":"477f51ad-4553-52dc-af0e-bff10231d3ed","provider_id":"offline"},'
    b'"tenant_id":"11111111-1111-4111-8111-111111111111","total_chunks":5,'
    b'"vendor_id":"22222222-2222-4222-8222-222222222222"}'
)
SNAPSHOT_SHA256 = "b7e881c53aeaafd8ecf03efa9488a3c7b0799f46bec8b951e3e908fcd4d30bb7"


def u(n: int) -> UUID:
    return UUID(int=n)


def binding_a(**changes: Any) -> RevisionBinding:
    values: dict[str, Any] = {
        "revision_id": REV_A,
        "document_id": DOC_A,
        "index_id": INDEX_A,
        "chunker_version": VERSION,
        "chunk_count": 2,
        "manifest_sha256": "a" * 64,
        "vector_manifest_sha256": "b" * 64,
    }
    values.update(changes)
    return RevisionBinding(**values)


def binding_b() -> RevisionBinding:
    return RevisionBinding(REV_B, DOC_B, INDEX_B, VERSION, 3, "c" * 64, "d" * 64)


def exclusions(count: int = 1, ids: tuple[UUID, ...] = (EXCLUDED,)) -> PendingExclusions:
    return PendingExclusions(count, ids, count > 100)


def snapshot(**changes: Any) -> RetrievalSnapshot:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "vendor_id": VENDOR,
        "identity": HASH_IDENTITY,
        "config": RETRIEVAL_CONFIG_V1,
        "bindings": (binding_a(), binding_b()),
        "exclusions": exclusions(),
        "captured_at": CAPTURED,
    }
    values.update(changes)
    return RetrievalSnapshot(**values)


def evidence(chunk_id: UUID = CHUNK_1, **changes: Any) -> ChunkEvidence:
    values: dict[str, Any] = {
        "chunk_id": chunk_id,
        "text": "alpha bravo",
        "content_sha256": hashlib.sha256(b"alpha bravo").hexdigest(),
        "ordinal": 0,
        "section_path": ("Retention",),
        "is_table": False,
        "body": SourceSpan(3, 3, 13, 24),
        "header": None,
        "document_key": "data-retention",
        "title": "Data Retention",
        "revision_no": 1,
        "version_label": None,
        "effective_date": None,
        "source_type": SourceType.VENDOR_STATEMENT,
        "authenticity": Authenticity.NOT_ESTABLISHED,
    }
    values.update(changes)
    return ChunkEvidence(**values)


def hit(position: int = 0, channel: Any = "lexical", rank: int = 1, score: float = 1.0) -> Any:
    return ChannelHit(position, channel, rank, score)


def item(chunk_id: UUID = CHUNK_1, fused_rank: int = 1, **changes: Any) -> RetrievedChunk:
    values: dict[str, Any] = {
        "chunk_id": chunk_id,
        "revision_id": REV_A,
        "document_id": DOC_A,
        "fused_rank": fused_rank,
        "fused_score": Fraction(1, 61),
        "hits": (hit(),),
        "evidence": evidence(chunk_id),
    }
    values.update(changes)
    return RetrievedChunk(**values)


# --- errors ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (retrieval.InvalidRetrievalRequestError, "invalid_retrieval_request"),
        (retrieval.InvalidSnapshotError, "invalid_snapshot"),
        (retrieval.RetrievalScopeError, "retrieval_scope"),
        (retrieval.EmptySnapshotError, "snapshot_empty"),
        (retrieval.SnapshotBoundsError, "snapshot_bounds_exceeded"),
        (retrieval.SnapshotNotReadyError, "snapshot_not_ready"),
        (retrieval.SnapshotInconsistentError, "snapshot_inconsistent"),
        (retrieval.RetrievalProviderError, "retrieval_provider_failed"),
        (retrieval.RetrievalDatabaseError, "retrieval_database_failed"),
    ],
)
def test_errors_have_fixed_code_messages_and_take_no_arguments(error: Any, code: str) -> None:
    instance = error()
    assert str(instance) == code and instance.args == (code,) and error.code == code
    with pytest.raises(TypeError):
        error(MARKER)


# --- configuration and canonical encoding -------------------------------------------------------


def test_config_canonical_bytes_and_digest_are_pinned() -> None:
    assert hashlib.sha256(CONFIG_BYTES).hexdigest() == CONFIG_SHA256  # the literal itself
    assert canonical_bytes(RETRIEVAL_CONFIG_V1.canonical_object()) == CONFIG_BYTES
    assert RETRIEVAL_CONFIG_V1.config_sha256 == CONFIG_SHA256
    assert RetrievalConfig() == RETRIEVAL_CONFIG_V1


@pytest.mark.parametrize(
    "change",
    [
        {"version": "hybrid-rrf-v2"},
        {"text_search_config": "english"},
        {"lexical_normalization": False},
        {"lexical_normalization": 1},
        {"channel_limit": 21},
        {"rrf_constant": 60.0},
        {"max_k": 19},
        {"config_sha256": CONFIG_SHA256},
        {"unknown": 1},
    ],
)
def test_only_the_v1_configuration_is_accepted(change: dict[str, Any]) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        RetrievalConfig(**change)


def test_config_replace_revalidates_and_derived_digest_cannot_be_supplied() -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        dataclasses.replace(RETRIEVAL_CONFIG_V1, version="other")
    with pytest.raises(ValueError, match="init=False"):
        dataclasses.replace(RETRIEVAL_CONFIG_V1, config_sha256="0" * 64)


@pytest.mark.parametrize(
    "value",
    [
        {"x": 1.5},
        {"x": None},
        {"x": (1, 2)},
        {"x": UUID(int=1)},
        {1: "x"},
        {"x": float("nan")},
        {"x": {"y": [b"bytes"]}},
        {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": 1}}}}}}}}}},
    ],
)
def test_canonical_encoding_rejects_values_it_does_not_list(value: Any) -> None:
    with pytest.raises(InvalidSnapshotError):
        canonical_bytes(value)


def test_canonical_encoding_is_ascii_sorted_and_compact() -> None:
    assert canonical_bytes({"b": [True, 1], "a": "é"}) == b'{"a":"\\u00e9","b":[true,1]}'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), "2026-01-02T03:04:05.000000Z"),
        (
            datetime(2026, 1, 1, 0, 30, 0, 7, tzinfo=timezone(timedelta(hours=1))),
            "2025-12-31T23:30:00.000007Z",
        ),
        (datetime(5, 6, 7, 8, 9, 10, 999999, tzinfo=UTC), "0005-06-07T08:09:10.999999Z"),
    ],
)
def test_canonical_timestamps_are_utc_with_six_fractional_digits(
    value: datetime, expected: str
) -> None:
    assert canonical_timestamp(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        datetime(2026, 1, 1),  # naive
        datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))),  # overflows on conversion
        date(2026, 1, 1),
        "2026-01-01T00:00:00Z",
    ],
)
def test_invalid_timestamps_are_rejected(value: Any) -> None:
    with pytest.raises(InvalidSnapshotError):
        canonical_timestamp(value)
    with pytest.raises(InvalidSnapshotError):
        snapshot(captured_at=value)


# --- snapshot -----------------------------------------------------------------------------------


def test_snapshot_canonical_bytes_digest_and_derived_values_are_pinned() -> None:
    assert hashlib.sha256(SNAPSHOT_BYTES).hexdigest() == SNAPSHOT_SHA256  # the literal itself
    captured = snapshot()
    assert captured.canonical_bytes() == SNAPSHOT_BYTES
    assert captured.sha256 == SNAPSHOT_SHA256
    assert captured.profile_id == PROFILE and captured.total_chunks == 5
    assert captured.identity.fingerprint == HASH_FINGERPRINT
    assert captured.captured_at == CAPTURED and captured.captured_at.tzinfo is UTC
    assert captured.profile_label == LEXICAL_HASH_LABEL
    # The pinned IDs are uuid5 values of the fixed namespaces, computed here independently.
    profile_ns = UUID("b6e99a93-0055-5a05-970d-26eb33f56723")
    index_ns = UUID("5adfc50a-fb67-5caa-a6ca-81c69eaf4285")
    assert uuid5(profile_ns, f"{TENANT}:{HASH_FINGERPRINT}") == PROFILE
    assert uuid5(index_ns, f"{TENANT}:{REV_A}:{VERSION}:{PROFILE}") == INDEX_A


def test_identical_encoded_fields_give_the_same_digest_and_timestamps_change_it() -> None:
    same_instant = CAPTURED.astimezone(UTC)
    assert snapshot(captured_at=same_instant).sha256 == SNAPSHOT_SHA256
    later = snapshot(captured_at=CAPTURED + timedelta(microseconds=1))
    assert later.sha256 != SNAPSHOT_SHA256  # informational provenance is in the digest


def test_snapshot_replace_revalidates_and_derived_values_cannot_be_supplied() -> None:
    captured = snapshot()
    changed = dataclasses.replace(captured, exclusions=exclusions(0, ()))
    assert changed.sha256 != captured.sha256
    with pytest.raises(InvalidSnapshotError):
        dataclasses.replace(captured, bindings=(binding_b(), binding_a()))
    for derived in ("sha256", "profile_id", "total_chunks"):
        with pytest.raises(ValueError, match="init=False"):
            changes: dict[str, Any] = {derived: None}
            dataclasses.replace(captured, **changes)


def test_a_snapshot_altered_after_construction_fails_revalidation() -> None:
    captured = snapshot()
    assert revalidate_snapshot(captured) == captured
    object.__setattr__(captured, "sha256", "0" * 64)
    with pytest.raises(InvalidSnapshotError):
        revalidate_snapshot(captured)
    with pytest.raises(InvalidSnapshotError):
        revalidate_snapshot(dataclasses.asdict(snapshot()))


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": str(TENANT)},
        {"vendor_id": None},
        {"identity": LIVE.__class__("voyage", "m", "a", 512, "l2")},  # not storable
        {"identity": "offline"},
        {"config": object()},
        {"bindings": [binding_a(), binding_b()]},  # a list, not a tuple
        {"bindings": ()},
        {"bindings": (binding_b(), binding_a())},  # unsorted
        {"bindings": (binding_a(), binding_a())},  # duplicate revision
        {"exclusions": None},
        {"exclusions": exclusions(1, (REV_A,))},  # an excluded revision cannot be bound
        {"unknown": 1},
    ],
)
def test_invalid_snapshots_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(InvalidSnapshotError):
        snapshot(**change)


def test_one_binding_per_document_and_derived_index_ids_are_required() -> None:
    two_for_one_document = RevisionBinding(
        REV_B,
        DOC_A,
        INDEX_B,
        VERSION,
        3,
        "c" * 64,
        "d" * 64,
    )
    with pytest.raises(InvalidSnapshotError):
        snapshot(bindings=(binding_a(), two_for_one_document))
    with pytest.raises(InvalidSnapshotError):
        snapshot(bindings=(binding_a(index_id=INDEX_B),))
    with pytest.raises(InvalidSnapshotError):  # the index ID is tenant-derived
        snapshot(tenant_id=VENDOR)


def test_snapshot_bounds_100_revisions_and_100000_chunks() -> None:
    def bindings(count: int, chunks: int) -> tuple[RevisionBinding, ...]:
        values = []
        for n in range(1, count + 1):
            revision = u(n)
            values.append(
                RevisionBinding(
                    revision,
                    u(10_000 + n),
                    uuid5(
                        UUID("5adfc50a-fb67-5caa-a6ca-81c69eaf4285"),
                        f"{TENANT}:{revision}:{VERSION}:{PROFILE}",
                    ),
                    VERSION,
                    chunks,
                    "a" * 64,
                    "b" * 64,
                )
            )
        return tuple(values)

    full = snapshot(bindings=bindings(100, 1000), exclusions=exclusions(0, ()))
    assert full.total_chunks == 100_000
    with pytest.raises(InvalidSnapshotError):
        snapshot(bindings=bindings(101, 1), exclusions=exclusions(0, ()))
    over = (*bindings(25, 4000), *bindings(26, 1)[25:])  # 100,001 chunks
    with pytest.raises(InvalidSnapshotError):
        snapshot(bindings=over, exclusions=exclusions(0, ()))


@pytest.mark.parametrize(
    "change",
    [
        {"revision_id": str(REV_A)},
        {"chunker_version": "Upper"},
        {"chunker_version": "x" * 33},
        {"chunk_count": 0},
        {"chunk_count": 4097},
        {"chunk_count": True},
        {"manifest_sha256": "A" * 64},
        {"vector_manifest_sha256": "b" * 63},
        {"extra": 1},
    ],
)
def test_invalid_bindings_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(InvalidSnapshotError):
        binding_a(**change)


def test_exclusions_count_ids_and_truncation_are_consistent() -> None:
    ids = tuple(u(n) for n in range(1, 101))
    assert PendingExclusions(100, ids, False).revision_ids == ids
    assert PendingExclusions(250, ids, True).truncated
    assert PendingExclusions(0, (), False).count == 0
    for count, values, truncated in [
        (101, ids, False),  # truncated must be true above 100
        (100, ids, True),
        (2, (u(1),), False),  # count/ID mismatch
        (2, (u(2), u(1)), False),  # unsorted
        (2, (u(1), u(1)), False),  # duplicate
        (-1, (), False),
        (True, (u(1),), False),
        (1, [u(1)], False),
        (1, ("x",), False),
        (1, (u(1),), 0),
    ]:
        with pytest.raises(InvalidSnapshotError):
            PendingExclusions(count, values, truncated)  # type: ignore[arg-type]


def test_snapshot_representations_show_ids_and_counts_only() -> None:
    captured = snapshot()
    text = repr(captured) + str(captured) + repr(binding_a()) + repr(exclusions())
    assert str(TENANT) in text and "total_chunks=5" in text
    assert "a" * 64 not in text and HASH_FINGERPRINT not in text


# --- request -------------------------------------------------------------------------------------


def test_requests_keep_queries_verbatim() -> None:
    request = RetrievalRequest(("  Retention period?\t", "\U0001d538 supplementary"))
    assert request.queries == ("  Retention period?\t", "\U0001d538 supplementary")
    assert request.k == 8
    assert RetrievalRequest(("a",), 1).k == 1 and RetrievalRequest(("a",), 20).k == 20
    assert len(RetrievalRequest(tuple(str(n) for n in range(8))).queries) == 8
    assert RetrievalRequest(("x" * 4000,)).queries[0] == "x" * 4000
    assert RetrievalRequest(("é" * 4000,)).queries  # 8,000 bytes
    assert RetrievalRequest(("Retention", "retention")).queries  # exact equality only


@pytest.mark.parametrize(
    ("queries", "k"),
    [
        ((), 8),
        (tuple(str(n) for n in range(9)), 8),
        (["a"], 8),
        (("",), 8),
        ((" \t\n",), 8),
        (("a\x00b",), 8),
        (("\ud800",), 8),  # lone surrogate
        (("x" * 4001,), 8),
        (("\U0001d538" * 4001,), 8),  # 4,001 code points
        (("a", "a"), 8),  # duplicate, rejected not merged
        ((b"a",), 8),
        (("a",), 0),
        (("a",), 21),
        (("a",), True),
        (("a",), 8.0),
    ],
)
def test_invalid_requests_are_rejected(queries: Any, k: Any) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        RetrievalRequest(queries, k)


def test_request_bytes_bound_unknown_fields_replace_and_representation() -> None:
    # 4,000 supplementary code points are exactly 16,000 UTF-8 bytes: the largest valid query.
    assert len(RetrievalRequest(("\U0001d538" * 4000,)).queries[0].encode()) == 16_000
    with pytest.raises(InvalidRetrievalRequestError):
        RetrievalRequest(("a",), 8, extra=1)
    request = RetrievalRequest(("a",))
    with pytest.raises(InvalidRetrievalRequestError):
        dataclasses.replace(request, k=0)
    assert MARKER not in repr(RetrievalRequest((MARKER,))) + str(RetrievalRequest((MARKER,)))


# --- channel lists and hits ----------------------------------------------------------------------


def test_channel_lists_accept_the_documented_orders() -> None:
    lexical = ChannelList(0, "lexical", ((u(1), 2.0), (u(2), 1.0), (u(3), 1.0)))
    vector = ChannelList(7, "vector", ((u(9), -1e-9), (u(2), 0.5), (u(3), 0.5)))
    assert len(lexical.entries) == 3 and vector.query_position == 7
    assert ChannelList(0, "vector", ()).entries == ()
    full = tuple((u(n), float(100 - n)) for n in range(20))
    assert len(ChannelList(0, "lexical", full).entries) == 20


@pytest.mark.parametrize(
    ("position", "channel", "entries"),
    [
        (0, "lexical", ((u(1), 1.0), (u(1), 0.5))),  # duplicate chunk
        (0, "lexical", ((u(1), 1.0), (u(2), 2.0))),  # increasing lexical
        (0, "vector", ((u(1), 0.5), (u(2), 0.1))),  # decreasing distance
        (0, "lexical", ((u(2), 1.0), (u(1), 1.0))),  # tie not by UUID
        (0, "vector", ((u(2), 0.1), (u(1), 0.1))),
        (0, "lexical", ((u(1), 0.0),)),  # non-positive lexical
        (0, "lexical", ((u(1), -1.0),)),
        (0, "vector", ((u(1), math.nan),)),
        (0, "vector", ((u(1), math.inf),)),
        (0, "vector", ((u(1), 1),)),  # int score
        (0, "vector", ((str(u(1)), 0.1),)),
        (0, "vector", [(u(1), 0.1)]),
        (0, "vector", ((u(1), 0.1, 0),)),
        (0, "vector", tuple((u(n), float(n)) for n in range(21))),  # more than 20
        (8, "vector", ()),
        (-1, "vector", ()),
        (True, "vector", ()),
        (0, "semantic", ()),
    ],
)
def test_invalid_channel_lists_are_rejected(position: Any, channel: Any, entries: Any) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        ChannelList(position, channel, entries)


@pytest.mark.parametrize(
    ("position", "channel", "rank", "score"),
    [
        (0, "lexical", 0, 1.0),
        (0, "lexical", 21, 1.0),
        (0, "lexical", 1, 0.0),
        (0, "vector", 1, math.nan),
        (0, "vector", True, 0.1),
        (8, "vector", 1, 0.1),
        (0, "other", 1, 0.1),
    ],
)
def test_invalid_hits_are_rejected(position: Any, channel: Any, rank: Any, score: Any) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        ChannelHit(position, channel, rank, score)


# --- fusion --------------------------------------------------------------------------------------


def test_fusion_matches_the_pinned_fixture() -> None:
    lists = (
        ChannelList(0, "lexical", ((u(1), 2.0), (u(2), 1.0))),
        ChannelList(0, "vector", ((u(2), 0.1), (u(3), 0.2))),
    )
    fused = fuse(lists, query_count=1, vector_skipped=(), k=8)
    assert [(c.chunk_id, c.fused_rank, c.fused_score) for c in fused] == [
        (u(2), 1, Fraction(123, 3782)),  # 1/61 + 1/62
        (u(1), 2, Fraction(1, 61)),
        (u(3), 3, Fraction(1, 62)),
    ]
    assert [(h.query_position, h.channel, h.rank, h.score) for h in fused[0].hits] == [
        (0, "lexical", 2, 1.0),
        (0, "vector", 1, 0.1),
    ]


def test_fusion_sums_duplicates_across_queries_and_channels() -> None:
    lists = (
        ChannelList(1, "vector", ((u(5), 0.2),)),
        ChannelList(0, "lexical", ((u(4), 3.0), (u(5), 2.0))),
        ChannelList(1, "lexical", ((u(5), 9.0),)),
    )
    fused = fuse(lists, query_count=2, vector_skipped=(0,), k=8)
    assert fused[0].chunk_id == u(5)
    assert fused[0].fused_score == Fraction(1, 62) + Fraction(1, 61) + Fraction(1, 61)
    assert [h.key for h in fused[0].hits] == [(0, "lexical"), (1, "lexical"), (1, "vector")]
    assert fused[1].chunk_id == u(4) and fused[1].fused_score == Fraction(1, 61)


def test_equal_fused_scores_tie_by_ascending_uuid() -> None:
    lists = (
        ChannelList(0, "lexical", ((u(9), 1.0), (u(3), 0.5))),
        ChannelList(0, "vector", ((u(3), 0.1), (u(9), 0.2))),
    )
    fused = fuse(lists, query_count=1, vector_skipped=(), k=2)
    assert fused[0].fused_score == fused[1].fused_score
    assert [c.chunk_id for c in fused] == [u(3), u(9)]


def _filled(position: int, channel: Any, placed: dict[int, UUID], length: int) -> ChannelList:
    entries = []
    for rank in range(1, length + 1):
        chunk = placed.get(
            rank, u(1000 + 100 * position + (50 if channel == "vector" else 0) + rank)
        )
        score = float(100 - rank) if channel == "lexical" else rank / 100
        entries.append((chunk, score))
    return ChannelList(position, channel, tuple(entries))


def test_exact_fractions_tie_where_float_addition_order_would_not() -> None:
    x, y = u(10), u(11)  # x sorts first
    lists = (
        _filled(0, "lexical", {1: x, 2: y}, 2),
        _filled(0, "vector", {2: x, 1: y}, 2),
        _filled(1, "lexical", {3: x, 9: y}, 9),
        _filled(1, "vector", {9: x, 3: y}, 9),
    )

    def f(rank: int) -> float:
        return 1 / (60 + rank)

    float_x = ((f(1) + f(2)) + f(3)) + f(9)  # summed in list order
    float_y = ((f(2) + f(1)) + f(9)) + f(3)
    assert float_x < float_y  # float order would rank y first

    fused = fuse(lists, query_count=2, vector_skipped=(), k=20)
    scores = {c.chunk_id: c for c in fused}
    assert scores[x].fused_score == scores[y].fused_score
    assert scores[x].fused_rank < scores[y].fused_rank  # exact tie, broken by UUID


def test_fewer_than_k_candidates_and_the_empty_result() -> None:
    fused = fuse(
        (ChannelList(0, "lexical", ((u(1), 1.0),)),), query_count=1, vector_skipped=(), k=8
    )
    assert len(fused) == 1
    assert fuse((), query_count=1, vector_skipped=(), k=8) == ()
    assert fuse((ChannelList(0, "lexical", ()),), query_count=1, vector_skipped=(), k=1) == ()
    many = tuple((u(n), float(100 - n)) for n in range(20))
    assert len(fuse((ChannelList(0, "lexical", many),), query_count=1, vector_skipped=(), k=5)) == 5


@pytest.mark.parametrize(
    ("lists", "query_count", "skipped", "k"),
    [
        ((ChannelList(0, "lexical", ()), ChannelList(0, "lexical", ())), 1, (), 8),
        ((ChannelList(1, "lexical", ()),), 1, (), 8),  # position beyond query_count
        ((ChannelList(0, "vector", ()),), 1, (0,), 8),  # vector list for a skipped position
        ((), 1, (1,), 8),
        ((), 2, (1, 0), 8),
        ((), 1, [0], 8),
        ([], 1, (), 8),
        (("list",), 1, (), 8),
        ((), 0, (), 8),
        ((), 9, (), 8),
        ((), 1, (), 0),
        ((), 1, (), 21),
    ],
)
def test_invalid_fusion_inputs_are_rejected(
    lists: Any, query_count: Any, skipped: Any, k: Any
) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        fuse(lists, query_count=query_count, vector_skipped=skipped, k=k)


def test_fusion_revalidates_lists_altered_after_construction() -> None:
    altered = ChannelList(0, "lexical", ((u(1), 1.0),))
    object.__setattr__(altered, "entries", ((u(1), 1.0), (u(1), 0.5)))
    with pytest.raises(InvalidRetrievalRequestError):
        fuse((altered,), query_count=1, vector_skipped=(), k=8)


def test_fused_chunks_require_the_exact_rrf_sum_and_ordered_hits() -> None:
    assert FusedChunk(u(1), 1, Fraction(1, 61), (hit(),)).fused_score == Fraction(1, 61)
    for score, hits in [
        (Fraction(1, 62), (hit(),)),
        (1 / 61, (hit(),)),
        (Fraction(0), ()),
        (Fraction(1, 61) * 2, (hit(), hit())),  # duplicate (position, channel)
        (
            Fraction(1, 61) * 2,
            (hit(0, "vector", 1, 0.1), hit(0, "lexical", 1, 1.0)),
        ),  # vector before lexical
    ]:
        with pytest.raises(InvalidRetrievalRequestError):
            FusedChunk(u(1), 1, score, hits)  # type: ignore[arg-type]


# --- query vectors -------------------------------------------------------------------------------


def _axis(position: int) -> tuple[float, ...]:
    return tuple(1.0 if i == position else 0.0 for i in range(1024))


def test_query_vectors_convert_and_mark_zero_vectors_skipped() -> None:
    batch = HashingEmbedder().embed(("retention period", "éàü"), "query")
    vectors = query_vectors(batch, identity=HASH_IDENTITY, query_count=2)
    assert not vectors[0].is_zero and vectors[1].is_zero
    assert vector_skipped(vectors) == (1,)


@pytest.mark.parametrize(
    "case",
    ["document", "count", "identity", "type", "zero_live", "overflow", "norm_after_rounding"],
)
def test_query_vector_conversion_failures_are_fixed_errors(case: str) -> None:
    identity = HASH_IDENTITY
    count = 1
    if case == "document":
        batch: Any = HashingEmbedder().embed(("a",), "document")
    elif case == "count":
        batch = HashingEmbedder().embed(("a", "b"), "query")
    elif case == "identity":
        batch = HashingEmbedder().embed(("a",), "query")
        identity = LIVE
    elif case == "type":
        batch = (_axis(0),)
    elif case == "zero_live":
        identity = LIVE
        batch = EmbeddingBatch(LIVE, "query", (_axis(0),), EmbeddingUsage(None))
        object.__setattr__(batch, "vectors", (tuple(0.0 for _ in range(1024)),))
    elif case == "overflow":
        # A coordinate beyond the float32 range: finite as a float64, so only the batch
        # revalidation (its norm) or the float32 conversion can reject it.
        vector = list(_axis(0))
        vector[1] = 3.5e38
        batch = EmbeddingBatch(HASH_IDENTITY, "query", (_axis(0),), EmbeddingUsage(None))
        object.__setattr__(batch, "vectors", (tuple(vector),))
    else:
        # 0.999999001 passes the provider tolerance but rounds below it (see ADR-0014).
        vector = list(_axis(0))
        vector[0] = 0.999999001
        batch = EmbeddingBatch(HASH_IDENTITY, "query", (tuple(vector),), EmbeddingUsage(None))
    with pytest.raises(InvalidEmbeddingError):
        query_vectors(batch, identity=identity, query_count=count)


def test_query_vector_inputs_are_strict() -> None:
    batch = HashingEmbedder().embed(("a",), "query")
    for count in (0, 9, True, 1.0):
        with pytest.raises(InvalidEmbeddingError):
            query_vectors(batch, identity=HASH_IDENTITY, query_count=count)  # type: ignore[arg-type]
    with pytest.raises(InvalidEmbeddingError):
        query_vectors(batch, identity=LIVE.__class__("x", "y", "z", 512, "l2"), query_count=1)


# --- evidence and results ----------------------------------------------------------------------


def test_evidence_splits_a_repeated_header_from_the_body() -> None:
    header_text, body_text = "| Key | Value |\n|---|---|\n", "| r9 | v9 |"
    text = header_text + body_text
    table = evidence(
        text=text,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
        is_table=True,
        header=SourceSpan(3, 4, 9, 9 + len(header_text)),
        body=SourceSpan(20, 20, 400, 400 + len(body_text)),
    )
    assert table.header_text == header_text and table.body_text == body_text
    plain = evidence()
    assert plain.header_text is None and plain.body_text == plain.text == "alpha bravo"
    assert "alpha" not in repr(table) + str(table) + repr(plain)
    assert "Retention" not in repr(plain)


@pytest.mark.parametrize(
    "change",
    [
        {"content_sha256": "0" * 64},  # digest mismatch
        {"text": "\ud800" * 11},
        {"text": ""},
        {"body": SourceSpan(3, 3, 13, 25)},  # body length mismatch
        {"header": SourceSpan(1, 1, 0, 5)},  # header on a non-table chunk
        {"is_table": True, "header": SourceSpan(3, 3, 0, 5)},  # header line not before body
        {"section_path": ["Retention"]},
        {"section_path": tuple("abcdefg")},
        {"ordinal": 4096},
        {"revision_no": 0},
        {"effective_date": datetime(2026, 1, 1, tzinfo=UTC)},
        {"source_type": "vendor_statement"},
        {"authenticity": "not_established"},
        {"version_label": 1},
        {"document_key": ""},
        {"chunk_id": "x"},
        {"extra": 1},
    ],
)
def test_invalid_evidence_is_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(InvalidRetrievalRequestError):
        evidence(**change)


def test_results_derive_snapshot_facts_and_check_ranks_and_ownership() -> None:
    captured = snapshot()
    result = RetrievalResult(captured, 1, 8, (), (item(),))
    assert result.tenant_id == TENANT and result.vendor_id == VENDOR
    assert result.snapshot_sha256 == SNAPSHOT_SHA256 and result.config_sha256 == CONFIG_SHA256
    assert result.profile_fingerprint == HASH_FINGERPRINT
    assert result.profile_label == LEXICAL_HASH_LABEL
    assert result.items[0].display_score == pytest.approx(1 / 61)
    assert RetrievalResult(captured, 1, 8, (0,), ()).items == ()
    text = repr(result) + str(result) + repr(result.items[0])
    assert "alpha" not in text and "Retention" not in text


@pytest.mark.parametrize(
    "case",
    [
        "too_many",
        "rank_gap",
        "duplicate",
        "order",
        "tie_order",
        "foreign_revision",
        "mismatched_document",
        "position",
        "skipped_vector_hit",
        "unsorted_skipped",
        "snapshot",
        "evidence_id",
    ],
)
def test_inconsistent_results_are_rejected(case: str) -> None:
    captured = snapshot()
    two = Fraction(1, 61) + Fraction(1, 61)
    items: tuple[Any, ...] = (item(),)
    query_count, k = 2, 8
    skipped: tuple[int, ...] = ()
    if case == "too_many":
        k = 1
        items = (item(u(1), 1, fused_score=two, hits=(hit(), hit(1))), item(u(2), 2))
    elif case == "rank_gap":
        items = (item(u(1), 2),)
    elif case == "duplicate":
        items = (item(u(1), 1, fused_score=two, hits=(hit(), hit(1))), item(u(1), 2))
    elif case == "order":
        items = (item(u(1), 1), item(u(2), 2, fused_score=two, hits=(hit(), hit(1))))
    elif case == "tie_order":
        items = (item(u(2), 1), item(u(1), 2))
    elif case == "foreign_revision":
        items = (item(revision_id=u(99)),)
    elif case == "mismatched_document":
        items = (item(document_id=DOC_B),)
    elif case == "position":
        items = (item(fused_score=Fraction(1, 61), hits=(hit(2),)),)
        query_count = 2
    elif case == "skipped_vector_hit":
        items = (item(hits=(hit(0, "vector", 1, 0.1),)),)
        skipped = (0,)
    elif case == "unsorted_skipped":
        skipped = (1, 0)
    elif case == "snapshot":
        captured = dataclasses.asdict(captured)  # type: ignore[assignment]
    else:
        with pytest.raises(InvalidRetrievalRequestError):
            item(evidence=evidence(u(2)))
        return
    with pytest.raises(InvalidRetrievalRequestError):
        RetrievalResult(captured, query_count, k, skipped, items)
