"""Contract-suite scripts for the scripted fake provider (M7, ADR-0029).

The contract suite runs the production review handler with ``ScriptedFakeProvider`` in two
phases per (tenant, vendor) pair. Its outputs are contract fixtures: **NOT a quality measurement
of Claude or semantic retrieval**.

1. **Refusal phase.** Every key answers ``Refuse()``; every question must end unresolved with no
   findings. The run records each question's retrieved set.
2. **Scripted phase.** A second review of the same pair. Scripts are built here from the human
   ground truth and the refusal phase's retrieved sets, never from a model or a request:
   expected non-missing questions cite the retrieved chunks that contain a gold anchor quote,
   with the verdict that yields the expected status; expected-missing and unlabelled questions
   answer ``insufficient_evidence`` with no claim. Four fixed traps each must leave their
   question unresolved with no provenance violation in the output: a citation of another
   tenant's chunk, a quote that is not in the cited chunk, a response naming another model and
   invalid JSON.

The fake itself never reads the ground truth: this module hands it finished response texts.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evidenceguard_agents.scripted import (
    FAKE_MODEL_ID,
    Refuse,
    Respond,
    ScriptedFakeProvider,
    Step,
    WrongModel,
)
from evidenceguard_evaluation.records import RetrievedItem

CONTRACT_MODEL_ID = FAKE_MODEL_ID
"""The model id the contract reviews pin: the scripted fake's own id."""
VERIFIER = "verifier"
ANALYST = "risk_analyst"
TRAP_FOREIGN_CITATION = "foreign_citation"
TRAP_QUOTE_MISMATCH = "quote_mismatch"
TRAP_WRONG_MODEL = "wrong_model"
TRAP_INVALID_JSON = "invalid_json"
TRAPS = (TRAP_FOREIGN_CITATION, TRAP_QUOTE_MISMATCH, TRAP_WRONG_MODEL, TRAP_INVALID_JSON)
TRAP_STEPS = 12
"""More steps than one stage can ever consume (initial, retries and one repair)."""
REFUSAL_STEPS = 12
OTHER_MODEL_ID = "fake-other-model-v1"
MISMATCHED_QUOTE = "This sentence does not occur in any evidence passage."
NIL_CHUNK_ID = "00000000-0000-0000-0000-000000000000"
NO_ANSWER_RATIONALE = "Contract fixture: the scripted answer gives no evidence for this question."
ANSWER_RATIONALE = "Contract fixture: scripted from the human ground truth."
EMPTY_ANALYSIS = json.dumps({"findings": []})


@dataclass(frozen=True)
class GoldPassage:
    anchor: str
    quote: str


@dataclass(frozen=True)
class QuestionPlan:
    """The scripted-phase plan for one template question."""

    question_id: str
    expected_status: str | None
    gold: tuple[GoldPassage, ...] = ()
    claim_text: str | None = None
    trap: str | None = None


@dataclass(frozen=True)
class ScriptedAnswer:
    """What the script answers for one question: the cited (chunk id, quote) pairs and the
    gold anchor each pair comes from."""

    question_id: str
    verdict: str
    citations: tuple[tuple[str, str, str], ...]


def refusal_provider(question_ids: Sequence[str]) -> ScriptedFakeProvider:
    """Phase 1: every Verifier and Risk Analyst key refuses."""
    refusals: tuple[Step, ...] = tuple(Refuse() for _ in range(REFUSAL_STEPS))
    scripts: dict[tuple[str, str], tuple[Step, ...]] = {}
    for question_id in question_ids:
        scripts[(VERIFIER, question_id)] = refusals
        scripts[(ANALYST, question_id)] = refusals
    return ScriptedFakeProvider(scripts=scripts)


def _verifier_text(verdict: str, claims: list[dict[str, Any]], rationale: str) -> str:
    return json.dumps({"verdict": verdict, "claims": claims, "rationale": rationale})


