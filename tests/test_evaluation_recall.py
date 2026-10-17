"""Exact Recall, the corpus digest, contract and isolation checks and the report
(``evidenceguard_retrieval.evaluation.recall``; M4e, ADR-0017). Independent hand-built fixtures;
no database and no retrieval."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from uuid import UUID

import pytest

from evidenceguard_retrieval.evaluation.corpus import FINAL, INITIAL, EvaluationError
from evidenceguard_retrieval.evaluation.recall import (
    CONTRACT_CODES,
    ISOLATION_CODES,
    REPORT_SCHEMA,
    STAMP,
    ChunkOwner,
    EvaluationReport,
    GroupContext,
    GroupReport,
    Profile,
    QuestionRun,
    RankedItem,
    check_question,
    corpus_digest,
    display,
    fraction_json,
    macro,
    recall_at_k,
    report_bytes,
    require_passing,
)


def u(n: int) -> UUID:
    return UUID(int=n)


A, B, C, X, Y, Z = (u(n) for n in range(1, 7))


# --- Recall arithmetic --------------------------------------------------------------------------


def test_the_specified_two_thirds_example() -> None:
    assert recall_at_k([A, X, B, Y, Z], frozenset({A, B, C}), 5) == Fraction(2, 3)
    assert display(Fraction(2, 3)) == "0.6667"


def test_recall_cases() -> None:
    gold = frozenset({A, B})
    assert recall_at_k([A], frozenset({A}), 5) == 1  # two gold anchors sharing one chunk
    assert recall_at_k([X, A], gold, 5) == Fraction(1, 2)  # fewer than k results
    assert recall_at_k([], gold, 5) == 0
    assert recall_at_k([X, Y, Z, u(7), u(8), A], gold, 5) == 0  # beyond k is not counted
    assert recall_at_k([X, Y, Z, u(7), u(8), A], gold, 8) == Fraction(1, 2)
    assert recall_at_k([A, B], frozenset(), 5) is None
    with pytest.raises(EvaluationError, match=r"^duplicate_retrieval_id$"):
        recall_at_k([A, A], gold, 5)
    with pytest.raises(EvaluationError, match=r"^invalid_k$"):
        recall_at_k([A], gold, 0)


def test_macro_excludes_empty_gold_and_all_empty_is_null() -> None:
    assert macro([Fraction(1), Fraction(1, 2), None]) == Fraction(3, 4)
    assert macro([None, None]) is None
    assert macro([]) is None


def test_display_rounds_half_to_even_and_json_keeps_the_exact_fraction() -> None:
    assert display(Fraction(1, 20000)) == "0.0000"  # 0.5 ten-thousandths -> even
    assert display(Fraction(3, 20000)) == "0.0002"
    assert display(Fraction(1)) == "1.0000"
    assert display(Fraction(1, 3)) == "0.3333"
    assert fraction_json(Fraction(2, 4)) == {"numerator": 1, "denominator": 2, "display": "0.5000"}
    assert fraction_json(None) is None
    with pytest.raises(EvaluationError):
        display(Fraction(-1, 2))


# --- digest ------------------------------------------------------------------------------------


def test_the_digest_framing_is_exact() -> None:
    files = [("documents/b.md", b"B"), ("corpus.toml", b"C")]
    expected = hashlib.sha256()
    expected.update(b"eg-corpus-digest-v1\n")
    for chunk in (b"clean", b"corpus.toml", b"C", b"documents/b.md", b"B"):
        expected.update(len(chunk).to_bytes(8, "big") + chunk)
    assert corpus_digest("clean", files) == expected.hexdigest()
    assert corpus_digest("clean", list(reversed(files))) == expected.hexdigest()


def test_the_digest_distinguishes_boundaries_variants_and_content() -> None:
    base = corpus_digest("clean", [("a", b"bc")])
    assert corpus_digest("clean", [("ab", b"c")]) != base
    assert corpus_digest("injected", [("a", b"bc")]) != base
    assert corpus_digest("clean", [("a", b"bd")]) != base
    assert corpus_digest("clean", [("a", b"bc"), ("b", b"")]) != base


def test_the_digest_sorts_by_utf8_bytes() -> None:
    files = [("é.md", b"1"), ("z.md", b"2")]  # "z" < "é" by UTF-8 bytes and code points
    expected = hashlib.sha256(b"eg-corpus-digest-v1\n")
    for chunk in (b"clean", b"z.md", b"2", "é.md".encode(), b"1"):
        expected.update(len(chunk).to_bytes(8, "big") + chunk)
    assert corpus_digest("clean", files) == expected.hexdigest()


@pytest.mark.parametrize(
    "files",
    [[("a", b"1"), ("a", b"2")], [("../a", b"1")], [("/a", b"1")], [("a\\b", b"1")]],
)
def test_the_digest_rejects_invalid_paths(files: list[tuple[str, bytes]]) -> None:
    with pytest.raises(EvaluationError, match=r"^corpus_digest_invalid$"):
        corpus_digest("clean", files)


# --- contract and isolation checks ------------------------------------------------------------

OWNERS = {
    A: ChunkOwner("halverson-freight", "lumenvale-cloud", "halverson-freight/lumenvale-cloud/p@r1"),
    B: ChunkOwner("halverson-freight", "lumenvale-cloud", "halverson-freight/lumenvale-cloud/p@r1"),
    C: ChunkOwner("halverson-freight", "lumenvale-cloud", "halverson-freight/lumenvale-cloud/p@r2"),
    X: ChunkOwner(
        "halverson-freight", "ferrowick-payroll", "halverson-freight/ferrowick-payroll/s@r1"
    ),
    Y: ChunkOwner("marisol-clinics", "lumenvale-cloud", "marisol-clinics/lumenvale-cloud/p@r1"),
}
CONTEXT = GroupContext(
    "halverson-freight",
    "lumenvale-cloud",
    INITIAL,
    "s" * 64,
    "f" * 64,
    "c" * 64,
    frozenset({A, B}),
    OWNERS,
)


def run(
    ids: list[UUID],
    *,
    gold: frozenset[UUID] = frozenset({A, B}),
    forbidden: frozenset[UUID] = frozenset(),
    texts: dict[UUID, str] | None = None,
    ranks: list[int] | None = None,
    snapshot: str = "s" * 64,
    profile: str = "f" * 64,
    config: str = "c" * 64,
) -> QuestionRun:
    fused = ranks or list(range(1, len(ids) + 1))
    items = tuple(RankedItem(n, chunk, fused[n - 1]) for n, chunk in enumerate(ids, start=1))
    return QuestionRun(
        "RET-01", items, snapshot, profile, config, texts or {}, gold, forbidden, ("CANARY-1",)
    )


def codes(
    result: tuple[object, tuple[object, ...], tuple[object, ...]],
) -> tuple[set[str], set[str]]:
    _, contract, isolation = result
    return {f.code for f in contract}, {f.code for f in isolation}  # type: ignore[attr-defined]


def test_a_valid_question_reports_exact_recall() -> None:
    report, contract, isolation = check_question(CONTEXT, run([B]))
    assert (report.outcome, report.failure_codes, contract, isolation) == ("ok", (), (), ())
    assert report.recall_at_5 == report.recall_at_8 == Fraction(1, 2)
    assert report.ranked[0].ref == "halverson-freight/lumenvale-cloud/p@r1"
    empty, _, _ = check_question(CONTEXT, run([A], gold=frozenset()))
    assert (empty.outcome, empty.recall_at_5) == ("ok_empty_gold", None)


@pytest.mark.parametrize(
    ("observation", "contract", "isolation"),
    [
        (run([A], snapshot="t" * 64), {"snapshot_mismatch"}, set()),
        (run([A], profile="g" * 64), {"profile_mismatch"}, set()),
        (run([A], config="d" * 64), {"config_mismatch"}, set()),
        (run([A, A]), {"duplicate_retrieval_id"}, set()),
        (run([A, B], ranks=[1, 3]), {"invalid_fused_rank"}, set()),
        (run([u(99)]), {"unknown_chunk"}, set()),
        (run([C]), {"result_outside_snapshot"}, set()),
        (run([A], forbidden=frozenset({A})), set(), {"forbidden_result"}),
        (run([X]), {"result_outside_snapshot"}, {"cross_vendor_result"}),
        (run([Y]), {"result_outside_snapshot"}, {"cross_tenant_result"}),
        (run([A], texts={A: "contains CANARY-1 here"}), set(), {"foreign_canary"}),
    ],
)
def test_failures_are_classified(
    observation: QuestionRun, contract: set[str], isolation: set[str]
) -> None:
    result = check_question(CONTEXT, observation)
    assert codes(result) == (contract, isolation)
    report = result[0]
    assert report.outcome == "invalid" and report.recall_at_5 is None
    assert set(report.failure_codes) == contract | isolation
    assert contract <= CONTRACT_CODES and isolation <= ISOLATION_CODES


def test_too_many_results_is_a_contract_failure() -> None:
    ids = [A, B, *(u(100 + n) for n in range(7))]
    owners = dict(OWNERS) | {chunk: OWNERS[A] for chunk in ids[2:]}
    context = replace(CONTEXT, snapshot_chunks=frozenset(ids), owners=owners)
    contract, isolation = codes(check_question(context, run(ids)))
    assert (contract, isolation) == ({"too_many_results"}, set())


# --- reports -------------------------------------------------------------------------------------

PROFILE = Profile("offline-hashing", "hash-v1", "1", 64, "f" * 64, "offline")


def _group(epoch: str, *observations: QuestionRun) -> GroupReport:
    context = replace(CONTEXT, epoch=epoch)
    results = [check_question(context, o) for o in observations]
    return GroupReport(
        context.tenant, context.vendor, epoch, context.snapshot_sha256, tuple(r[0] for r in results)
    )


def _renamed(observation: QuestionRun, question: str) -> QuestionRun:
    return replace(observation, question_id=question)


def _report(*groups: GroupReport) -> EvaluationReport:
    return EvaluationReport("clean", "d" * 64, "text-md-v1", "c" * 64, PROFILE, groups, (), ())


def test_group_macro_counts_and_failed_group() -> None:
    good = _group(
        INITIAL,
        _renamed(run([A, B]), "RET-01"),
        _renamed(run([A]), "RET-02"),
        _renamed(run([A], gold=frozenset()), "BCP-01"),
    )
    assert good.status == "ok"
    assert good.counts() == {
        "questions": 3,
        "valid_nonempty_gold": 2,
        "valid_empty_gold": 1,
        "invalid": 0,
    }
    assert good.macro() == (Fraction(3, 4), Fraction(3, 4))

    all_empty = _group(FINAL, _renamed(run([A], gold=frozenset()), "BCP-01"))
    assert all_empty.macro() == (None, None) and all_empty.status == "ok"

    failed = _group(FINAL, _renamed(run([A, B]), "RET-01"), _renamed(run([C]), "RET-02"))
    assert failed.status == "failed" and failed.macro() == (None, None)
    assert failed.counts()["invalid"] == 1 and failed.counts()["valid_nonempty_gold"] == 1
    body = failed.to_json()
    assert body["macro"] == {"recall_at_5": None, "recall_at_8": None}
    assert [q["outcome"] for q in body["questions"]] == ["ok", "invalid"]


def test_require_passing_fails_on_any_failed_group_whatever_the_recall() -> None:
    perfect = _group(INITIAL, _renamed(run([A, B]), "RET-01"))
    failed = _group(FINAL, _renamed(run([A, B, C]), "RET-01"))
    require_passing(_report(perfect))
    report = _report(perfect, failed)
    assert report.status == "failed"
    with pytest.raises(EvaluationError) as raised:
        require_passing(report)
    assert raised.value.code == "evaluation_failed"


def test_the_report_is_canonical_sorted_and_stamped() -> None:
    later = _group(FINAL, _renamed(run([B]), "SUB-01"), _renamed(run([A]), "CMP-01"))
    earlier = _group(INITIAL, _renamed(run([A]), "RET-01"))
    data = report_bytes(_report(later, earlier))
    assert data == report_bytes(_report(earlier, later))
    body = json.loads(data)
    assert body["schema"] == REPORT_SCHEMA and body["stamp"] == STAMP
    assert [g["epoch"] for g in body["groups"]] == [INITIAL, FINAL]
    assert [q["id"] for q in body["groups"][1]["questions"]] == ["CMP-01", "SUB-01"]
    assert data == json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
    assert "threshold" not in data.decode()


def test_reports_and_failures_carry_no_document_text() -> None:
    private = "PRIVATE-EVIDENCE-TEXT CANARY-1"
    observation = run([A, B], texts={A: private, B: "other private text"})
    report, contract, isolation = check_question(CONTEXT, observation)
    group = GroupReport(CONTEXT.tenant, CONTEXT.vendor, INITIAL, CONTEXT.snapshot_sha256, (report,))
    full = EvaluationReport(
        "clean", "d" * 64, "text-md-v1", "c" * 64, PROFILE, (group,), contract, isolation
    )
    data = report_bytes(full).decode()
    assert "PRIVATE" not in data and "CANARY-1" not in data and "other private" not in data
    assert json.loads(data)["isolation_failures"][0]["code"] == "foreign_canary"
