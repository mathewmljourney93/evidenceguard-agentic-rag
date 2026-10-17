"""Recall, contract and isolation checks, the evaluation report and the corpus digest (M4e,
ADR-0017).

Pure code over validated values; nothing here reads files, a database or the network.

- ``recall_at_k`` is ``|set(ranked[:k]) ∩ G| / |G|`` as an exact ``Fraction``, or ``None``
  (N/A) for an empty gold set; fewer than k results never change the denominator.
- A question with any contract or isolation failure is ``invalid``: its Recall is not computed
  (``None``), its observed ranked output is kept as returned, and its group and the report are
  ``failed`` with both macro values ``None``. ``require_passing`` then raises.
- The report (``eg-retrieval-eval-v1``) serializes to canonical JSON. Only validated safe
  identifiers appear in it: corpus slugs and keys, epochs, question IDs, fixed codes, canonical
  UUID strings and integers.
- ``corpus_digest`` (``eg-corpus-digest-v1``) frames the variant name, each path and each file's
  exact bytes with 8-byte big-endian lengths, over paths sorted bytewise.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal
from uuid import UUID

from evidenceguard_retrieval.evaluation.corpus import EPOCHS, EvaluationError

REPORT_SCHEMA = "eg-retrieval-eval-v1"
DIGEST_VERSION = "eg-corpus-digest-v1"
STAMP = "NOT a quality measurement of semantic retrieval"
RECALL_KS = (5, 8)
RETRIEVAL_K = 8

Outcome = Literal["ok", "ok_empty_gold", "invalid"]

CONTRACT_CODES = frozenset(
    {
        "duplicate_retrieval_id",
        "invalid_fused_rank",
        "too_many_results",
        "result_outside_snapshot",
        "unknown_chunk",
        "snapshot_mismatch",
        "profile_mismatch",
        "config_mismatch",
    }
)
ISOLATION_CODES = frozenset(
    {"forbidden_result", "cross_vendor_result", "cross_tenant_result", "foreign_canary"}
)


# --- Recall arithmetic ---------------------------------------------------------------------------


def recall_at_k(ranked: Sequence[UUID], gold: frozenset[UUID], k: int) -> Fraction | None:
    """Exact Recall@k, or ``None`` for empty ``gold``. Duplicate IDs are a contract error."""
    if len(set(ranked)) != len(ranked):
        raise EvaluationError("duplicate_retrieval_id")
    if k < 1:
        raise EvaluationError("invalid_k")
    if not gold:
        return None
    return Fraction(len(set(ranked[:k]) & gold), len(gold))


def macro(values: Sequence[Fraction | None]) -> Fraction | None:
    """The mean of the non-``None`` values, or ``None`` when there are none."""
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present, Fraction(0)) / len(present)


def display(value: Fraction) -> str:
    """Four decimal places, round half to even (``Fraction.__round__``), for display only."""
    if value < 0:
        raise EvaluationError("invalid_fraction")
    scaled = round(value * 10_000)
    return f"{scaled // 10_000}.{scaled % 10_000:04d}"


def fraction_json(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "display": display(value),
    }


# --- corpus digest ------------------------------------------------------------------------------


def _frame(data: bytes) -> bytes:
    return len(data).to_bytes(8, "big") + data


def corpus_digest(variant: str, files: Sequence[tuple[str, bytes]]) -> str:
    """``eg-corpus-digest-v1`` over the selected variant's effective file set."""
    paths = [path for path, _ in files]
    if len(set(paths)) != len(paths):
        raise EvaluationError("corpus_digest_invalid")
    digest = hashlib.sha256()
    digest.update(f"{DIGEST_VERSION}\n".encode("ascii"))
    digest.update(_frame(variant.encode("utf-8")))
    for path, data in sorted(files, key=lambda item: item[0].encode("utf-8")):
        if "\\" in path or path.startswith("/") or ".." in path.split("/"):
            raise EvaluationError("corpus_digest_invalid")
        digest.update(_frame(path.encode("utf-8")))
        digest.update(_frame(data))
    return digest.hexdigest()


# --- checks -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkOwner:
    """The loaded corpus's owner of a chunk: tenant, vendor and logical revision reference."""

    tenant: str
    vendor: str
    ref: str