def answer_for(plan: QuestionPlan, retrieved: Sequence[RetrievedItem]) -> ScriptedAnswer:
    """The non-trap answer: cite every retrieved chunk containing a gold quote."""
    citations: list[tuple[str, str, str]] = []
    for passage in plan.gold:
        for item in retrieved:
            if passage.quote in item.text:
                citations.append((item.chunk_id, passage.quote, passage.anchor))
                break
    expected = plan.expected_status
    if expected == "conflicting" and len({quote for _, quote, _ in citations}) >= 2:
        return ScriptedAnswer(plan.question_id, "contradicted", tuple(citations))
    if expected in ("vendor_claim", "documentary_support") and citations:
        return ScriptedAnswer(plan.question_id, "supported", tuple(citations))
    return ScriptedAnswer(plan.question_id, "insufficient_evidence", ())


def _answer_text(plan: QuestionPlan, answer: ScriptedAnswer, rationale: str) -> str:
    if answer.verdict == "insufficient_evidence":
        return _verifier_text(answer.verdict, [], NO_ANSWER_RATIONALE)
    claim = {
        "text": plan.claim_text or "Contract fixture claim.",
        "citations": [{"chunk_id": chunk, "quote": quote} for chunk, quote, _ in answer.citations],
    }
    return _verifier_text(answer.verdict, [claim], rationale)


def _trap_steps(
    trap: str, retrieved: Sequence[RetrievedItem], foreign: RetrievedItem
) -> tuple[Step, ...]:
    if trap == TRAP_FOREIGN_CITATION:
        claim = {
            "text": "Contract trap.",
            "citations": [{"chunk_id": foreign.chunk_id, "quote": foreign.text[:200].strip()}],
        }
        text = _verifier_text("supported", [claim], ANSWER_RATIONALE)
        return tuple(Respond(text) for _ in range(TRAP_STEPS))
    if trap == TRAP_QUOTE_MISMATCH:
        chunk = retrieved[0].chunk_id if retrieved else NIL_CHUNK_ID
        claim = {
            "text": "Contract trap.",
            "citations": [{"chunk_id": chunk, "quote": MISMATCHED_QUOTE}],
        }
        text = _verifier_text("supported", [claim], ANSWER_RATIONALE)
        return tuple(Respond(text) for _ in range(TRAP_STEPS))
    if trap == TRAP_WRONG_MODEL:
        text = _verifier_text("insufficient_evidence", [], NO_ANSWER_RATIONALE)
        return tuple(WrongModel(OTHER_MODEL_ID, text) for _ in range(TRAP_STEPS))
    if trap == TRAP_INVALID_JSON:
        return tuple(Respond("{not valid json") for _ in range(TRAP_STEPS))
    raise ValueError("unknown trap")


@dataclass(frozen=True)
class ScriptedPhase:
    provider: ScriptedFakeProvider
    answers: Mapping[str, ScriptedAnswer]


def scripted_provider(
    plans: Sequence[QuestionPlan],
    retrieved: Mapping[str, Sequence[RetrievedItem]],
    *,
    foreign: RetrievedItem,
    rationale_extra: str | None = None,
) -> ScriptedPhase:
    """Phase 2 scripts (module docstring). ``rationale_extra`` is a test hook that appends text
    to the first answered rationale (the canary negative control); the CLI never sets it."""
    scripts: dict[tuple[str, str], tuple[Step, ...]] = {}
    answers: dict[str, ScriptedAnswer] = {}
    extra_pending = rationale_extra
    analysis = tuple(Respond(EMPTY_ANALYSIS) for _ in range(TRAP_STEPS))
    for plan in plans:
        items = retrieved.get(plan.question_id, ())
        scripts[(ANALYST, plan.question_id)] = analysis
        if plan.trap is not None:
            scripts[(VERIFIER, plan.question_id)] = _trap_steps(plan.trap, items, foreign)
            continue
        answer = answer_for(plan, items)
        answers[plan.question_id] = answer
        rationale = ANSWER_RATIONALE
        if extra_pending is not None and answer.verdict != "insufficient_evidence":
            rationale = f"{ANSWER_RATIONALE} {extra_pending}"
            extra_pending = None
        text = _answer_text(plan, answer, rationale)
        scripts[(VERIFIER, plan.question_id)] = tuple(Respond(text) for _ in range(TRAP_STEPS))
    return ScriptedPhase(ScriptedFakeProvider(scripts=scripts), answers)
