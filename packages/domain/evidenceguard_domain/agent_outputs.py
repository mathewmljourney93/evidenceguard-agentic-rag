"""Strict, immutable Verifier and Risk Analyst output schemas and their parser (M5a, ADR-0019).

Shape only: provenance, evidence status, source types and authorization are derived later from
trusted data (M5b). The model never supplies them.

Parsing (``parse_output``) is two-pass:

1. the text is at most 65,536 UTF-8 bytes;
2. a preliminary ``json.loads`` scan rejects duplicate keys, ``NaN``/``Infinity`` and other
   non-finite numbers, trailing text, any top-level value other than an object, nesting deeper
   than 8 and more than 2,000 values; its result is discarded;
3. the same text is validated in Pydantic's strict **JSON mode** against the purpose's schema,
   which accepts JSON strings for enum values and JSON arrays for tuple fields while rejecting
   numeric enums, coercions and unknown fields.

Any failure gives ``None`` (``invalid_output`` at the call boundary). Nothing from the failure is
kept.

Immutability and privacy:

- every collection is a tuple of frozen models, enum members or strings; attribute assignment
  and deletion raise ``InvalidModelValueError``;
- direct construction is strict Python mode: enum members, tuples and nested model instances are
  required (a raw enum string, a list or a nested ``dict`` is rejected); nested instances are
  revalidated, so a ``model_construct``-built value cannot slip in through a parent;
- ``__init__``, ``model_validate``, ``model_validate_json``, ``model_validate_strings`` and
  ``model_copy`` run each whole operation (input traversal, update copying and validation)
  inside one boundary that turns any ordinary failure into a fresh ``InvalidModelValueError``
  with no cause or context; process control propagates unchanged. ``model_validate_strings`` is
  the same strict Python-mode validation as ``model_validate`` (no string coercion);
- ``repr``/``str`` show the type name and counts only, for every output type.

``model_construct`` and ``object.__setattr__`` can still bypass validation. Trusted in-process
code is not a security boundary; domain code never uses those bypasses.
"""

import json
import math
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from types import MappingProxyType
from typing import Annotated, Any, ClassVar, Self, cast
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from evidenceguard_domain.evidence import QuestionId, Severity, Verdict
from evidenceguard_domain.model_calls import (
    MAX_OUTPUT_TEXT_BYTES,
    OUTPUT_SCHEMA_IDS,
    InvalidModelValueError,
    ModelPurpose,
    utf8_size,
)

MAX_JSON_DEPTH = 8
MAX_JSON_VALUES = 2_000
MAX_CLAIMS = 10
MAX_CITATIONS = 8
MAX_FINDINGS = 20
MAX_FINDING_QUESTIONS = 20
MAX_FOLLOW_UPS = 5
CANONICAL_UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _plain_text(value: str) -> str:
    """Reject NUL and lone surrogates; never strip or normalize."""
    if "\x00" in value or utf8_size(value) is None:
        raise ValueError("invalid text")
    return value


def _text(max_length: int) -> StringConstraints:
    return StringConstraints(min_length=1, max_length=max_length)


_Plain = AfterValidator(_plain_text)
ClaimText = Annotated[str, _text(1000), _Plain]
Quote = Annotated[str, _text(1000), _Plain]
Rationale = Annotated[str, _text(2000), _Plain]
Title = Annotated[str, _text(200), _Plain]
Statement = Annotated[str, _text(2000), _Plain]
FollowUp = Annotated[str, _text(500), _Plain]
CanonicalUuid = Annotated[str, StringConstraints(pattern=CANONICAL_UUID_PATTERN)]


def _guarded[T](build: Callable[[], T]) -> T:
    """Run one whole public validation operation (traversal, copying and Pydantic validation)
    and turn any ordinary failure into a fresh ``InvalidModelValueError``, raised after leaving
    the handler so no cause, context or original text is retained. Only ``Exception`` is
    suppressed: process control propagates as the same object. This normalizes errors from
    supported inputs; it is not a sandbox against malicious trusted code (Prompt 172)."""
    built: list[T] = []
    with suppress(Exception):
        built.append(build())
    if not built:
        raise InvalidModelValueError()
    return built[0]


