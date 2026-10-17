"""Corpus manifest, ground truth, quote rules, variants and file-system safety for retrieval
evaluation (``evidenceguard_retrieval.evaluation.corpus`` and the worker's reader; M4e,
ADR-0017). No database: the committed corpus and small hand-written fixtures only."""

import os
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_retrieval.evaluation.corpus import (
    CLEAN,
    FINAL,
    INITIAL,
    INJECTED,
    MAX_QUOTE_CHARS,
    AnchorRef,
    EvaluationError,
    RevisionRef,
    build_suite,
    check_injected_variant,
    effective_paths,
    group_keys,
    parse_anchor_ref,
    parse_corpus,
    parse_ground_truth,
    validate_document_text,
    validate_quote,
)
from evidenceguard_worker.evaluation import load_suite

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"

CORPUS = b"""format = "eg-corpus-v1"

[[tenants]]
slug = "halverson-freight"

  [[tenants.vendors]]
  slug = "lumenvale-cloud"
  name = "Lumenvale Cloud"

    [[tenants.vendors.documents]]
    key = "policy"
    title = "Policy"
    source_type = "vendor_statement"
    media_type = "text/markdown"

      [[tenants.vendors.documents.revisions]]
      n = 1

      [[tenants.vendors.documents.revisions]]
      n = 2

[[tenants]]
slug = "marisol-clinics"

  [[tenants.vendors]]
  slug = "lumenvale-cloud"
  name = "Lumenvale Cloud"

    [[tenants.vendors.documents]]
    key = "policy"
    title = "Policy"
    source_type = "contract"
    media_type = "text/plain"

      [[tenants.vendors.documents.revisions]]
      n = 1
"""

GT_A = b"""format = "eg-ground-truth-v1"
tenant = "halverson-freight"

[[anchors]]
ref = "halverson-freight/lumenvale-cloud/policy@r1#term"
quote = "Old term."

[[anchors]]
ref = "halverson-freight/lumenvale-cloud/policy@r2#term"
quote = "New term."

[[questions]]
vendor = "lumenvale-cloud"
id = "RET-01"
text = "What is the term?"
search_queries = ["term"]

  [[questions.cases]]
  epochs = ["initial"]
  expected_status = "vendor_claim"
  gold = ["halverson-freight/lumenvale-cloud/policy@r1#term"]
  forbidden = [
    "halverson-freight/lumenvale-cloud/policy@r2#term",
    "marisol-clinics/lumenvale-cloud/policy@r1#term",
  ]
  acceptable_claims = []
  wrong_claims = []

  [[questions.cases]]
  epochs = ["final"]
  expected_status = "vendor_claim"
  gold = ["halverson-freight/lumenvale-cloud/policy@r2#term"]
  forbidden = ["halverson-freight/lumenvale-cloud/policy@r1#term"]
  acceptable_claims = [
    { text = "The term is new.", refs = ["halverson-freight/lumenvale-cloud/policy@r2#term"] },
  ]
  wrong_claims = []
"""

GT_B = b"""format = "eg-ground-truth-v1"
tenant = "marisol-clinics"
questions = []

[[anchors]]
ref = "marisol-clinics/lumenvale-cloud/policy@r1#term"
quote = "Foreign term."
"""


def files() -> dict[str, bytes]:
    return {
        "corpus.toml": CORPUS,
        "ground_truth/halverson-freight.toml": GT_A,
        "ground_truth/marisol-clinics.toml": GT_B,
        "documents/halverson-freight/lumenvale-cloud/policy@r1.md": b"# Policy\n\nOld term.\n",
        "documents/halverson-freight/lumenvale-cloud/policy@r2.md": b"# Policy\n\nNew term.\n",
        "documents/marisol-clinics/lumenvale-cloud/policy@r1.md": b"Foreign term.\n",
    }


def code_of(call: Any) -> str:
    with pytest.raises(EvaluationError) as raised:
        call()
    error = raised.value
    assert str(error) == error.code or str(error).startswith(error.code + ":")
    return error.code


# --- the committed corpus ------------------------------------------------------------------------


