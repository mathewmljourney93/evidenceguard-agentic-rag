"""M4a contracts; golden coordinates calculated independently from SHA-256 bytes."""

import dataclasses
import json
import math
import os
import subprocess
import sys
from typing import Any

import pytest

from evidenceguard_domain.embeddings import (
    LEXICAL_HASH_LABEL,
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingUsage,
    InputType,
    InvalidEmbeddingError,
    validate_request,
    validate_result,
)
from evidenceguard_retrieval.embeddings import (
    HASH_IDENTITY,
    EmbeddingProvider,
    HashingEmbedder,
    embed_validated,
)


def sparse(**coordinates: float) -> tuple[float, ...]:
    return tuple(coordinates.get(str(i), 0.0) for i in range(1024))


def batch() -> EmbeddingBatch:
    return HashingEmbedder().embed(("hello",), "query")


def test_literal_fingerprint_and_feature_buckets() -> None:
    # Independently hashed canonical JSON and literal feature bytes, not this provider.
    assert HASH_IDENTITY.fingerprint == (
        "ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376"
    )
    # u:hello -> bucket 250, digest byte 8 = 0x8a (positive).
    # u:world -> bucket 909, byte 8 = 0x21 (negative).
    # b:hello world -> bucket 204, byte 8 = 0x76 (positive).
    scale = 1 / math.sqrt(3)
    provider = HashingEmbedder()
    assert provider.embed(("hello",), "query").vectors == (sparse(**{"250": 1.0}),)
    vector = provider.embed(("hello world",), "document").vectors[0]
    assert vector == pytest.approx(sparse(**{"250": scale, "909": -scale, "204": scale}), abs=1e-6)


def test_repeated_features_and_opposite_sign_collision_cancel() -> None:
    # u:a -> 879,+1; b:a a -> 127,-1. Repeated unigrams count twice.
    vector = HashingEmbedder().embed(("a a",), "query").vectors[0]
    assert vector == pytest.approx(sparse(**{"879": 2 / math.sqrt(5), "127": -1 / math.sqrt(5)}))
    # Independently found u:t19 and u:t36 collide at 455 with signs +1/-1.
    # Their bigram is 172,+1; the colliding unigram coordinate cancels to zero.
    assert HashingEmbedder().embed(("t19 t36",), "query").vectors == (sparse(**{"172": 1.0}),)


@pytest.mark.parametrize("text", ["HELLO, world!", "hello\tworld", "hello\nworld", "héllo world"])
def test_ascii_tokenization_and_delimiters(text: str) -> None:
    provider = HashingEmbedder()
    expected = "h llo world" if "é" in text else "hello world"
    assert provider.embed((text,), "query").vectors == provider.embed((expected,), "query").vectors


def test_unicode_not_normalized_and_non_ascii_zero_label() -> None:
    p = HashingEmbedder()
    assert p.embed(("é", "中文", "😀", "!!!"), "query").vectors == ((0.0,) * 1024,) * 4
    assert p.embed(("é",), "query").vectors != p.embed(("e\u0301",), "query").vectors
    assert p.label == batch().label == LEXICAL_HASH_LABEL
    assert LEXICAL_HASH_LABEL in repr(p) and LEXICAL_HASH_LABEL in repr(batch())


def test_order_duplicates_modes_and_batch_individual_equivalence() -> None:
    p: EmbeddingProvider = HashingEmbedder()
    texts = ("world", "hello", "world")
    q = embed_validated(p, texts, "query")
    d = embed_validated(p, texts, "document")
    assert q.vectors == d.vectors
    assert q.input_type == "query" and d.input_type == "document"
    assert q.vectors == tuple(p.embed((text,), "query").vectors[0] for text in texts)
    assert q.vectors[0] == q.vectors[2] != q.vectors[1]
    assert q.usage.input_tokens is None


