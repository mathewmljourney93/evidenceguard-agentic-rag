"""Review output values and the strict stored-row decoder (M5g, ADR-0025).

Implements M5g-A of the specification accepted in Prompt 217 (``docs/plan.md``). Every value is a
frozen dataclass with a keyword-only validating constructor:

- exact types (``type(x) is T``: a ``bool`` is never an ``int``, a ``str`` subclass is refused);
- an unknown keyword, or a missing one, is the value's fixed error;
- nested values are rebuilt through their own constructors and compared for equality, with no
  normalization (only ``created_at`` is converted to UTC, as specified);
- derived fields are recomputed and never accepted as arguments;
- ``repr``/``str`` show identifiers, digests and counts only: never a title, question or finding
  text, quotation, rationale, wrapper or Markdown bytes.

Construction failures are a fresh fixed error raised after leaving the handler, with no cause or
context; process control propagates as the same object. Nothing here logs, touches a database or
proves that a value came from one.

What a ``ReviewOutput`` cannot prove: that its content came from trusted stages through the M5f
source-bound recheck, that ``markdown_sha256``/``markdown_bytes`` describe the pinned renderer's
output, or that the database links the job to the review. Those are worker and writer
obligations (``evidenceguard_worker.review`` and ``evidenceguard_persistence.review_outputs``).
"""

import hashlib
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from evidenceguard_domain.report_content import (
    MAX_CONTENT_BYTES,
    MAX_MARKDOWN_BYTES,
    RENDERER,
    SCHEMA,
    ReportMode,
    ReviewReportContent,
    decode_review_report,
    revalidate_review_report,
    review_report_bytes,
)

MAX_QUESTIONS = 100
MAX_FINDINGS = 200
MAX_JOB_ATTEMPT = 10
REVIEW_OUTPUT_COLUMNS = frozenset(
    {
        "tenant_id",
        "review_id",
        "job_id",
        "schema_id",
        "renderer_id",
        "mode",
        "wrapper_canonical",
        "wrapper_sha256",
        "legacy_sha256",
        "review_request_sha256",
        "snapshot_sha256",
        "configuration_sha256",
        "question_count",
        "finding_count",
        "unresolved_count",
        "markdown_sha256",
        "markdown_bytes",
        "job_attempt",
        "created_at",
    }
)
"""The exact column names of one ``review_outputs`` row (the decoder's closed key set)."""

_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_PRINTABLE = re.compile(r"[ -~]*", re.ASCII)
_MISSING: Any = object()


# --- errors (fixed codes and messages) -----------------------------------------------------------


class ReviewOutputValueError(Exception):
    """Base of the fixed M5g domain errors."""

    code: ClassVar[str] = "review_output_error"
    message: ClassVar[str] = "the review output value is invalid"

    def __init__(self) -> None:
        super().__init__(self.message)


class InvalidReviewOutputError(ReviewOutputValueError):
    """Invalid ``ReviewOutput`` construction or replacement."""

    code = "invalid_review_output"
    message = "the review output is invalid"


class InvalidStoredOutputError(ReviewOutputValueError):
    """An invalid stored row, ``StoredReviewOutput`` or ``ReviewOutputWrite``."""

    code = "invalid_stored_review_output"
    message = "the stored review output is invalid"