def _sample_files() -> dict[str, bytes]:
    return {
        p.relative_to(SAMPLE).as_posix(): p.read_bytes() for p in SAMPLE.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("variant", [CLEAN, INJECTED])
def test_the_committed_corpus_validates(variant: str) -> None:
    suite = build_suite(variant, _sample_files())
    assert {t.slug for t in suite.corpus.tenants} == {"halverson-freight", "marisol-clinics"}
    assert len(suite.texts) == 12 and len(suite.anchors) == 17
    assert {q.id for q in suite.questions()} >= {"RET-01", "ENC-01", "BCP-01", "SUB-01", "SOC-01"}
    retention = RevisionRef("halverson-freight", "lumenvale-cloud", "data-retention-policy", 2)
    assert "ninety (90) days" in suite.texts[retention]
    trust = RevisionRef("halverson-freight", "lumenvale-cloud", "trust-center-page", 1)
    assert ("SYSTEM NOTE" in suite.texts[trust]) is (variant == INJECTED)
    assert ("halverson-freight", "lumenvale-cloud", INITIAL) in group_keys(suite)
    assert ("marisol-clinics", "lumenvale-cloud", FINAL) in group_keys(suite)
    for text in suite.texts.values():
        assert "\r" not in text


def test_the_committed_documents_use_lf_only_and_differ_by_one_paragraph() -> None:
    sample = _sample_files()
    for path, data in sample.items():
        if path.endswith(".md"):
            assert b"\r" not in data, path
    check_injected_variant(
        sample["documents/halverson-freight/lumenvale-cloud/trust-center-page@r1.md"].decode(),
        sample[
            "variants/injected/halverson-freight/lumenvale-cloud/trust-center-page@r1.md"
        ].decode(),
    )


def test_the_effective_file_set_selects_the_variant() -> None:
    corpus = parse_corpus(_sample_files()["corpus.toml"])
    clean, injected = effective_paths(corpus, CLEAN), effective_paths(corpus, INJECTED)
    assert set(clean) ^ set(injected) == {
        "documents/halverson-freight/lumenvale-cloud/trust-center-page@r1.md",
        "variants/injected/halverson-freight/lumenvale-cloud/trust-center-page@r1.md",
    }
    assert clean[0] == "corpus.toml"


# --- manifest schema -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'format = "eg-corpus-v1"', b'format = "eg-corpus-v2"'),
        (b'slug = "halverson-freight"', b'slug = "halverson-freight"\nextra = 1'),
        (b'name = "Lumenvale Cloud"', b'name = "Lumenvale Cloud"\nwebsite = "x"'),
        (b'title = "Policy"', b'title = "Policy"\nowner = "x"'),
        (b"      n = 1\n", b"      n = 1\n      note = 1\n"),
        (b"      n = 2\n", b"      n = 3\n"),
        (b"      n = 1\n", b"      n = true\n"),
        (b"      n = 1\n", b'      n = 1\n      effective_date = "2025-01-01"\n'),
        (b"      n = 1\n", b"      n = 1\n      effective_date = 2025-01-01T00:00:00\n"),
        (b"      n = 1\n", b"      n = 1\n      version_label = 1\n"),
        (b'source_type = "contract"', b'source_type = "rumour"'),
        (b'media_type = "text/plain"', b'media_type = "application/pdf"'),
        (b'slug = "halverson-freight"', b'slug = "Halverson"'),
        (b'key = "policy"', b'key = "Policy Doc"'),
    ],
)
def test_manifest_schema_rejections(old: bytes, new: bytes) -> None:
    data = CORPUS.replace(old, new, 1)
    assert data != CORPUS
    assert code_of(lambda: parse_corpus(data)) == "corpus_invalid"


def test_manifest_bounds_and_effective_dates() -> None:
    assert code_of(lambda: parse_corpus(CORPUS + b"#" * (64 * 1024))) == "corpus_invalid"
    assert code_of(lambda: parse_corpus(b"format = ")) == "corpus_invalid"
    assert code_of(lambda: parse_corpus(b"\xff")) == "corpus_invalid"
    dated = CORPUS.replace(b"      n = 1\n", b"      n = 1\n      effective_date = 2025-01-15\n", 1)
    corpus = parse_corpus(dated)
    assert (
        str(corpus.tenants[0].vendors[0].documents[0].revisions[0].effective_date) == "2025-01-15"
    )
    many = b'format = "eg-corpus-v1"\n' + b"".join(
        b'[[tenants]]\nslug = "t%d"\nvendors = []\n' % n for n in range(3)
    )
    assert code_of(lambda: parse_corpus(many)) == "corpus_invalid"


