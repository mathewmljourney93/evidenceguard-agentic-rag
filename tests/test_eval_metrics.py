"""M7 (ADR-0029): pure metrics on hand-built cases."""

from fractions import Fraction

import pytest

from evidenceguard_evaluation import metrics
from evidenceguard_evaluation.metrics import CitationCheck, QuestionOutcome


def _outcomes(*rows: tuple[str | None, str | None]) -> list[QuestionOutcome]:
    return [QuestionOutcome(f"Q-{i:02d}", e, a) for i, (e, a) in enumerate(rows)]


def test_recall_at_k_counts_gold_in_the_top_k_only() -> None:
    ranked = ["a", "x", "b", "y", "z", "c"]
    assert metrics.recall_at_k(ranked, {"a", "b", "c"}, 5) == Fraction(2, 3)
    assert metrics.recall_at_k(ranked, {"a", "b", "c"}, 8) == Fraction(1)
    assert metrics.recall_at_k(ranked, set(), 5) is None
    with pytest.raises(ValueError):
        metrics.recall_at_k(ranked, {"a"}, 0)


def test_wilson_bounds() -> None:
    assert metrics.wilson_interval(0, 0) is None
    low, high = metrics.wilson_interval(9, 10) or (0.0, 0.0)
    assert low == pytest.approx(0.5958, abs=1e-4) and high == pytest.approx(0.9821, abs=1e-4)
    low, high = metrics.wilson_interval(0, 5) or (1.0, 1.0)
    assert low == 0.0 and high == pytest.approx(0.4345, abs=1e-4)
    assert metrics.wilson_interval(5, 5) is not None


def test_claim_support_precision_and_probe_accuracy() -> None:
    assert metrics.claim_support_precision([]) is None
    assert metrics.claim_support_precision([True, True, False, True]) == Fraction(3, 4)
    verdicts = [(True, True), (False, False), (False, True)]
    assert metrics.probe_accuracy(verdicts) == Fraction(2, 3)
    assert metrics.probe_accuracy([]) is None


def test_coverage_excludes_expected_missing_from_its_denominator() -> None:
    outcomes = _outcomes(
        ("vendor_claim", "vendor_claim"),
        ("conflicting", None),  # unresolved: no status given
        ("documentary_support", "missing"),
        ("missing", "missing"),
        ("missing", "vendor_claim"),
        (None, "vendor_claim"),  # unlabelled: never counted
    )
    assert metrics.coverage(outcomes) == Fraction(1, 3)
    assert metrics.abstention(outcomes) == {"correct": Fraction(1, 2), "false": Fraction(1, 3)}
    assert metrics.status_accuracy(outcomes) == {
        "conflicting": (0, 1),
        "documentary_support": (0, 1),
        "missing": (1, 2),
        "vendor_claim": (1, 1),
    }


def test_conflict_detection_reports_false_conflicts_and_the_superseded_trap() -> None:
    outcomes = _outcomes(("conflicting", "conflicting"), ("vendor_claim", "conflicting"))
    result = metrics.conflict_detection(outcomes, superseded_citations=2)
    assert result == {"detected": Fraction(1), "false": Fraction(1), "superseded_citations": 2}


def test_provenance_violations_use_the_authorized_set_and_stored_text() -> None:
    authorized = {"c1": "Customer data is retained for ninety (90) days."}
    checks = [
        CitationCheck("c1", "ninety (90) days", authorized),
        CitationCheck("c1", "thirty (30) days", authorized),
        CitationCheck("c2", "ninety (90) days", authorized),
    ]
    assert metrics.provenance_violations(checks) == 2


def test_flip_rate_against_the_clean_baseline() -> None:
    clean: list[dict[str, str | None]] = [
        {"a": "missing", "b": "vendor_claim"},
        {"a": "missing", "b": None},
    ]
    injected: list[dict[str, str | None]] = [
        {"a": "vendor_claim", "b": "vendor_claim"},
        {"a": "vendor_claim", "b": None},
    ]
    assert metrics.flip_rate(clean[0], clean[1]) == Fraction(1, 2)
    effect = metrics.injection_effect(clean, injected)
    assert effect == {"injected_flip_rate": Fraction(1, 2), "clean_flip_rate": Fraction(1, 2)}
    assert metrics.injection_effect(clean[:1], [])["clean_flip_rate"] is None


def test_the_canary_scan_covers_every_free_text_field_case_insensitively() -> None:
    fields = [
        ("rationale", "Per lv-tb-canary-aes."),
        ("claim", "Nothing here."),
        ("finding", "SEE LV-TB-CANARY-36H"),
        ("follow-up", "Which evidence?"),
    ]
    found = metrics.canary_scan(fields, ["LV-TB-CANARY-AES", "LV-TB-CANARY-36H"])
    assert found == ["rationale", "finding"]
    assert metrics.canary_scan(fields, []) == []


def test_latency_has_no_p95_below_twenty_values() -> None:
    small = metrics.latency_summary([30, 10, 20])
    assert small["n"] == 3 and small["min"] == 10 and small["max"] == 30
    assert small["median"] == {"numerator": 20, "denominator": 1}
    assert small["p95"] is None and small["raw"] == [30, 10, 20]
    large = metrics.latency_summary(list(range(1, 21)))
    assert large["p95"] == 19
    assert metrics.latency_summary([])["median"] is None


def test_refusals_are_counted_by_category() -> None:
    outcomes = ["completed", "refusal", "refusal", "timeout"]
    assert metrics.refusal_counts(outcomes) == {"refusal": 2, "timeout": 1}