class _OutputModel(BaseModel):
    """Shared strict, frozen, private base of the output types (see the module docstring)."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        revalidate_instances="always",
        hide_input_in_errors=True,
        str_strip_whitespace=False,
    )

    _counted: ClassVar[tuple[str, ...]] = ()
    # Tuple fields of nested output models. In Python mode, Pydantic's strict validation would
    # accept a ``dict`` for a nested model; the Python-mode entry points below require exact
    # instances instead. JSON-mode validation is unaffected (nested objects decode to models).
    _nested: ClassVar[tuple[tuple[str, type["_OutputModel"]], ...]] = ()

    @classmethod
    def _nested_are_instances(cls, data: object) -> bool:
        if isinstance(data, cls):
            return True
        if not isinstance(data, Mapping):
            return True  # left to Pydantic, which rejects it
        for name, model in cls._nested:
            if name in data:
                value = data[name]
                if type(value) is not tuple or not all(type(item) is model for item in value):
                    return False
        return True

    @classmethod
    def _strict_python(cls, obj: Any) -> Self:
        if not cls._nested_are_instances(obj):
            raise InvalidModelValueError()
        return super().model_validate(obj, strict=True)

    def __init__(self, /, **data: Any) -> None:
        def build() -> bool:
            if not type(self)._nested_are_instances(data):
                return False
            super(_OutputModel, self).__init__(**data)
            return True

        built = False
        with suppress(Exception):
            built = build()
        if not built:
            raise InvalidModelValueError()

    # This ``__init__`` only wraps ``BaseModel.__init__`` (the same strict Python-mode
    # validation) and translates its errors. Pydantic 2.14 treats any ``__init__`` without this
    # flag as a custom initializer and calls it with raw input during JSON validation, which
    # would apply Python-mode strictness to JSON values; the flag is the one Pydantic sets on its
    # own ``BaseModel.__init__`` (ADR-0019 records this dependency; tests pin both behaviours).
    __init__.__pydantic_base_init__ = True  # type: ignore[attr-defined]

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> Self:
        if kwargs:
            raise InvalidModelValueError()
        return _guarded(lambda: cls._strict_python(obj))

    @classmethod
    def model_validate_json(cls, json_data: Any, **kwargs: Any) -> Self:
        if kwargs:
            raise InvalidModelValueError()
        return _guarded(
            lambda: super(_OutputModel, cls).model_validate_json(json_data, strict=True)
        )

    @classmethod
    def model_validate_strings(cls, obj: Any, **kwargs: Any) -> Self:
        """Validate ``obj`` exactly as ``model_validate`` does: strict Python mode with exact
        nested instances. Pydantic's string mode would coerce raw strings (for example an enum
        value), which the Python-mode entry points must reject; JSON text uses
        ``model_validate_json`` or ``parse_output`` instead (Prompt 172)."""
        if kwargs:
            raise InvalidModelValueError()
        return _guarded(lambda: cls._strict_python(obj))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Return a validated copy; an update can never produce an unvalidated value. ``deep``
        is accepted for compatibility: values are immutable, so a shallow copy is safe. Reading
        the update mapping happens inside the same error boundary as validation."""

        def build() -> "_OutputModel":
            data = {name: getattr(self, name) for name in type(self).model_fields}
            if update is not None:
                if not isinstance(update, Mapping):
                    raise InvalidModelValueError()
                pairs = list(update.items())
                if not all(type(key) is str for key, _ in pairs):
                    raise InvalidModelValueError()
                data.update(pairs)
            return type(self)(**data)

        return cast(Self, _guarded(build))

    def __setattr__(self, name: str, value: Any) -> None:
        raise InvalidModelValueError()

    def __delattr__(self, name: str) -> None:
        raise InvalidModelValueError()

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        for name in self._counted:
            yield name, len(getattr(self, name))

    def __repr__(self) -> str:
        counts = ", ".join(f"{name}={len(getattr(self, name))}" for name in self._counted)
        return f"{type(self).__name__}({counts})"

    def __str__(self) -> str:
        return self.__repr__()


class QuoteRef(_OutputModel):
    """A cited chunk ID (canonical lowercase hyphenated spelling) and a verbatim quote."""

    chunk_id: CanonicalUuid
    quote: Quote

    @property
    def chunk_uuid(self) -> UUID:
        return UUID(self.chunk_id)


def _distinct_quotes(citations: tuple[QuoteRef, ...]) -> bool:
    return len({(c.chunk_id, c.quote) for c in citations}) == len(citations)