class _Invalid(Exception):
    """Private: a failed check inside a guarded construction."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Invalid


def _run[T](build: Callable[[], T], error: type[ReviewOutputValueError]) -> T:
    """Run one guarded construction. Any ordinary failure (including a missing keyword reported
    as ``_MISSING``) becomes a fresh ``error`` raised after the handler; process control
    propagates as the same object."""
    built: list[T] = []
    with suppress(Exception):  # translated below, outside the handler; nothing is retained
        built.append(build())
    if not built:
        raise error()
    return built[0]


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _supplied(*values: object) -> bool:
    return all(value is not _MISSING for value in values)


# --- values --------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class ReviewOutput:
    """A review's hash-covered report content with its Markdown digest and size, ready to be
    stored. Every derived field is recomputed from ``content`` (M5g-A)."""

    tenant_id: UUID
    review_id: UUID
    job_id: UUID
    content: ReviewReportContent
    markdown_sha256: str
    markdown_bytes: int
    schema_id: str = field(init=False)
    renderer_id: str = field(init=False)
    mode: str = field(init=False)
    wrapper_canonical: bytes = field(init=False)
    wrapper_sha256: str = field(init=False)
    legacy_sha256: str = field(init=False)
    review_request_sha256: str = field(init=False)
    snapshot_sha256: str = field(init=False)
    configuration_sha256: str = field(init=False)
    question_count: int = field(init=False)
    finding_count: int = field(init=False)
    unresolved_count: int = field(init=False)

    def __init__(
        self,
        *,
        tenant_id: UUID = _MISSING,
        review_id: UUID = _MISSING,
        job_id: UUID = _MISSING,
        content: ReviewReportContent = _MISSING,
        markdown_sha256: str = _MISSING,
        markdown_bytes: int = _MISSING,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown)
            _require(_supplied(tenant_id, review_id, job_id, content))
            _require(_supplied(markdown_sha256, markdown_bytes))
            _require(all(type(value) is UUID for value in (tenant_id, review_id, job_id)))
            _require(_is_sha256(markdown_sha256))
            _require(_is_int(markdown_bytes, 1, MAX_MARKDOWN_BYTES))
            _require(type(content) is ReviewReportContent)
            checked = revalidate_review_report(content)
            binding = checked.binding
            _require(
                binding.tenant_id == tenant_id
                and binding.review_id == review_id
                and binding.job_id == job_id
            )
            _require(checked.mode is ReportMode.CONTRACT)
            wrapper = review_report_bytes(checked)
            _require(type(wrapper) is bytes and 1 <= len(wrapper) <= MAX_CONTENT_BYTES)
            questions = len(checked.questions)
            findings = len(checked.content.findings)
            unresolved = len(checked.content.unresolved_question_ids)
            _require(1 <= questions <= MAX_QUESTIONS and 0 <= findings <= MAX_FINDINGS)
            _require(0 <= unresolved <= questions)
            values: dict[str, object] = {
                "tenant_id": tenant_id,
                "review_id": review_id,
                "job_id": job_id,
                "content": checked,
                "markdown_sha256": markdown_sha256,
                "markdown_bytes": markdown_bytes,
                "schema_id": SCHEMA,
                "renderer_id": RENDERER,
                "mode": checked.mode.value,
                "wrapper_canonical": wrapper,
                "wrapper_sha256": hashlib.sha256(wrapper).hexdigest(),
                "legacy_sha256": checked.legacy_sha256,
                "review_request_sha256": binding.review_request_sha256,
                "snapshot_sha256": binding.snapshot_sha256,
                "configuration_sha256": binding.configuration_sha256,
                "question_count": questions,
                "finding_count": findings,
                "unresolved_count": unresolved,
            }
            for name, value in values.items():
                object.__setattr__(self, name, value)

        _run(build, InvalidReviewOutputError)

    def __repr__(self) -> str:
        return (
            f"ReviewOutput(review_id={self.review_id}, wrapper_sha256={self.wrapper_sha256!r}, "
            f"questions={self.question_count}, findings={self.finding_count}, "
            f"unresolved={self.unresolved_count})"
        )

    __str__ = __repr__


def _rebuilt_output(value: object) -> ReviewOutput:
    """A supplied ``ReviewOutput`` rebuilt through its constructor (which rebuilds the nested
    content and recomputes every derived field) and required to equal the input."""
    _require(type(value) is ReviewOutput)
    assert isinstance(value, ReviewOutput)
    rebuilt = ReviewOutput(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        job_id=value.job_id,
        content=value.content,
        markdown_sha256=value.markdown_sha256,
        markdown_bytes=value.markdown_bytes,
    )
    _require(rebuilt == value)
    return rebuilt


def revalidated_output(value: object) -> ReviewOutput:
    """``value`` rebuilt as an exact ``ReviewOutput`` or a fresh ``InvalidReviewOutputError``."""
    return _run(lambda: _rebuilt_output(value), InvalidReviewOutputError)


def _utc(value: object) -> datetime:
    _require(type(value) is datetime)
    assert isinstance(value, datetime)
    _require(value.tzinfo is not None and value.utcoffset() is not None)
    return value.astimezone(UTC)


@dataclass(frozen=True, init=False, repr=False)
class StoredReviewOutput:
    """A stored output with its audit fields. ``job_attempt`` and ``created_at`` are audit values
    only: they are never ordered or compared with other timestamps."""

    output: ReviewOutput
    job_attempt: int
    created_at: datetime

    def __init__(
        self,
        *,
        output: ReviewOutput = _MISSING,
        job_attempt: int = _MISSING,
        created_at: datetime = _MISSING,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _supplied(output, job_attempt, created_at))
            checked = _rebuilt_output(output)
            _require(_is_int(job_attempt, 1, MAX_JOB_ATTEMPT))
            object.__setattr__(self, "output", checked)
            object.__setattr__(self, "job_attempt", job_attempt)
            object.__setattr__(self, "created_at", _utc(created_at))

        _run(build, InvalidStoredOutputError)

    def __repr__(self) -> str:
        return f"StoredReviewOutput(output={self.output!r}, job_attempt={self.job_attempt})"

    __str__ = __repr__


def _rebuilt_stored(value: object) -> StoredReviewOutput:
    _require(type(value) is StoredReviewOutput)
    assert isinstance(value, StoredReviewOutput)
    rebuilt = StoredReviewOutput(
        output=value.output, job_attempt=value.job_attempt, created_at=value.created_at
    )
    _require(rebuilt == value)
    return rebuilt


def revalidated_stored(value: object) -> StoredReviewOutput:
    """``value`` rebuilt as an exact ``StoredReviewOutput`` or ``InvalidStoredOutputError``."""
    return _run(lambda: _rebuilt_stored(value), InvalidStoredOutputError)


@dataclass(frozen=True, init=False, repr=False)
class ReviewOutputWrite:
    """The writer's result: the stored row and whether it was an identical replay (G20)."""

    stored: StoredReviewOutput
    replayed: bool

    def __init__(
        self,
        *,
        stored: StoredReviewOutput = _MISSING,
        replayed: bool = _MISSING,
        **unknown: object,
    ) -> None:
        def build() -> None:
            _require(not unknown and _supplied(stored, replayed))
            _require(type(replayed) is bool)
            object.__setattr__(self, "stored", _rebuilt_stored(stored))
            object.__setattr__(self, "replayed", replayed)

        _run(build, InvalidStoredOutputError)

    def __repr__(self) -> str:
        return (
            f"ReviewOutputWrite(review_id={self.stored.output.review_id}, replayed={self.replayed})"
        )

    __str__ = __repr__


