"""The chunk contract (``evidenceguard_domain.chunks``, M3d, ADR-0010): pure tests.

Deterministic IDs, the canonical manifest's exact bytes, the ``Chunk`` invariants, the expected
set of the current attempt, and batch bounds.
"""

import hashlib
import json
from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from evidenceguard_domain.chunks import (
    CHUNK_ID_NAMESPACE,
    MANIFEST_KEYS,
    MAX_BATCH_CHARS,
    MAX_BATCH_CHUNKS,
    Chunk,
    ExpectedChunkSet,
    InvalidChunkError,
    batches,
    chunk_id,
    chunks_manifest_sha256,
    manifest_bytes,
    manifest_sha256,
    within_batch_bounds,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
REVISION = UUID("22222222-2222-4222-8222-222222222222")
VERSION = "text-md-v1"
CONTENT_MARKER = "synthetic-private-content-marker"


def _chunk(ordinal: int = 0, text: str = "Body text.", **overrides: Any) -> Chunk:
    values: dict[str, Any] = {
        "id": chunk_id(TENANT, REVISION, VERSION, ordinal),
        "tenant_id": TENANT,
        "revision_id": REVISION,
        "chunker_version": VERSION,
        "ordinal": ordinal,
        "text": text,
        "section_path": (),
        "is_table": False,
        "line_start": 1,
        "line_end": 1,
        "char_start": 0,
        "char_end": len(text),
    }
    values.update(overrides)
    return Chunk(**values)


def test_the_namespace_is_the_documented_fixed_literal() -> None:
    derived = uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/namespaces/chunk-id/v1")
    assert CHUNK_ID_NAMESPACE == derived == UUID("973dffe5-e145-5fd2-833e-6793460ee3be")


def test_chunk_ids_follow_the_formula_and_examples() -> None:
    assert chunk_id(TENANT, REVISION, VERSION, 0) == UUID("a11668be-c537-5f4d-b5d8-7a056099b8a0")
    other = UUID("33333333-3333-4333-8333-333333333333")
    assert chunk_id(other, REVISION, VERSION, 0) == UUID("53214eae-4b9a-5805-a6e7-41a8e3b6341c")
    assert chunk_id(TENANT, REVISION, VERSION, 7) == uuid5(
        CHUNK_ID_NAMESPACE, f"{TENANT}:{REVISION}:{VERSION}:7"
    )
    for bad in (-1, True, "0"):
        with pytest.raises(ValueError):
            chunk_id(TENANT, REVISION, VERSION, bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        chunk_id(TENANT, REVISION, "Not Valid", 0)


def test_the_manifest_bytes_are_canonical_and_ascii() -> None:
    first = _chunk(0, "Caf\u00e9 \U0001f600", section_path=("Caf\u00e9", "\U0001f600"))
    second = _chunk(
        1,
        "| h |\n|---|\n| r |",
        is_table=True,
        line_start=5,
        line_end=5,
        char_start=40,
        char_end=45,
        header_line_start=1,
        header_line_end=2,
        header_char_start=0,
        header_char_end=12,
    )

    data = manifest_bytes([first.manifest_entry(), second.manifest_entry()])

    digest_1 = hashlib.sha256(first.text.encode()).hexdigest()
    digest_2 = hashlib.sha256(second.text.encode()).hexdigest()
    expected = (
        '[{"char_end":6,"char_start":0,"content_sha256":"' + digest_1 + '",'
        '"header_char_end":null,"header_char_start":null,"header_line_end":null,'
        '"header_line_start":null,"id":"a11668be-c537-5f4d-b5d8-7a056099b8a0",'
        '"is_table":false,"line_end":1,"line_start":1,"ordinal":0,'
        '"section_path":["Caf\\u00e9","\\ud83d\\ude00"]},'
        '{"char_end":45,"char_start":40,"content_sha256":"' + digest_2 + '",'
        '"header_char_end":12,"header_char_start":0,"header_line_end":2,'
        '"header_line_start":1,"id":"' + str(second.id) + '",'
        '"is_table":true,"line_end":5,"line_start":5,"ordinal":1,"section_path":[]}]'
    )
    assert data == expected.encode("ascii")
    assert chunks_manifest_sha256([first, second]) == hashlib.sha256(data).hexdigest()
    assert json.loads(data)[0]["section_path"] == ["Caf\u00e9", "\U0001f600"]


def test_manifest_entries_must_be_complete_and_in_ordinal_order() -> None:
    entry = _chunk(0).manifest_entry()
    assert tuple(sorted(entry)) == MANIFEST_KEYS
    with pytest.raises(ValueError):
        manifest_bytes([_chunk(1, char_start=0).manifest_entry()])
    with pytest.raises(ValueError):
        manifest_bytes([{key: value for key, value in entry.items() if key != "is_table"}])
    with pytest.raises(ValueError):
        manifest_bytes([{**entry, "text": "extra"}])


def test_the_manifest_is_stable_and_sensitive_to_every_field() -> None:
    base = [_chunk(0), _chunk(1, "Second.", line_start=3, line_end=3, char_start=20, char_end=27)]
    digest = manifest_sha256(chunk.manifest_entry() for chunk in base)
    assert digest == manifest_sha256(chunk.manifest_entry() for chunk in base)
    variants: list[dict[str, Any]] = [
        {"section_path": ("Other",)},
        {"line_start": 2, "line_end": 2},
        {"char_start": 1, "char_end": 11},
        {"text": "Body text!"},
    ]
    for change in variants:
        changed = [replace(base[0], **change), base[1]]
        assert manifest_sha256(chunk.manifest_entry() for chunk in changed) != digest


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": UUID("00000000-0000-4000-8000-000000000000")},
        {"text": ""},
        {"text": "x" * 4001, "char_end": 4001},
        {"char_end": 99},
        {"line_start": 0},
        {"line_end": 0},
        {"section_path": ("a",) * 7},
        {"section_path": ["a"]},
        {"ordinal": 4096, "id": chunk_id(TENANT, REVISION, VERSION, 4096)},
        {"header_char_start": 0},
        {
            "header_line_start": 1,
            "header_line_end": 1,
            "header_char_start": 0,
            "header_char_end": 5,
            "line_start": 2,
            "line_end": 2,
            "char_start": 10,
            "char_end": 15,
        },
        {"chunker_version": "Bad Version"},
    ],
)
def test_chunks_that_break_the_contract_are_refused(overrides: dict[str, Any]) -> None:
    values: dict[str, Any] = {"text": CONTENT_MARKER, "char_end": len(CONTENT_MARKER)}
    values.update(overrides)
    with pytest.raises(InvalidChunkError) as info:
        _chunk(**values)
    assert CONTENT_MARKER not in str(info.value)


