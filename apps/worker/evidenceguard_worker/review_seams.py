"""Review-creation composition seams with the pinned M5c artifacts (M5d, ADR-0022).

Internal and test-only: no runtime path, command, API route or registry imports this module, and
``run_review`` is not registered in production (W8). It is the only worker module that imports
``evidenceguard_agents`` (D2); persistence never does.

- ``create_review_with_artifacts`` checks the actor and request, then the role, then loads the
  pinned template and both prompts through the M5c loaders **before any database work**, and only
  then calls ``create_review``.
- ``load_trusted_review`` checks its inputs and role, calls ``load_review``, then loads the same
  pinned artifacts and returns a validated ``ResolvedReview``.

An unknown or altered artifact is ``ReviewArtifactsUnavailableError``. Errors are fresh, raised
after leaving every handler, with no cause or context; process control propagates as the same
object; nothing logs.
"""

import hashlib
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from evidenceguard_agents.prompts import PromptSpec, load_pinned_prompt
from evidenceguard_agents.templates import ReviewTemplate, TemplateRef, load_pinned_template
from evidenceguard_domain.context import ActorContext
from evidenceguard_domain.errors import PermissionDeniedError
from evidenceguard_domain.model_calls import ModelPurpose
from evidenceguard_domain.reviews import (
    CreatedReview,
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewArtifactsUnavailableError,
    ReviewConfiguration,
    ReviewRequest,
    TrustedReview,
    rebuilt_request,
)
from evidenceguard_persistence.retrieval import RETRIEVAL_ROLES
from evidenceguard_persistence.reviews import create_review, load_review


class _Invalid(Exception):
    """Private: a failed check inside a guarded construction."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Invalid


def _run[T](build: Callable[[], T], error: type[Exception]) -> T:
    built: list[T] = []
    with suppress(Exception):
        built.append(build())
    if not built:
        raise error()
    return built[0]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, init=False, repr=False)
class ResolvedReview:
    """A trusted review with its pinned template and prompts. The constructor checks
    consistency only; it cannot prove that the artifacts came from the pinned loaders (only
    ``load_trusted_review`` builds it that way)."""

    review: TrustedReview
    template: ReviewTemplate
    verifier: PromptSpec
    verifier_system_text: str
    analyst: PromptSpec
    analyst_system_text: str

    def __init__(
        self,
        *,
        review: TrustedReview,
        template: ReviewTemplate,
        verifier: PromptSpec,
        verifier_system_text: str,
        analyst: PromptSpec,
        analyst_system_text: str,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and type(review) is TrustedReview)
            checked_review = TrustedReview(
                review_id=review.review_id,
                tenant_id=review.tenant_id,
                request=review.request,
                request_sha256=review.request_sha256,
                snapshot=review.snapshot,
                job_id=review.job_id,
            )
            configuration = checked_review.request.configuration
            _require(type(template) is ReviewTemplate)
            checked_template = ReviewTemplate(
                ref=template.ref, title=template.title, questions=template.questions
            )
            _require(checked_template.ref == _template_ref(configuration))
            for spec, text, ref, purpose in (
                (
                    verifier,
                    verifier_system_text,
                    configuration.verifier_prompt,
                    ModelPurpose.VERIFIER,
                ),
                (
                    analyst,
                    analyst_system_text,
                    configuration.analyst_prompt,
                    ModelPurpose.RISK_ANALYST,
                ),
            ):
                _require(type(spec) is PromptSpec and type(text) is str)
                checked_spec = PromptSpec(ref=spec.ref, purpose=spec.purpose)
                _require(checked_spec.ref == ref and checked_spec.purpose is purpose)
                _require(_digest(text) == ref.sha256)
            object.__setattr__(self, "review", checked_review)
            object.__setattr__(self, "template", checked_template)
            object.__setattr__(
                self, "verifier", PromptSpec(ref=verifier.ref, purpose=verifier.purpose)
            )
            object.__setattr__(self, "verifier_system_text", verifier_system_text)
            object.__setattr__(
                self, "analyst", PromptSpec(ref=analyst.ref, purpose=analyst.purpose)
            )
            object.__setattr__(self, "analyst_system_text", analyst_system_text)

        _run(build, InvalidReviewValueError)

    def __repr__(self) -> str:
        return (
            f"ResolvedReview(review_id={self.review.review_id}, "
            f"template_id={self.template.ref.template_id!r}, "
            f"template_version={self.template.ref.version})"
        )

    __str__ = __repr__


def _template_ref(configuration: ReviewConfiguration) -> TemplateRef:
    return TemplateRef(
        template_id=configuration.template_id,
        version=configuration.template_version,
        sha256=configuration.template_sha256,
    )


@dataclass(frozen=True)
class _Artifacts:
    template: ReviewTemplate
    verifier: tuple[PromptSpec, str]
    analyst: tuple[PromptSpec, str]


def _load_artifacts(configuration: ReviewConfiguration) -> _Artifacts:
    """The pinned template and prompts; any M5c failure is ``ReviewArtifactsUnavailableError``."""

    def build() -> _Artifacts:
        return _Artifacts(
            template=load_pinned_template(_template_ref(configuration)),
            verifier=load_pinned_prompt(configuration.verifier_prompt, ModelPurpose.VERIFIER),
            analyst=load_pinned_prompt(configuration.analyst_prompt, ModelPurpose.RISK_ANALYST),
        )

    return _run(build, ReviewArtifactsUnavailableError)


def _checked_actor(actor: object) -> ActorContext:
    if type(actor) is not ActorContext:
        raise InvalidReviewRequestError()
    assert isinstance(actor, ActorContext)
    return actor


def _require_role(actor: ActorContext) -> None:
    if actor.role not in RETRIEVAL_ROLES:
        raise PermissionDeniedError()


def create_review_with_artifacts(
    session_factory: sessionmaker[Session], actor: ActorContext, request: ReviewRequest
) -> CreatedReview:
    """Check inputs, role and the pinned artifacts, then create the review."""
    checked_actor = _checked_actor(actor)
    checked = rebuilt_request(request)
    _require_role(checked_actor)
    _load_artifacts(checked.configuration)
    return create_review(session_factory, checked_actor, checked)


def load_trusted_review(
    session_factory: sessionmaker[Session], actor: ActorContext, review_id: UUID
) -> ResolvedReview:
    """Reload a review and resolve its pinned template and prompts."""
    checked_actor = _checked_actor(actor)
    if type(review_id) is not UUID:
        raise InvalidReviewRequestError()
    _require_role(checked_actor)
    review = load_review(session_factory, checked_actor, review_id)
    artifacts = _load_artifacts(review.request.configuration)
    return _run(
        lambda: ResolvedReview(
            review=review,
            template=artifacts.template,
            verifier=artifacts.verifier[0],
            verifier_system_text=artifacts.verifier[1],
            analyst=artifacts.analyst[0],
            analyst_system_text=artifacts.analyst[1],
        ),
        ReviewArtifactsUnavailableError,
    )
