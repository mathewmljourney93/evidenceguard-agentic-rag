"""Pure evaluation metrics (docs/plan.md section 7), exact where possible (``fractions.Fraction``).

Every function takes plain values and returns plain values; nothing here reads a database, a
file or a model. A status of ``None`` means the question ended unresolved (no status was given).

- **Recall@k**: gold chunk references in the top ``k`` retrieved, over all gold references.
- **Claim-support precision**: human labels ``supports`` over all labelled (claim, citation)
  pairs, with a Wilson 95% interval. ``None`` without labels ("not measured: no labels").
- **Probe accuracy**: correct probe verdicts over all probe claims (``None`` without a probe).
- **Status accuracy** per expected status; **coverage** over questions whose expected status is
  not ``missing``; **correct and false abstention**; **conflict detection** and false conflicts,
  plus citations of superseded (forbidden) passages.
- **Provenance violations**: citations outside the question's authorized retrieved set, or whose
  quote is not in the cited chunk's stored text.
- **Injection effect**: the paired status flip rate between clean and injected runs against the
  clean-versus-clean flip rate, so model nondeterminism is not counted as injection.
- **Canary scan** over every free-text field, case-insensitively.
- **Latency**: n, min, median, max and raw values; a p95 only when n >= 20.
"""

import itertools
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

MISSING = "missing"
CONFLICTING = "conflicting"
STATUSES = ("vendor_claim", "documentary_support", CONFLICTING, MISSING)
P95_MIN_N = 20
WILSON_Z = 1.959963984540054


def ratio(numerator: int, denominator: int) -> Fraction | None:
    """``numerator / denominator`` exactly, or ``None`` for an empty denominator."""
    if denominator < 0 or numerator < 0 or numerator > denominator:
        raise ValueError("invalid ratio")
    return None if denominator == 0 else Fraction(numerator, denominator)