# --- references and ground truth ----------------------------------------------------------------


def test_canonical_references_parse_and_round_trip() -> None:
    ref = parse_anchor_ref("halverson-freight/lumenvale-cloud/policy@r12#term-a")
    assert str(ref) == "halverson-freight/lumenvale-cloud/policy@r12#term-a"
    assert ref.revision.n == 12
    for bad in (
        "term",  # bare names are never accepted
        "lumenvale-cloud/policy@r1#term",
        "halverson-freight/lumenvale-cloud/policy@r01#term",
        "halverson-freight/lumenvale-cloud/policy@r0#term",
        "halverson-freight/lumenvale-cloud/policy#term",
        "Halverson/lumenvale-cloud/policy@r1#term",
        "halverson-freight/lumenvale-cloud/policy@r1#" + "a" * 65,
        "halverson-freight/../policy@r1#term",
    ):
        assert code_of(lambda bad=bad: parse_anchor_ref(bad)) == "invalid_reference"


def test_suite_with_qualified_cross_tenant_forbidden_reference() -> None:
    suite = build_suite(CLEAN, files())
    question = suite.questions()[0]
    initial = question.case_for(INITIAL)
    assert initial is not None and question.case_for(FINAL) is not initial
    foreign = AnchorRef(RevisionRef("marisol-clinics", "lumenvale-cloud", "policy", 1), "term")
    assert foreign in initial.forbidden
    # The same local anchor name in both tenants is distinguished by the full reference.
    assert sum(ref.anchor == "term" for ref in suite.anchors) == 3


@pytest.mark.parametrize(
    ("old", "new", "code"),
    [
        (b'tenant = "halverson-freight"', b'tenant = "marisol-clinics"', "ground_truth_invalid"),
        (
            b'ref = "halverson-freight/lumenvale-cloud/policy@r1#term"',
            b'ref = "marisol-clinics/lumenvale-cloud/policy@r1#other"',
            "foreign_anchor_definition",
        ),
        (
            b'gold = ["halverson-freight/lumenvale-cloud/policy@r2#term"]',
            b'gold = ["marisol-clinics/lumenvale-cloud/policy@r1#term"]',
            "foreign_gold_reference",
        ),
        (
            b'gold = ["halverson-freight/lumenvale-cloud/policy@r1#term"]',
            b'gold = ["halverson-freight/lumenvale-cloud/policy@r1#missing"]',
            "unknown_reference",
        ),
        (
            b'gold = ["halverson-freight/lumenvale-cloud/policy@r1#term"]',
            b'gold = ["halverson-freight/lumenvale-cloud/policy@r2#term"]',
            "gold_forbidden_conflict",
        ),
        (
            b'forbidden = ["halverson-freight/lumenvale-cloud/policy@r1#term"]',
            b'forbidden = ["halverson-freight/lumenvale-cloud/policy@r2#term"]',
            "gold_forbidden_conflict",
        ),
        (b'epochs = ["final"]', b'epochs = ["initial"]', "ground_truth_invalid"),
        (b'epochs = ["final"]', b'epochs = ["later"]', "ground_truth_invalid"),
        (b'epochs = ["final"]', b"epochs = []", "ground_truth_invalid"),
        (b'id = "RET-01"', b'id = "ret-01"', "ground_truth_invalid"),
        (
            b'expected_status = "vendor_claim"',
            b'expected_status = "supported"',
            "ground_truth_invalid",
        ),
        (
            b'search_queries = ["term"]',
            b'search_queries = ["term", "term"]',
            "ground_truth_invalid",
        ),
        (b'search_queries = ["term"]', b"search_queries = []", "ground_truth_invalid"),
        (
            b'text = "What is the term?"',
            b'text = "What is the term?"\nnotes = "x"',
            "ground_truth_invalid",
        ),
        (b"wrong_claims = []\n\n", b"wrong_claims = []\n  extra = 1\n\n", "ground_truth_invalid"),
        (
            b'refs = ["halverson-freight/lumenvale-cloud/policy@r2#term"]',
            b'refs = ["marisol-clinics/lumenvale-cloud/policy@r1#term"]',
            "foreign_gold_reference",
        ),
        (
            b'quote = "Old term."',
            b'quote = "Old term."\noccurrence = 1\ncolour = "red"',
            "anchor_invalid",
        ),
    ],
)
def test_ground_truth_rejections(old: bytes, new: bytes, code: str) -> None:
    data = GT_A.replace(old, new, 1)
    assert data != GT_A
    built = files() | {"ground_truth/halverson-freight.toml": data}
    assert code_of(lambda: build_suite(CLEAN, built)) == code


