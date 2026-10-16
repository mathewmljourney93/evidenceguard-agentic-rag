"""Canonical stored embedding values (``evidenceguard_domain.embedding_storage``, M4b,
ADR-0014), without a database.

Every expected digest, UUID and float32 value below was calculated independently of the module
under test, from literal bytes with the standard library (``struct``, ``hashlib``, ``uuid``), and
is pinned as a literal. These tests prove the application side of the storage contract only;
agreement with PostgreSQL's ``vector_send``/``vector_norm`` is checked by
``test_embeddings_postgres.py``, which runs only against a real database.
"""

import hashlib
import math
import struct
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from evidenceguard_domain import embedding_storage as storage
from evidenceguard_domain.embedding_storage import (
    INDEX_ID_NAMESPACE,
    PROFILE_ID_NAMESPACE,
    STORED_DIMS,
    StoredEmbedding,
    StoredVector,
    canonical_vector,
    decode_wire,
    index_id,
    profile_id,
    revalidate_rows,
    stored_embeddings,
    vector_manifest_sha256,
)
from evidenceguard_domain.embeddings import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InvalidEmbeddingError,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY, HashingEmbedder

TENANT = UUID("66666666-6666-4666-8666-666666666666")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
CHUNK_0 = UUID("33333333-3333-4333-8333-333333333333")
CHUNK_1 = UUID("44444444-4444-4444-8444-444444444444")
VERSION = "text-md-v1"
HASH_FINGERPRINT = "ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376"
LIVE = EmbeddingIdentity("voyage", "voyage-4-lite", "adapter-v1", 1024, "l2")
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

# struct.pack('>HH', 1024, 0) + big-endian float32 coordinates, hashed independently.
E0_SHA256 = "88072432d21607cffcd341d01a2edd0c6c638b942a47c84ac2572646c238aae0"  # [1.0, 0, …]
ZERO_SHA256 = "9f3bbabb5640ba70df6a190cdcd1c881a86347ef9fbf0493f3e2cb558f3e0724"
QUARTER_SHA256 = "2f78a023b5a5f774a72a85771de1f3446da3603b192384864d18dbca6dbb0473"  # all 1/32
PROFILE_ID = UUID("67b0b3a7-dcac-5e2a-a419-a47058c9dc22")
INDEX_ID = UUID("9a15ed4b-d10d-546f-b607-78e3884be2b5")
MANIFEST_SHA256 = "5426e9b8559fa8f5539c3e8107ff0f5d8995a7236b0072223f35036340b381e0"

# Adjacent float32 values around the tolerance edges (bit patterns 0x3F800000 - 17/-16, +8/+9).
BELOW_REJECTED = 0.9999989867210388
BELOW_ACCEPTED = 0.9999990463256836
ABOVE_ACCEPTED = 1.0000009536743164
ABOVE_REJECTED = 1.000001072883606


def axis(value: float, index: int = 0) -> tuple[float, ...]:
    return tuple(value if i == index else 0.0 for i in range(STORED_DIMS))


def provider_batch(*vectors: tuple[float, ...], identity: EmbeddingIdentity) -> EmbeddingBatch:
    return EmbeddingBatch(identity, "document", tuple(vectors), EmbeddingUsage(None))


# --- fixed namespaces and IDs ----------------------------------------------------------------


def test_namespaces_are_the_documented_literals() -> None:
    assert (
        uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/embedding-profile-id/v1")
        == PROFILE_ID_NAMESPACE
        == UUID("b6e99a93-0055-5a05-970d-26eb33f56723")
    )
    assert (
        uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/embedding-index-id/v1")
        == INDEX_ID_NAMESPACE
        == UUID("5adfc50a-fb67-5caa-a6ca-81c69eaf4285")
    )


def test_profile_and_index_ids_are_pinned() -> None:
    assert HASH_IDENTITY.fingerprint == HASH_FINGERPRINT
    assert profile_id(TENANT, HASH_FINGERPRINT) == PROFILE_ID
    assert index_id(TENANT, REVISION, VERSION, PROFILE_ID) == INDEX_ID
    # Tenant scope: the same identity in another tenant is a different profile.
    other = UUID("77777777-7777-4777-8777-777777777777")
    assert profile_id(other, HASH_FINGERPRINT) != PROFILE_ID