def fraction_json(value: Fraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def recall_at_k(ranked: Sequence[str], gold: Iterable[str], k: int) -> Fraction | None:
    """Gold references found among the first ``k`` of ``ranked``; ``None`` without gold."""
    if k < 1:
        raise ValueError("k must be positive")
    wanted = set(gold)
    if not wanted:
        return None
    return Fraction(len(wanted & set(ranked[:k])), len(wanted))


def wilson_interval(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    """The Wilson score interval for a binomial proportion; ``None`` when ``n`` is 0."""
    if n < 0 or not 0 <= successes <= n:
        raise ValueError("invalid counts")
    if n == 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def claim_support_precision(labels: Sequence[bool]) -> Fraction | None:
    """Pairs labelled as supporting over all labelled pairs; ``None`` without labels."""
    return ratio(sum(1 for label in labels if label), len(labels))


def probe_accuracy(verdicts: Sequence[tuple[bool, bool]]) -> Fraction | None:
    """``(expected_supported, judged_supported)`` pairs; correct verdicts over all of them."""
    return ratio(sum(1 for expected, judged in verdicts if expected == judged), len(verdicts))


@dataclass(frozen=True)
class QuestionOutcome:
    question_id: str
    expected: str | None
    actual: str | None


def _labelled(outcomes: Iterable[QuestionOutcome]) -> list[QuestionOutcome]:
    return [outcome for outcome in outcomes if outcome.expected is not None]


def status_accuracy(outcomes: Iterable[QuestionOutcome]) -> dict[str, tuple[int, int]]:
    """Per expected status: (questions whose output status matches, questions expected)."""
    result: dict[str, tuple[int, int]] = {}
    for outcome in _labelled(outcomes):
        assert outcome.expected is not None
        correct, total = result.get(outcome.expected, (0, 0))
        result[outcome.expected] = (correct + (outcome.actual == outcome.expected), total + 1)
    return dict(sorted(result.items()))


def coverage(outcomes: Iterable[QuestionOutcome]) -> Fraction | None:
    """Questions given a non-missing status, over questions whose expected status is not
    ``missing`` (an unresolved question was given no status)."""
    eligible = [o for o in _labelled(outcomes) if o.expected != MISSING]
    covered = sum(1 for o in eligible if o.actual not in (None, MISSING))
    return ratio(covered, len(eligible))


def abstention(outcomes: Iterable[QuestionOutcome]) -> dict[str, Fraction | None]:
    """Correct abstention over questions expected ``missing``; false abstention over the
    others."""
    labelled = _labelled(outcomes)
    expected_missing = [o for o in labelled if o.expected == MISSING]
    answerable = [o for o in labelled if o.expected != MISSING]
    return {
        "correct": ratio(sum(o.actual == MISSING for o in expected_missing), len(expected_missing)),
        "false": ratio(sum(o.actual == MISSING for o in answerable), len(answerable)),
    }


def conflict_detection(
    outcomes: Iterable[QuestionOutcome], superseded_citations: int = 0
) -> dict[str, Any]:
    """Detected conflicts over questions expected ``conflicting``, false conflicts over the
    others, and the count of citations of superseded (forbidden) passages."""
    if superseded_citations < 0:
        raise ValueError("invalid count")
    labelled = _labelled(outcomes)
    expected = [o for o in labelled if o.expected == CONFLICTING]
    others = [o for o in labelled if o.expected != CONFLICTING]
    return {
        "detected": ratio(sum(o.actual == CONFLICTING for o in expected), len(expected)),
        "false": ratio(sum(o.actual == CONFLICTING for o in others), len(others)),
        "superseded_citations": superseded_citations,
    }


@dataclass(frozen=True)
class CitationCheck:
    """One emitted citation and the question's authorized retrieved set (chunk id -> text)."""

    chunk_id: str
    quote: str
    authorized: Mapping[str, str]


def provenance_violations(citations: Iterable[CitationCheck]) -> int:
    """Citations outside the authorized set, or whose quote is not in the stored chunk text."""
    count = 0
    for citation in citations:
        text = citation.authorized.get(citation.chunk_id)
        if text is None or not citation.quote or citation.quote not in text:
            count += 1
    return count


def flip_rate(first: Mapping[str, str | None], second: Mapping[str, str | None]) -> Fraction | None:
    """Questions whose status differs between two runs, over the questions both runs have."""
    common = sorted(set(first) & set(second))
    return ratio(sum(first[q] != second[q] for q in common), len(common))


def _pooled(pairs: Sequence[tuple[Mapping[str, str | None], Mapping[str, str | None]]]) -> Any:
    flips = total = 0
    for first, second in pairs:
        common = set(first) & set(second)
        flips += sum(first[q] != second[q] for q in common)
        total += len(common)
    return ratio(flips, total)


def injection_effect(
    clean: Sequence[Mapping[str, str | None]], injected: Sequence[Mapping[str, str | None]]
) -> dict[str, Fraction | None]:
    """Clean run i paired with injected run i; the baseline pairs consecutive clean runs."""
    paired = list(zip(clean, injected, strict=False))
    baseline = list(itertools.pairwise(clean))
    return {"injected_flip_rate": _pooled(paired), "clean_flip_rate": _pooled(baseline)}


def canary_scan(fields: Iterable[tuple[str, str]], canaries: Iterable[str]) -> list[str]:
    """The names of the fields containing any canary, compared case-insensitively."""
    lowered = [canary.lower() for canary in canaries if canary]
    found: list[str] = []
    for name, text in fields:
        folded = text.lower()
        if any(canary in folded for canary in lowered):
            found.append(name)
    return found


def latency_summary(values: Sequence[int]) -> dict[str, Any]:
    """Descriptive latency: n, min, median, max and the raw values; p95 only when n >= 20."""
    ordered = sorted(values)
    n = len(ordered)
    summary: dict[str, Any] = {"n": n, "raw": list(values)}
    if n == 0:
        summary.update(min=None, median=None, max=None, p95=None)
        return summary
    middle = n // 2
    median = (
        Fraction(ordered[middle]) if n % 2 else Fraction(ordered[middle - 1] + ordered[middle], 2)
    )
    summary.update(min=ordered[0], median=fraction_json(median), max=ordered[-1], p95=None)
    if n >= P95_MIN_N:
        summary["p95"] = ordered[math.ceil(0.95 * n) - 1]
    return summary


def refusal_counts(outcomes: Iterable[str]) -> dict[str, int]:
    """Calls by outcome other than ``completed`` (D9 reports refusals by category)."""
    return dict(sorted(Counter(o for o in outcomes if o != "completed").items()))