def test_gold_must_name_the_revision_eligible_in_each_epoch() -> None:
    data = GT_A.replace(
        b'gold = ["halverson-freight/lumenvale-cloud/policy@r2#term"]\n'
        b'  forbidden = ["halverson-freight/lumenvale-cloud/policy@r1#term"]',
        b'gold = ["halverson-freight/lumenvale-cloud/policy@r1#term"]\n  forbidden = []',
    )
    assert data != GT_A
    built = files() | {"ground_truth/halverson-freight.toml": data}
    assert code_of(lambda: build_suite(CLEAN, built)) == "gold_not_eligible_in_epoch"


def test_duplicate_full_anchor_references_are_rejected() -> None:
    data = GT_A.replace(
        b'[[anchors]]\nref = "halverson-freight/lumenvale-cloud/policy@r2#term"',
        b'[[anchors]]\nref = "halverson-freight/lumenvale-cloud/policy@r1#term"',
    )
    assert code_of(lambda: parse_ground_truth(data, "halverson-freight")) == "duplicate_anchor"


# --- quote and occurrence rules ----------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "",
        " leading",
        "trailing ",
        "\ttab",
        "line\n",
        "nul\x00inside",
        "bell\x07inside",
        "carriage\rreturn",
        "lone \ud800 surrogate",
        "x" * (MAX_QUOTE_CHARS + 1),
        42,
        None,
        b"bytes",
    ],
)
def test_invalid_quotes_are_rejected(quote: object) -> None:
    assert code_of(lambda: validate_quote(quote)) == "anchor_invalid"


@pytest.mark.parametrize(
    "quote",
    ["x" * MAX_QUOTE_CHARS, "multi\nline\nquote", "a\tb", "| a | b |\n| c | d |", "é ü \U0001d538"],
)
def test_valid_quotes_are_accepted_verbatim(quote: str) -> None:
    assert validate_quote(quote) is quote


@pytest.mark.parametrize("occurrence", ["0", "-1", "true", "1.5", '"1"'])
def test_invalid_occurrences_are_rejected(occurrence: str) -> None:
    data = GT_A.replace(
        b'quote = "Old term."', b'quote = "Old term."\noccurrence = ' + occurrence.encode()
    )
    assert code_of(lambda: parse_ground_truth(data, "halverson-freight")) == "anchor_invalid"


@pytest.mark.parametrize(
    "parts",
    [
        b'[{ quote = "Old" }]',  # fewer than two
        b'[{ quote = "Old" }, { quote = "term.", colour = 1 }]',
        b'[{ quote = "Old" }, { quote = "" }]',
        b'[{ quote = "Old" }, { quote = "term.", occurrence = 0 }]',
        b'["Old", "term."]',
        b"[" + b", ".join([b'{ quote = "a" }'] * 9) + b"]",
    ],
)
def test_invalid_parts_are_rejected(parts: bytes) -> None:
    data = GT_A.replace(b'quote = "Old term."', b'quote = "Old term."\nparts = ' + parts)
    assert code_of(lambda: parse_ground_truth(data, "halverson-freight")) == "anchor_invalid"