def test_cross_process_hash_seed_independence() -> None:
    code = (
        "import json; from evidenceguard_retrieval.embeddings import HashingEmbedder; "
        "print(json.dumps(HashingEmbedder().embed(('hello world','t19 t36'),'query').vectors))"
    )
    outputs = []
    for seed in ("1", "987654"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outputs.append(json.loads(subprocess.check_output([sys.executable, "-c", code], env=env)))
    assert outputs[0] == outputs[1]
    assert outputs[0][0][250] == pytest.approx(1 / math.sqrt(3), abs=1e-6)
    assert outputs[0][1][172] == 1


@pytest.mark.parametrize(
    ("texts", "mode"),
    [
        ((), "query"),
        (("a",) * 33, "query"),
        (["a"], "query"),
        ("a", "query"),
        (("",), "query"),
        ((" " * 4,), "query"),
        (("\u2003",), "query"),
        (("a" * 4001,), "query"),
        (("a\x00",), "query"),
        (("\ud800",), "query"),
        (("\udfff",), "query"),
        ((True,), "query"),
        ((42,), "query"),
        ((b"a",), "query"),
        (("😀" * 4000,) * 8 + ("a",), "query"),
        (("a",), "QUERY"),
        (("a",), True),
        (("a",), None),
    ],
)
def test_request_rejections(texts: Any, mode: Any) -> None:
    with pytest.raises(InvalidEmbeddingError, match=r"^invalid_embedding$"):
        validate_request(texts, mode)
    with pytest.raises(InvalidEmbeddingError, match=r"^invalid_embedding$"):
        HashingEmbedder().embed(texts, mode)


@pytest.mark.parametrize(
    "texts", [("a",), ("a",) * 32, ("a" * 4000,), ("😀" * 4000,), ("😀" * 4000,) * 8]
)
def test_request_boundaries_and_exact_preservation(texts: tuple[str, ...]) -> None:
    original = texts
    validate_request(texts, "document")
    assert texts is original
    assert len(HashingEmbedder().embed(texts, "document").vectors) == len(texts)


class RecordingProvider:
    identity = HASH_IDENTITY

    def __init__(self) -> None:
        self.seen: tuple[str, ...] = ()

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        self.seen = texts
        return HashingEmbedder().embed(texts, input_type)


def test_boundary_passes_exact_text_and_rejects_before_provider_call() -> None:
    p = RecordingProvider()
    texts = ("  A\r\n😀\t ",)
    embed_validated(p, texts, "document")
    assert p.seen is texts and p.seen[0] == "  A\r\n😀\t "
    with pytest.raises(InvalidEmbeddingError):
        embed_validated(p, ("",), "query")
    assert p.seen is texts


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_id", "A"),
        ("provider_id", " a"),
        ("provider_id", "a" * 65),
        ("provider_id", "é"),
        ("provider_id", ""),
        ("provider_id", True),
        ("model_id", 1),
        ("algorithm_version", "a/b"),
        ("dims", True),
        ("dims", "1024"),
        ("dims", 1.0),
        ("dims", 0),
        ("dims", 4097),
        ("normalization", "L2"),
        ("normalization", 2),
        ("private-extra", "private-input"),
    ],
)
def test_identity_rejections(field: str, value: Any) -> None:
    data: dict[str, Any] = dataclasses.asdict(HASH_IDENTITY)
    data[field] = value
    with pytest.raises(InvalidEmbeddingError, match=r"^invalid_embedding$"):
        EmbeddingIdentity(**data)


def test_identity_boundaries_fingerprint_changes_and_immutability() -> None:
    for dims in (1, 4096):
        identity = EmbeddingIdentity("a" * 64, "a._-0", "v1", dims, "l2")
        assert identity.dims == dims and len(identity.fingerprint) == 64
    for field, value in [
        ("provider_id", "other"),
        ("model_id", "other"),
        ("algorithm_version", "v2"),
        ("dims", 1),
    ]:
        update: dict[str, Any] = {field: value}
        assert dataclasses.replace(HASH_IDENTITY, **update).fingerprint != HASH_IDENTITY.fingerprint
    for instance, field in [
        (HASH_IDENTITY, "dims"),
        (batch(), "vectors"),
        (EmbeddingUsage(None), "input_tokens"),
        (HashingEmbedder(), "identity"),
    ]:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field, 2)
    with pytest.raises(InvalidEmbeddingError):
        dataclasses.replace(HASH_IDENTITY, dims=True)
    assert dataclasses.replace(batch()) == batch()
    with pytest.raises(InvalidEmbeddingError):
        dataclasses.replace(batch(), vectors=((2.0,) * 1024,))