@pytest.mark.parametrize(
    "call",
    [
        lambda: profile_id(str(TENANT), HASH_FINGERPRINT),  # type: ignore[arg-type]
        lambda: profile_id(TENANT, HASH_FINGERPRINT.upper()),
        lambda: index_id(TENANT, REVISION, "Bad Version", PROFILE_ID),
        lambda: index_id(TENANT, str(REVISION), VERSION, PROFILE_ID),  # type: ignore[arg-type]
    ],
)
def test_id_inputs_are_strict(call: object) -> None:
    with pytest.raises((InvalidEmbeddingError, ValueError)):
        call()  # type: ignore[operator]


# --- wire bytes, digests and literals ---------------------------------------------------------


def test_wire_bytes_match_pgvector_send_format_and_pinned_digests() -> None:
    e0 = canonical_vector(axis(1.0), allows_zero=False)
    assert e0.wire_bytes() == b"\x04\x00\x00\x00" + b"\x3f\x80\x00\x00" + b"\x00" * 4092
    assert e0.sha256 == E0_SHA256 and not e0.is_zero
    zero = canonical_vector(axis(0.0), allows_zero=True)
    assert zero.sha256 == ZERO_SHA256 and zero.is_zero
    quarter = canonical_vector(tuple([1 / 32] * STORED_DIMS), allows_zero=False)
    assert quarter.wire_bytes() == b"\x04\x00\x00\x00" + b"\x3d\x00\x00\x00" * STORED_DIMS
    assert quarter.sha256 == QUARTER_SHA256
    assert decode_wire(quarter.wire_bytes()) == quarter.coordinates


def test_text_literal_round_trips_to_the_same_float32_values() -> None:
    values = [0.1, -0.2, 1e-30, 1.401298464324817e-45, 0.6, 0.3]
    vector = list(axis(0.0))
    vector[: len(values)] = values
    norm = math.hypot(*vector)
    unit = tuple(value / norm for value in vector)
    stored = canonical_vector(unit, allows_zero=False)
    literal = stored.literal()
    assert literal.startswith("[") and literal.endswith("]") and " " not in literal
    parsed = tuple(
        struct.unpack(">f", struct.pack(">f", float(text)))[0] for text in literal[1:-1].split(",")
    )
    assert parsed == stored.coordinates  # what strtof yields equals the canonical value


def test_negative_zero_is_canonicalized() -> None:
    vector = list(axis(1.0))
    vector[5] = -0.0
    stored = canonical_vector(tuple(vector), allows_zero=False)
    assert math.copysign(1.0, stored.coordinates[5]) == 1.0
    assert stored.sha256 == E0_SHA256
    with pytest.raises(InvalidEmbeddingError):
        StoredVector(tuple(vector), allows_zero=False)  # canonical values never hold -0.0


def test_decode_rejects_wrong_headers_and_lengths() -> None:
    good = canonical_vector(axis(1.0), allows_zero=False).wire_bytes()
    for data in (good[:-4], b"\x04\x01" + good[2:], b"\x00\x03" + good[2:], bytearray(good)):
        with pytest.raises(InvalidEmbeddingError):
            decode_wire(data)  # type: ignore[arg-type]


# --- post-rounding storage validation ------------------------------------------------------


def test_the_accepted_lower_boundary_example_passes_m4a_but_is_rejected_after_rounding() -> None:
    """The reviewer's case (Prompt 115): provider validity does not imply storage validity."""
    provider = provider_batch(axis(0.999999001), identity=LIVE)  # accepted by M4a
    assert struct.unpack(">f", struct.pack(">f", 0.999999001))[0] == BELOW_REJECTED
    with pytest.raises(InvalidEmbeddingError) as info:
        stored_embeddings(provider, identity=LIVE, chunks=[(CHUNK_0, DIGEST_A)])
    assert str(info.value) == "invalid_embedding"


@pytest.mark.parametrize(
    ("provider", "stored"),
    [
        (1.0, 1.0),
        (0.9999995, 0.9999995231628418),
        (1.000001, ABOVE_ACCEPTED),
        (0.99999904, BELOW_ACCEPTED),
    ],
)
def test_successful_rounding_cases(provider: float, stored: float) -> None:
    rows = stored_embeddings(
        provider_batch(axis(provider), identity=LIVE),
        identity=LIVE,
        chunks=[(CHUNK_0, DIGEST_A)],
    )
    assert rows[0].vector.coordinates[0] == stored


