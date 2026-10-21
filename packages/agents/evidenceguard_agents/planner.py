"""The deterministic Planner (M5c-B1, D; ADR-0021).

``plan_review`` turns a review template into exactly one ``PlannedQuestion`` per template
question, in template order, whose retrieval request uses the question's search queries
unchanged and in order with ``k`` (default 8). There is no query expansion, rewriting,
reordering, cross-question deduplication or model call (D4/E3). The output is a pure function of
the template and ``k``; it is trusted only when the template came from ``load_pinned_template``.
"""

from dataclasses import dataclass

from evidenceguard_agents.artifact_errors import (
    InvalidAgentArgumentError,
    InvalidAgentValueError,
    require,
    run_guarded,
)
from evidenceguard_agents.templates import ReviewTemplate, _rebuilt_template, _template_question
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.retrieval import DEFAULT_K, MAX_K, RetrievalRequest


@dataclass(frozen=True, init=False, repr=False)
class PlannedQuestion:
    """A template question and its retrieval request; the request's queries are exactly the
    question's search queries (same strings, order and count)."""

    question: EvidenceQuestion
    retrieval: RetrievalRequest

    def __init__(
        self, *, question: EvidenceQuestion, retrieval: RetrievalRequest, **unknown: object
    ) -> None:
        def build() -> None:
            require(not unknown)
            checked_question = _template_question(question)
            require(type(retrieval) is RetrievalRequest)
            checked_retrieval = RetrievalRequest(retrieval.queries, retrieval.k)
            require(checked_retrieval.queries == checked_question.search_queries)
            object.__setattr__(self, "question", checked_question)
            object.__setattr__(self, "retrieval", checked_retrieval)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"PlannedQuestion(question_id={self.question.question_id!r}, "
            f"queries={len(self.retrieval.queries)}, k={self.retrieval.k})"
        )

    __str__ = __repr__


def plan_review(template: ReviewTemplate, *, k: int = DEFAULT_K) -> tuple[PlannedQuestion, ...]:
    """One planned question per template question, in template order. An invalid template or
    ``k`` (not an ``int`` 1-20) is ``InvalidAgentArgumentError``."""

    def build() -> tuple[PlannedQuestion, ...]:
        require(type(k) is int and 1 <= k <= MAX_K)
        checked = _rebuilt_template(template)
        return tuple(
            PlannedQuestion(
                question=question, retrieval=RetrievalRequest(question.search_queries, k)
            )
            for question in checked.questions
        )

    return run_guarded(build, InvalidAgentArgumentError)