@pytest.mark.parametrize("value", [True, -1, 1.0, "1", [], {}])
def test_usage_strictness(value: Any) -> None:
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingUsage(value)


def test_usage_unknown_and_supported_replacement() -> None:
    assert EmbeddingUsage(0).input_tokens == 0
    assert EmbeddingUsage(10**100).input_tokens == 10**100
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingUsage(None, secret="private-input")
    with pytest.raises(InvalidEmbeddingError):
        dataclasses.replace(EmbeddingUsage(None), input_tokens=True)


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        (),
        ([1.0] * 1024,),
        ((True,) * 1024,),
        (("1",) * 1024,),
        ((1.0,),),
        (sparse(**{"0": 2.0}),),
        (sparse(**{"0": float("nan")}),),
        (sparse(**{"0": float("inf")}),),
        (sparse(**{"0": -float("inf")}),),
        (sparse(**{"0": 1e308}),),
        (sparse(**{"0": 5e-324}),),
        ((0.0,) * 1024,) * 33,
    ],
)
def test_batch_rejections(vectors: Any) -> None:
    with pytest.raises(InvalidEmbeddingError, match=r"^invalid_embedding$"):
        EmbeddingBatch(HASH_IDENTITY, "query", vectors, EmbeddingUsage(None))


def test_extreme_integer_has_only_fixed_error_without_exception_context() -> None:
    huge = 10**10000
    with pytest.raises(InvalidEmbeddingError) as exc:
        EmbeddingBatch(HASH_IDENTITY, "query", ((huge,) + (0,) * 1023,), EmbeddingUsage(None))
    assert str(exc.value) == "invalid_embedding"
    assert exc.value.__context__ is None


def test_norm_tolerance_and_live_zero_policy() -> None:
    EmbeddingBatch(HASH_IDENTITY, "query", (sparse(**{"0": 1 + 0.5e-6}),), EmbeddingUsage(None))
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingBatch(HASH_IDENTITY, "query", (sparse(**{"0": 1 + 2e-6}),), EmbeddingUsage(None))
    live = dataclasses.replace(HASH_IDENTITY, provider_id="live")
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingBatch(live, "query", ((0.0,) * 1024,), EmbeddingUsage(1))
    assert (
        EmbeddingBatch(live, "query", (sparse(**{"0": 1}),), EmbeddingUsage(1)).label
        == "provider embeddings"
    )


class MalformedProvider:
    identity = HASH_IDENTITY

    def __init__(self, result: Any) -> None:
        self.result = result

    def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
        return self.result  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_type", "document"),
        ("input_type", True),
        ("vectors", ()),
        ("vectors", (sparse(**{"0": 1}),) * 2),
        ("vectors", [[1.0] * 1024]),
        ("vectors", ((float("nan"),) * 1024,)),
        ("vectors", ((True,) * 1024,)),
        ("vectors", ((2.0,) * 1024,)),
        ("usage", {"input_tokens": 1}),
        ("identity", dataclasses.replace(HASH_IDENTITY, model_id="wrong")),
        ("identity", dataclasses.replace(HASH_IDENTITY, dims=1)),
    ],
)
def test_untrusted_forged_batch_revalidated(field: str, value: Any) -> None:
    forged = batch()
    object.__setattr__(forged, field, value)
    with pytest.raises(InvalidEmbeddingError):
        embed_validated(MalformedProvider(forged), ("hello",), "query")