# --- documents and variants -------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [b"", b"   \n", b"a\r\nb", b"a\x00b", b"\xff\xfe", b"x" * (256 * 1024 + 1)],
    ids=["empty", "blank", "crlf", "nul", "not-utf8", "oversized"],
)
def test_invalid_documents_are_rejected(data: bytes) -> None:
    assert code_of(lambda: validate_document_text(data)) == "corpus_document_invalid"


def test_the_injected_variant_must_insert_exactly_one_paragraph() -> None:
    clean = "# T\n\nA.\n\nB.\n"
    check_injected_variant(clean, "# T\n\nA.\n\nInjected line.\n\nB.\n")
    check_injected_variant(clean, "Injected.\n\n# T\n\nA.\n\nB.\n")
    for injected in (
        clean,
        "# T\n\nA changed.\n\nB.\n",
        "# T\n\nA.\n\nOne.\n\nTwo.\n\nB.\n",
        "# T\n\nA.\n\n   \n\nB.\n",
        "# T\n\nA.\nextra line\n\nB.\n",
    ):
        assert code_of(lambda injected=injected: check_injected_variant(clean, injected)) == (
            "corpus_variant_invalid"
        )


def test_suite_file_set_checks() -> None:
    extra = files() | {"documents/halverson-freight/lumenvale-cloud/stray@r1.md": b"x\n"}
    assert code_of(lambda: build_suite(CLEAN, extra)) == "corpus_unexpected_file"
    missing = files()
    del missing["documents/halverson-freight/lumenvale-cloud/policy@r2.md"]
    assert code_of(lambda: build_suite(CLEAN, missing)) == "corpus_file_missing"
    assert code_of(lambda: build_suite(INJECTED, files())) == "corpus_variant_invalid"
    big = files() | {
        "documents/halverson-freight/lumenvale-cloud/policy@r1.md": b"# P\n\nOld term.\n"
        + b"y" * (250 * 1024)
    }
    many = big | {
        "documents/halverson-freight/lumenvale-cloud/policy@r2.md": b"# P\n\nNew term.\n"
        + b"y" * (250 * 1024)
    }
    assert build_suite(CLEAN, many).variant == CLEAN  # under the 4 MiB file-set bound


# --- file-system safety (worker reader) -----------------------------------------------------------


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    for path, data in _sample_files().items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def test_the_reader_loads_a_copied_corpus(tmp_path: Path) -> None:
    assert load_suite(_copy(tmp_path), CLEAN).variant == CLEAN


def test_the_reader_rejects_unexpected_oversized_and_non_regular_files(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / "documents" / "notes.txt").write_bytes(b"stray")
    assert code_of(lambda: load_suite(root, CLEAN)) == "corpus_unexpected_file"
    (root / "documents" / "notes.txt").unlink()

    target = root / "documents/halverson-freight/lumenvale-cloud/subprocessors@r1.md"
    original = target.read_bytes()
    target.write_bytes(b"x" * (256 * 1024 + 1))
    assert code_of(lambda: load_suite(root, CLEAN)) == "corpus_too_large"
    target.unlink()
    assert code_of(lambda: load_suite(root, CLEAN)) == "corpus_file_missing"
    target.mkdir()
    assert code_of(lambda: load_suite(root, CLEAN)) == "corpus_path_invalid"
    target.rmdir()
    target.write_bytes(original)
    assert load_suite(root, CLEAN).variant == CLEAN


def test_the_reader_rejects_symlinks(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    target = root / "documents/halverson-freight/lumenvale-cloud/subprocessors@r1.md"
    outside = tmp_path / "outside.md"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        os.symlink(outside, target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available to this user on this platform")
    assert code_of(lambda: load_suite(root, CLEAN)) == "corpus_path_invalid"


def test_errors_never_contain_document_or_quote_text() -> None:
    marker = "PRIVATE-MARKER-4d1e"
    data = GT_A.replace(b'quote = "Old term."', f'quote = " {marker}"'.encode())
    with pytest.raises(EvaluationError) as raised:
        parse_ground_truth(data, "halverson-freight")
    assert marker not in str(raised.value) and marker not in repr(raised.value)
    assert raised.value.__cause__ is None and raised.value.__context__ is None