def test_a_repeated_header_chunk_must_match_both_spans() -> None:
    chunk = _chunk(
        2,
        "| h |\n|---|\n| r |",
        is_table=True,
        line_start=4,
        line_end=4,
        char_start=30,
        char_end=35,
        header_line_start=1,
        header_line_end=2,
        header_char_start=0,
        header_char_end=12,
    )
    assert chunk.has_repeated_header


def test_a_chunk_never_shows_its_text_or_section_path() -> None:
    chunk = _chunk(text=CONTENT_MARKER, char_end=len(CONTENT_MARKER), section_path=("Secret",))
    assert CONTENT_MARKER not in repr(chunk) and "Secret" not in repr(chunk)
    assert CONTENT_MARKER not in str(chunk)


def test_the_expected_set_of_an_attempt() -> None:
    chunks = [_chunk(0), _chunk(1, "Two.", char_start=12, char_end=16)]
    expected = ExpectedChunkSet.of(chunks)
    assert expected == ExpectedChunkSet(
        chunker_version=VERSION,
        chunk_count=2,
        manifest_sha256=chunks_manifest_sha256(chunks),
    )
    with pytest.raises(ValueError):
        ExpectedChunkSet.of([])
    other_revision = UUID("44444444-4444-4444-8444-444444444444")
    foreign = _chunk(1, revision_id=other_revision, id=chunk_id(TENANT, other_revision, VERSION, 1))
    with pytest.raises(ValueError):
        ExpectedChunkSet.of([chunks[0], foreign])
    for bad in (
        {"chunk_count": 0},
        {"chunk_count": 4097},
        {"manifest_sha256": "A" * 64},
        {"chunker_version": "-x"},
    ):
        values: dict[str, Any] = {
            "chunker_version": VERSION,
            "chunk_count": 1,
            "manifest_sha256": "a" * 64,
        }
        values.update(bad)
        with pytest.raises(ValueError):
            ExpectedChunkSet(**values)


def test_batches_respect_both_bounds_in_order() -> None:
    small = [_chunk(index, "s", char_start=index, char_end=index + 1) for index in range(450)]
    sized = [len(batch) for batch in batches(small)]
    assert sized == [MAX_BATCH_CHUNKS, MAX_BATCH_CHUNKS, 50]

    big_text = "b" * 4000
    big = [
        _chunk(index, big_text, char_start=index * 5000, char_end=index * 5000 + 4000)
        for index in range(300)
    ]
    groups = list(batches(big))
    assert [chunk for group in groups for chunk in group] == big
    assert all(within_batch_bounds(group) for group in groups)
    assert all(sum(len(chunk.text) for chunk in group) <= MAX_BATCH_CHARS for group in groups)
    assert len(groups[0]) == MAX_BATCH_CHARS // 4000
    assert not within_batch_bounds([])