def test_forged_nested_values_live_zero_and_unknown_batch_fields() -> None:
    for nested, field, value in [
        (EmbeddingUsage(None), "input_tokens", True),
        (dataclasses.replace(HASH_IDENTITY), "dims", True),
    ]:
        forged = batch()
        object.__setattr__(nested, field, value)
        object.__setattr__(
            forged, "usage" if isinstance(nested, EmbeddingUsage) else "identity", nested
        )
        with pytest.raises(InvalidEmbeddingError):
            embed_validated(MalformedProvider(forged), ("hello",), "query")
    live = dataclasses.replace(HASH_IDENTITY, provider_id="live")
    forged = batch()
    object.__setattr__(forged, "identity", live)
    object.__setattr__(forged, "vectors", ((0.0,) * 1024,))
    provider = MalformedProvider(forged)
    provider.identity = live
    with pytest.raises(InvalidEmbeddingError):
        embed_validated(provider, ("hello",), "query")
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingBatch(
            HASH_IDENTITY, "query", batch().vectors, EmbeddingUsage(None), secret="private-input"
        )


def test_raw_provider_errors_and_representations_are_private() -> None:
    class FailingProvider:
        identity = HASH_IDENTITY

        def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
            raise RuntimeError("private-input raw-provider-response [12345.6789]")

    with pytest.raises(InvalidEmbeddingError) as exc:
        embed_validated(FailingProvider(), ("private-input",), "query")
    assert str(exc.value) == "invalid_embedding" and exc.value.__context__ is None
    for value in (HASH_IDENTITY, EmbeddingUsage(123456789), batch(), exc.value):
        assert "private-input" not in repr(value)
        assert "123456789" not in repr(value)
        assert "vectors=" not in repr(value)
    with pytest.raises(InvalidEmbeddingError):
        embed_validated(MalformedProvider({"vectors": "private-input"}), ("hello",), "query")


def test_result_expected_metadata_is_strict() -> None:
    for mode, count in [(True, 1), ("query", True), ("query", 0), ("query", 33)]:
        args: Any = {"identity": HASH_IDENTITY, "input_type": mode, "count": count}
        with pytest.raises(InvalidEmbeddingError):
            validate_result(batch(), **args)


@pytest.mark.parametrize("field", ["provider_id", "model_id", "algorithm_version"])
@pytest.mark.parametrize("value", ["", "A", "a" * 65, "a\n", "é", False, [], 1])
def test_all_identity_identifiers_are_strict(field: str, value: Any) -> None:
    data: dict[str, Any] = dataclasses.asdict(HASH_IDENTITY)
    data[field] = value
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingIdentity(**data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity", {}),
        ("input_type", True),
        ("input_type", " document "),
        ("usage", {"input_tokens": 0}),
    ],
)
def test_batch_constructor_metadata_rejections(field: str, value: Any) -> None:
    data: dict[str, Any] = {
        "identity": HASH_IDENTITY,
        "input_type": "query",
        "vectors": batch().vectors,
        "usage": EmbeddingUsage(None),
    }
    data[field] = value
    with pytest.raises(InvalidEmbeddingError):
        EmbeddingBatch(**data)


def test_provider_cannot_change_expected_identity_during_call() -> None:
    class ChangingProvider:
        identity = HASH_IDENTITY

        def embed(self, texts: tuple[str, ...], input_type: InputType) -> EmbeddingBatch:
            self.identity = dataclasses.replace(HASH_IDENTITY, model_id="changed")
            return dataclasses.replace(batch(), identity=self.identity)

    with pytest.raises(InvalidEmbeddingError):
        embed_validated(ChangingProvider(), ("hello",), "query")


def test_offline_call_does_not_access_environment_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected I/O")

    import socket

    class NoEnvironment:
        get = staticmethod(refused)
        __getitem__ = staticmethod(refused)

    # Restore before pytest's own reporting/teardown reads the environment.
    with monkeypatch.context() as isolated:
        isolated.setattr(os, "getenv", refused)
        isolated.setattr(os, "environ", NoEnvironment())
        isolated.setattr(socket, "socket", refused)
        result = embed_validated(HashingEmbedder(), ("hello world",), "query")
    assert result.identity == HASH_IDENTITY