def test_all_coordinates_one_thirty_second_round_exactly() -> None:
    rows = stored_embeddings(
        provider_batch(tuple([1 / 32] * STORED_DIMS), identity=LIVE),
        identity=LIVE,
        chunks=[(CHUNK_0, DIGEST_A)],
    )
    assert rows[0].vector.sha256 == QUARTER_SHA256


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        (BELOW_REJECTED, False),
        (BELOW_ACCEPTED, True),
        (ABOVE_ACCEPTED, True),
        (ABOVE_REJECTED, False),
    ],
)
def test_adjacent_float32_values_at_both_tolerance_edges(value: float, accepted: bool) -> None:
    if accepted:
        assert StoredVector(axis(value), allows_zero=False).coordinates[0] == value
    else:
        with pytest.raises(InvalidEmbeddingError):
            StoredVector(axis(value), allows_zero=False)


def test_vectors_are_never_renormalized() -> None:
    stored = canonical_vector(axis(0.9999995), allows_zero=False)
    assert stored.coordinates[0] != 1.0


def test_float32_overflow_and_non_finite_values_are_rejected() -> None:
    for value in (3.5e38, math.inf, math.nan, 10**400):
        vector = list(axis(0.0))
        vector[0] = value
        with pytest.raises(InvalidEmbeddingError):
            canonical_vector(tuple(vector), allows_zero=True)


def test_a_nonzero_vector_that_rounds_to_zero_is_rejected() -> None:
    tiny = tuple([1e-46] * STORED_DIMS)  # below the smallest float32 subnormal
    with pytest.raises(InvalidEmbeddingError):
        canonical_vector(tiny, allows_zero=True)


def test_zero_vectors_only_where_permitted() -> None:
    assert canonical_vector(axis(0.0), allows_zero=True).is_zero
    with pytest.raises(InvalidEmbeddingError):
        canonical_vector(axis(0.0), allows_zero=False)
    with pytest.raises(InvalidEmbeddingError):
        StoredVector(axis(0.0), allows_zero=False)


@pytest.mark.parametrize(
    "coordinates",
    [
        axis(1.0)[:-1],
        (*axis(1.0), 0.0),
        [*axis(1.0)],
        (True, *axis(0.0)[1:]),
        (1, *axis(0.0)[1:]),  # canonical values are floats
        (0.1, *axis(0.0)[1:]),  # not float32-exact
    ],
)
def test_stored_vectors_require_canonical_float32_tuples(coordinates: object) -> None:
    with pytest.raises(InvalidEmbeddingError):
        StoredVector(coordinates, allows_zero=False)  # type: ignore[arg-type]


# --- whole-batch conversion ---------------------------------------------------------------


def test_offline_hashing_output_converts_and_keeps_order() -> None:
    batch = HashingEmbedder().embed(("Customer data", "!!!"), "document")
    rows = stored_embeddings(
        batch, identity=HASH_IDENTITY, chunks=[(CHUNK_0, DIGEST_A), (CHUNK_1, DIGEST_B)]
    )
    assert [row.chunk_id for row in rows] == [CHUNK_0, CHUNK_1]
    assert not rows[0].vector.is_zero and rows[1].vector.is_zero  # no ASCII features


def test_a_single_failing_vector_rejects_the_whole_batch() -> None:
    batch = provider_batch(axis(1.0), axis(0.999999001), identity=LIVE)
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(batch, identity=LIVE, chunks=[(CHUNK_0, DIGEST_A), (CHUNK_1, DIGEST_B)])


@pytest.mark.parametrize(
    ("identity", "chunks", "mode"),
    [
        (LIVE, [(CHUNK_0, DIGEST_A)], "query"),  # stored embeddings are document vectors
        (HASH_IDENTITY, [(CHUNK_0, DIGEST_A)], "document"),  # identity mismatch
        (LIVE, [(CHUNK_0, DIGEST_A), (CHUNK_1, DIGEST_B)], "document"),  # count mismatch
        (LIVE, [(CHUNK_0, "A" * 64)], "document"),  # bad digest
        (LIVE, [(str(CHUNK_0), DIGEST_A)], "document"),  # bad chunk ID
        (LIVE, (), "document"),
    ],
)
def test_batch_conversion_validates_against_the_request(
    identity: EmbeddingIdentity, chunks: object, mode: str
) -> None:
    batch = EmbeddingBatch(LIVE, mode, (axis(1.0),), EmbeddingUsage(None))  # type: ignore[arg-type]
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(batch, identity=identity, chunks=chunks)  # type: ignore[arg-type]