class ClaimOutput(_OutputModel):
    text: ClaimText
    citations: Annotated[tuple[QuoteRef, ...], Field(max_length=MAX_CITATIONS)] = ()

    _counted = ("citations",)
    _nested = (("citations", QuoteRef),)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not _distinct_quotes(self.citations):
            raise ValueError("duplicate quote reference")
        return self


class VerifierOutput(_OutputModel):
    verdict: Verdict
    claims: Annotated[tuple[ClaimOutput, ...], Field(max_length=MAX_CLAIMS)] = ()
    rationale: Rationale

    _counted = ("claims",)
    _nested = (("claims", ClaimOutput),)


class FindingOutput(_OutputModel):
    question_ids: Annotated[
        tuple[QuestionId, ...], Field(min_length=1, max_length=MAX_FINDING_QUESTIONS)
    ]
    title: Title
    severity: Severity
    statement: Statement
    citations: Annotated[tuple[QuoteRef, ...], Field(max_length=MAX_CITATIONS)] = ()
    follow_up_questions: Annotated[tuple[FollowUp, ...], Field(max_length=MAX_FOLLOW_UPS)] = ()

    _counted = ("question_ids", "citations", "follow_up_questions")
    _nested = (("citations", QuoteRef),)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("duplicate question ID")
        if not _distinct_quotes(self.citations):
            raise ValueError("duplicate quote reference")
        return self


class AnalystOutput(_OutputModel):
    findings: Annotated[tuple[FindingOutput, ...], Field(max_length=MAX_FINDINGS)] = ()

    _counted = ("findings",)
    _nested = (("findings", FindingOutput),)


# --- closed schema registry ----------------------------------------------------------------------

OutputType = VerifierOutput | AnalystOutput

OUTPUT_SCHEMAS: Mapping[ModelPurpose, type[VerifierOutput] | type[AnalystOutput]] = (
    MappingProxyType(
        {ModelPurpose.VERIFIER: VerifierOutput, ModelPurpose.RISK_ANALYST: AnalystOutput}
    )
)
SCHEMAS_BY_ID: Mapping[str, type[VerifierOutput] | type[AnalystOutput]] = MappingProxyType(
    {OUTPUT_SCHEMA_IDS[purpose]: schema for purpose, schema in OUTPUT_SCHEMAS.items()}
)


def output_schema_for(purpose: ModelPurpose) -> type[VerifierOutput] | type[AnalystOutput]:
    if type(purpose) is not ModelPurpose:
        raise InvalidModelValueError()
    return OUTPUT_SCHEMAS[purpose]


def revalidated_output(purpose: ModelPurpose, output: object) -> OutputType:
    """Revalidate an output instance of the purpose's exact schema type."""
    schema = output_schema_for(purpose)
    if type(output) is not schema:
        raise InvalidModelValueError()
    return schema.model_validate(output)


# --- parsing -------------------------------------------------------------------------------------


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError("non-finite constant")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


def _within_limits(value: object) -> bool:
    """Iterative walk: at most ``MAX_JSON_DEPTH`` nesting levels and ``MAX_JSON_VALUES`` values
    (the top-level object is depth 1 and counts as one value)."""
    stack: list[tuple[object, int]] = [(value, 1)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_JSON_DEPTH or count > MAX_JSON_VALUES:
            return False
        if type(item) is dict:
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return True


def _scan(text: str) -> bool:
    accepted = False
    with suppress(Exception):  # includes RecursionError for pathological nesting
        decoded = json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
        accepted = type(decoded) is dict and _within_limits(decoded)
    return accepted


def parse_output(purpose: ModelPurpose, text: object) -> OutputType | None:
    """Parse model output for ``purpose`` through the two-pass path, or return ``None``.

    An invalid ``purpose`` is a caller bug and raises ``InvalidModelValueError``; every problem
    with ``text`` gives ``None``. Process control propagates unchanged.
    """
    schema = output_schema_for(purpose)
    size = utf8_size(text)
    if size is None or size > MAX_OUTPUT_TEXT_BYTES:
        return None
    assert isinstance(text, str)
    if not _scan(text):
        return None
    parsed: list[OutputType] = []
    with suppress(Exception):
        parsed.append(schema.model_validate_json(text))
    return parsed[0] if parsed else None