@dataclass(frozen=True)
class GroupContext:
    tenant: str
    vendor: str
    epoch: str
    snapshot_sha256: str
    profile_fingerprint: str
    config_sha256: str
    snapshot_chunks: frozenset[UUID]
    owners: Mapping[UUID, ChunkOwner]


@dataclass(frozen=True)
class RankedItem:
    """One returned item as observed, in result order (``position`` is one-based)."""

    position: int
    chunk_id: UUID
    fused_rank: int


@dataclass(frozen=True)
class QuestionRun:
    """One question's retrieval observation for one epoch."""

    question_id: str
    ranked: tuple[RankedItem, ...]
    result_snapshot_sha256: str
    result_profile_fingerprint: str
    result_config_sha256: str
    evidence_texts: Mapping[UUID, str]
    gold: frozenset[UUID]
    forbidden: frozenset[UUID]
    canaries: tuple[str, ...]


@dataclass(frozen=True)
class Failure:
    code: str
    tenant: str
    vendor: str
    epoch: str
    question: str
    chunk_id: UUID | None
    position: int | None

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "tenant": self.tenant,
            "vendor": self.vendor,
            "epoch": self.epoch,
            "question": self.question,
            "chunk_id": None if self.chunk_id is None else str(self.chunk_id),
            "position": self.position,
        }


@dataclass(frozen=True)
class RankedEntry:
    position: int
    chunk_id: UUID
    ref: str | None


@dataclass(frozen=True)
class QuestionReport:
    id: str
    outcome: Outcome
    failure_codes: tuple[str, ...]
    gold_count: int
    ranked: tuple[RankedEntry, ...]
    recall_at_5: Fraction | None
    recall_at_8: Fraction | None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "outcome": self.outcome,
            "failure_codes": list(self.failure_codes),
            "gold_count": self.gold_count,
            "ranked": [
                {"position": e.position, "chunk_id": str(e.chunk_id), "ref": e.ref}
                for e in self.ranked
            ],
            "recall_at_5": fraction_json(self.recall_at_5),
            "recall_at_8": fraction_json(self.recall_at_8),
        }


def check_question(
    context: GroupContext, run: QuestionRun, k: int = RETRIEVAL_K
) -> tuple[QuestionReport, tuple[Failure, ...], tuple[Failure, ...]]:
    """Contract and isolation checks, then Recall for a valid question. Returns the question
    report and its contract and isolation failures."""
    contract: list[Failure] = []
    isolation: list[Failure] = []

    def fail(target: list[Failure], code: str, chunk: UUID | None, position: int | None) -> None:
        target.append(
            Failure(
                code,
                context.tenant,
                context.vendor,
                context.epoch,
                run.question_id,
                chunk,
                position,
            )
        )

    if run.result_snapshot_sha256 != context.snapshot_sha256:
        fail(contract, "snapshot_mismatch", None, None)
    if run.result_profile_fingerprint != context.profile_fingerprint:
        fail(contract, "profile_mismatch", None, None)
    if run.result_config_sha256 != context.config_sha256:
        fail(contract, "config_mismatch", None, None)
    if len(run.ranked) > k:
        fail(contract, "too_many_results", None, k + 1)

    seen: set[UUID] = set()
    for item in run.ranked:
        chunk = item.chunk_id
        if chunk in seen:
            fail(contract, "duplicate_retrieval_id", chunk, item.position)
        seen.add(chunk)
        if item.fused_rank != item.position:
            fail(contract, "invalid_fused_rank", chunk, item.position)
        owner = context.owners.get(chunk)
        if owner is None:
            fail(contract, "unknown_chunk", chunk, item.position)
        elif chunk not in context.snapshot_chunks:
            fail(contract, "result_outside_snapshot", chunk, item.position)
        if chunk in run.forbidden:
            fail(isolation, "forbidden_result", chunk, item.position)
        if owner is not None and owner.tenant != context.tenant:
            fail(isolation, "cross_tenant_result", chunk, item.position)
        elif owner is not None and owner.vendor != context.vendor:
            fail(isolation, "cross_vendor_result", chunk, item.position)
        text = run.evidence_texts.get(chunk, "")
        if any(canary in text for canary in run.canaries):
            fail(isolation, "foreign_canary", chunk, item.position)

    ranked_entries = tuple(
        RankedEntry(
            item.position,
            item.chunk_id,
            None if item.chunk_id not in context.owners else context.owners[item.chunk_id].ref,
        )
        for item in run.ranked
    )
    codes = tuple(sorted({f.code for f in (*contract, *isolation)}))
    if codes:
        report = QuestionReport(
            run.question_id, "invalid", codes, len(run.gold), ranked_entries, None, None
        )
    else:
        ids = [item.chunk_id for item in run.ranked]
        outcome: Outcome = "ok" if run.gold else "ok_empty_gold"
        report = QuestionReport(
            run.question_id,
            outcome,
            (),
            len(run.gold),
            ranked_entries,
            recall_at_k(ids, run.gold, 5),
            recall_at_k(ids, run.gold, 8),
        )
    return report, tuple(contract), tuple(isolation)