def test_live_zero_vectors_are_rejected_by_m4a_first() -> None:
    with pytest.raises(InvalidEmbeddingError):
        provider_batch(axis(0.0), identity=LIVE)


def test_only_the_fixed_1024_l2_column_is_storable() -> None:
    small = EmbeddingIdentity("offline", "fake-hash-v1", "ascii-word-sha256-v1", 8, "l2")
    batch = EmbeddingBatch(small, "document", (tuple([0.0] * 8),), EmbeddingUsage(None))
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(batch, identity=small, chunks=[(CHUNK_0, DIGEST_A)])


def test_duplicate_chunks_are_rejected() -> None:
    batch = provider_batch(axis(1.0), axis(1.0, 1), identity=LIVE)
    with pytest.raises(InvalidEmbeddingError):
        stored_embeddings(batch, identity=LIVE, chunks=[(CHUNK_0, DIGEST_A), (CHUNK_0, DIGEST_A)])


# --- write-batch revalidation -------------------------------------------------------------


def _row(chunk: UUID = CHUNK_0, vector: tuple[float, ...] | None = None) -> StoredEmbedding:
    return StoredEmbedding(chunk, DIGEST_A, StoredVector(vector or axis(1.0), allows_zero=True))


def test_revalidation_bounds_and_distinct_chunks() -> None:
    rows = tuple(_row(UUID(int=i + 1)) for i in range(storage.MAX_WRITE_BATCH))
    assert revalidate_rows(rows, allows_zero=False) == rows
    for bad in (
        (),
        (*rows, _row(UUID(int=999))),
        (_row(), _row()),
        ("row",),
    ):
        with pytest.raises(InvalidEmbeddingError):
            revalidate_rows(bad, allows_zero=False)  # type: ignore[arg-type]


def test_revalidation_applies_the_zero_policy() -> None:
    zero = _row(vector=axis(0.0))
    assert revalidate_rows([zero], allows_zero=True)[0].vector.is_zero
    with pytest.raises(InvalidEmbeddingError):
        revalidate_rows([zero], allows_zero=False)


def test_revalidation_rejects_a_forged_vector() -> None:
    row = _row()
    object.__setattr__(row.vector, "coordinates", axis(0.5))
    with pytest.raises(InvalidEmbeddingError):
        revalidate_rows([row], allows_zero=False)
    forged = _row()
    object.__setattr__(forged.vector, "sha256", ZERO_SHA256)
    with pytest.raises(InvalidEmbeddingError):
        revalidate_rows([forged], allows_zero=False)


# --- vector manifest and privacy ---------------------------------------------------------


def test_vector_manifest_is_pinned_and_order_strict() -> None:
    entries = [(0, CHUNK_0, DIGEST_A, E0_SHA256), (1, CHUNK_1, DIGEST_B, ZERO_SHA256)]
    expected = hashlib.sha256(
        f"0:{CHUNK_0}:{DIGEST_A}:{E0_SHA256}\n1:{CHUNK_1}:{DIGEST_B}:{ZERO_SHA256}\n".encode()
    ).hexdigest()
    assert vector_manifest_sha256(entries) == expected == MANIFEST_SHA256
    for bad in (
        list(reversed(entries)),
        [entries[0], entries[0]],
        [(0, CHUNK_0, DIGEST_A, "x")],
        [(True, CHUNK_0, DIGEST_A, E0_SHA256)],
    ):
        with pytest.raises(InvalidEmbeddingError):
            vector_manifest_sha256(bad)


def test_representations_and_errors_never_show_coordinates() -> None:
    vector = list(axis(0.0))
    vector[0], vector[1] = 0.6, 0.8
    stored = canonical_vector(tuple(vector), allows_zero=False)
    row = StoredEmbedding(CHUNK_0, DIGEST_A, stored)
    assert repr(stored) == str(stored) == "StoredVector()"
    assert repr(row) == f"StoredEmbedding(chunk_id={CHUNK_0})"
    assert "0.6" not in repr(row) and DIGEST_A not in repr(row)
    with pytest.raises(InvalidEmbeddingError) as info:
        canonical_vector(axis(0.999999001), allows_zero=False)
    assert str(info.value) == "invalid_embedding"
    assert info.value.__cause__ is None and info.value.__context__ is None