class ReviewStatus(StrEnum):
    """The W15 read-time projection (M5g-G3); there is no stored status column."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# --- the strict stored-row decoder ---------------------------------------------------------------

_UUID_COLUMNS = ("tenant_id", "review_id", "job_id")
_DIGEST_COLUMNS = (
    "wrapper_sha256",
    "legacy_sha256",
    "review_request_sha256",
    "snapshot_sha256",
    "configuration_sha256",
    "markdown_sha256",
)
_IDENTIFIER_COLUMNS = ("schema_id", "renderer_id", "mode")
_INTEGER_COLUMNS = (
    "question_count",
    "finding_count",
    "unresolved_count",
    "markdown_bytes",
    "job_attempt",
)


def _decoded(row: object) -> StoredReviewOutput:
    _require(isinstance(row, Mapping))
    assert isinstance(row, Mapping)
    values: dict[str, Any] = {}
    for key in row:
        _require(type(key) is str)
        values[key] = row[key]
    # 1. the closed key set
    _require(set(values) == REVIEW_OUTPUT_COLUMNS)
    # 2. exact column types, bounds and patterns (before any decoding)
    _require(all(type(values[name]) is UUID for name in _UUID_COLUMNS))
    _require(all(type(values[name]) is str for name in _IDENTIFIER_COLUMNS))
    _require(all(len(values[name]) <= 64 for name in _IDENTIFIER_COLUMNS))
    _require(all(_is_sha256(values[name]) for name in _DIGEST_COLUMNS))
    _require(all(type(values[name]) is int for name in _INTEGER_COLUMNS))
    _require(type(values["created_at"]) is datetime)
    wrapper = values["wrapper_canonical"]
    _require(type(wrapper) is str and 1 <= len(wrapper) <= MAX_CONTENT_BYTES)
    _require(_PRINTABLE.fullmatch(wrapper) is not None)
    # 3. strict decode (any M5f encoding, schema or digest error is refused here)
    content = decode_review_report(
        wrapper.encode("ascii"), expected_sha256=values["wrapper_sha256"]
    )
    # 4. rebuild
    output = ReviewOutput(
        tenant_id=values["tenant_id"],
        review_id=values["review_id"],
        job_id=values["job_id"],
        content=content,
        markdown_sha256=values["markdown_sha256"],
        markdown_bytes=values["markdown_bytes"],
    )
    stored = StoredReviewOutput(
        output=output, job_attempt=values["job_attempt"], created_at=values["created_at"]
    )
    # 5. every stored derived column equals the rebuilt value
    _require(output.wrapper_canonical == wrapper.encode("ascii"))
    for name in (
        "schema_id",
        "renderer_id",
        "mode",
        "wrapper_sha256",
        "legacy_sha256",
        "review_request_sha256",
        "snapshot_sha256",
        "configuration_sha256",
        "question_count",
        "finding_count",
        "unresolved_count",
    ):
        _require(getattr(output, name) == values[name])
    return stored


def decode_stored_review_output(row: Mapping[str, object]) -> StoredReviewOutput:
    """Decode one ``review_outputs`` row (M5g-A): closed key set, exact column types, the strict
    M5f decode against the stored wrapper digest, the rebuild, then every derived column. Any
    failure is a fresh ``InvalidStoredOutputError`` with no cause or context."""
    return _run(lambda: _decoded(row), InvalidStoredOutputError)