# --- the report --------------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupReport:
    tenant: str
    vendor: str
    epoch: str
    snapshot_sha256: str
    questions: tuple[QuestionReport, ...]

    @property
    def status(self) -> str:
        return "failed" if any(q.outcome == "invalid" for q in self.questions) else "ok"

    def counts(self) -> dict[str, int]:
        return {
            "questions": len(self.questions),
            "valid_nonempty_gold": sum(q.outcome == "ok" for q in self.questions),
            "valid_empty_gold": sum(q.outcome == "ok_empty_gold" for q in self.questions),
            "invalid": sum(q.outcome == "invalid" for q in self.questions),
        }

    def macro(self) -> tuple[Fraction | None, Fraction | None]:
        if self.status == "failed":
            return None, None
        valid = [q for q in self.questions if q.outcome == "ok"]
        return macro([q.recall_at_5 for q in valid]), macro([q.recall_at_8 for q in valid])

    def to_json(self) -> dict[str, Any]:
        at_5, at_8 = self.macro()
        return {
            "tenant": self.tenant,
            "vendor": self.vendor,
            "epoch": self.epoch,
            "snapshot_sha256": self.snapshot_sha256,
            "status": self.status,
            "counts": self.counts(),
            "macro": {"recall_at_5": fraction_json(at_5), "recall_at_8": fraction_json(at_8)},
            "questions": [q.to_json() for q in sorted(self.questions, key=lambda q: q.id)],
        }


@dataclass(frozen=True)
class Profile:
    provider_id: str
    model_id: str
    algorithm_version: str
    dims: int
    fingerprint: str
    label: str

    def to_json(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "algorithm_version": self.algorithm_version,
            "dims": self.dims,
            "fingerprint": self.fingerprint,
            "label": self.label,
        }


@dataclass(frozen=True)
class EvaluationReport:
    variant: str
    corpus_digest: str
    chunker_version: str
    config_sha256: str
    profile: Profile
    groups: tuple[GroupReport, ...]
    contract_failures: tuple[Failure, ...]
    isolation_failures: tuple[Failure, ...]

    @property
    def status(self) -> str:
        return "failed" if any(g.status == "failed" for g in self.groups) else "ok"

    def to_json(self) -> dict[str, Any]:
        def failure_key(f: Failure) -> tuple[Any, ...]:
            return (
                f.tenant,
                f.vendor,
                EPOCHS.index(f.epoch),
                f.question,
                -1 if f.position is None else f.position,
                f.code,
            )

        return {
            "schema": REPORT_SCHEMA,
            "variant": self.variant,
            "corpus_digest": self.corpus_digest,
            "chunker_version": self.chunker_version,
            "config_sha256": self.config_sha256,
            "profile": self.profile.to_json(),
            "status": self.status,
            "stamp": STAMP,
            "groups": [
                g.to_json()
                for g in sorted(
                    self.groups, key=lambda g: (g.tenant, g.vendor, EPOCHS.index(g.epoch))
                )
            ],
            "contract_failures": [
                f.to_json() for f in sorted(self.contract_failures, key=failure_key)
            ],
            "isolation_failures": [
                f.to_json() for f in sorted(self.isolation_failures, key=failure_key)
            ],
        }


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def report_bytes(report: EvaluationReport) -> bytes:
    return canonical_json(report.to_json())


def require_passing(report: EvaluationReport) -> None:
    """Raise ``EvaluationError("evaluation_failed")`` when any group failed, whatever the
    Recall of other groups or questions."""
    if report.status == "failed":
        raise EvaluationError(
            "evaluation_failed",
            counts={
                "contract_failures": len(report.contract_failures),
                "isolation_failures": len(report.isolation_failures),
            },
        )
