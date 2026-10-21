"""Fixed errors and the guarded-operation runner for M5c (ADR-0021).

Every M5c error carries only its fixed code as its message: never a submitted value, template or
prompt text, evidence, quotation or model text, and never a cause or context. ``run_guarded``
runs one whole public operation (argument traversal, copying, resource handling and
construction): an ordinary failure becomes a fresh fixed error raised after leaving the handler,
so nothing is chained. Only ``Exception`` is caught; process control (``KeyboardInterrupt``,
``SystemExit`` and other ``BaseException`` subclasses) propagates as the same object. Nothing here
logs.
"""

from collections.abc import Callable
from typing import ClassVar


class ReviewArtifactError(Exception):
    """Base of the fixed M5c errors."""

    code: ClassVar[str] = "review_artifact_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidTemplateError(ReviewArtifactError):
    """Any ``parse_template`` failure, including a non-``bytes`` argument."""

    code = "invalid_review_template"


class UnknownTemplateError(ReviewArtifactError):
    """A well-formed template ID and version that is not in the registry."""

    code = "unknown_review_template"


class TemplateIntegrityError(ReviewArtifactError):
    """A registered template that is missing, unreadable, oversize, of the wrong digest or
    invalid, or a loaded reference that differs from the pinned one."""

    code = "template_integrity_failed"


class UnknownPromptError(ReviewArtifactError):
    """A well-formed prompt ID and version that is not in the registry."""

    code = "unknown_prompt"


class PromptIntegrityError(ReviewArtifactError):
    """A registered prompt that is missing, unreadable, oversize, empty, BOM-prefixed, not
    strict UTF-8, NUL-bearing or of the wrong digest, or a loaded reference or purpose that
    differs from the pinned one."""

    code = "prompt_integrity_failed"


class InvalidAgentArgumentError(ReviewArtifactError):
    """Wrong argument types or shapes for the loaders and ``plan_review``."""

    code = "invalid_agent_argument"


class InvalidAgentValueError(ReviewArtifactError):
    """Invalid direct construction or replacement of an M5c value."""

    code = "invalid_agent_value"


class InvalidAssemblyInputError(ReviewArtifactError):
    """Invalid or mismatched assembly inputs, a purpose or prompt-binding failure, invalid
    Unicode, or a repair mismatch (including an already-repaired request)."""

    code = "invalid_assembly_input"


class RequestTooLargeError(ReviewArtifactError):
    """A serialized user text above 400,000 UTF-8 bytes; no request is created."""

    code = "request_too_large"


class CheckFailed(Exception):
    """A failed check inside a guarded operation (translated by ``run_guarded``)."""


def require(condition: bool) -> None:
    if not condition:
        raise CheckFailed


def run_guarded[T](
    build: Callable[[], T],
    error: type[ReviewArtifactError],
    *,
    keep: tuple[type[ReviewArtifactError], ...] = (),
) -> T:
    """Run one whole public operation. An M5c error whose exact class is in ``keep`` is raised
    again as a fresh instance of that class; every other ordinary failure becomes a fresh
    ``error``. Both are raised after leaving the handler, so no cause or context is retained.
    Exception chains are never inspected."""
    built: list[T] = []
    raised = error
    try:
        built.append(build())
    except ReviewArtifactError as failure:
        if type(failure) in keep:
            raised = type(failure)
    except Exception:  # translated into the fixed error below
        pass
    if not built:
        raise raised()
    return built[0]
