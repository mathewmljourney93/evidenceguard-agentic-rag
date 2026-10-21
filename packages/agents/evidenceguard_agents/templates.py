"""Review templates: values, parsing and pinned packaged loading (M5c-B1, C, C1; ADR-0021).

A template is one packaged TOML file (``eg-review-template-v1``), UTF-8 without BOM, at most
65,536 bytes, parsed with ``tomllib`` after a strict UTF-8 decode; unknown keys are rejected at
every level and line endings are not normalized. ``parse_template`` is pure; the reference digest
it returns is the SHA-256 of the exact bytes it was given, nothing more. A directly constructed
``ReviewTemplate`` (or one parsed from other bytes) can carry any plausible digest, so it never
proves packaged origin: trusted production and reload paths use ``load_pinned_template`` only,
which reads the registered packaged file with a bounded read, checks its pinned digest and
compares the complete loaded reference with the review's pinned reference.

Published template files are immutable: a change is a new version with a new file and pinned
digest, and earlier versions stay packaged. Nothing here reads the evaluation ground truth, the
environment, a caller-supplied path or the network, and nothing logs. Errors are the fixed
``artifact_errors`` errors; process control propagates as the same object.
"""

import hashlib
import tomllib
from dataclasses import dataclass
from importlib.resources import files

from evidenceguard_agents.artifact_errors import (
    InvalidAgentArgumentError,
    InvalidAgentValueError,
    InvalidTemplateError,
    TemplateIntegrityError,
    UnknownTemplateError,
    require,
    run_guarded,
)
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.model_calls import is_question_id, utf8_size

TEMPLATE_FORMAT = "eg-review-template-v1"
MAX_TEMPLATE_BYTES = 65_536
MAX_TEMPLATE_VERSION = 999
MAX_TEMPLATE_ID_CHARS = 32
MAX_TITLE_CHARS = 200
MAX_QUESTIONS = 100
MAX_QUESTION_TEXT_CHARS = 500
MAX_QUERIES = 5
MAX_QUERY_CHARS = 200

_PACKAGE = "evidenceguard_agents"
_UTF8_BOM = b"\xef\xbb\xbf"
_ID_START = frozenset("abcdefghijklmnopqrstuvwxyz")
_ID_REST = _ID_START | frozenset("0123456789_")
_HEX = frozenset("0123456789abcdef")
_TOP_KEYS = frozenset({"format", "template_id", "version", "title", "questions"})
_QUESTION_KEYS = frozenset({"id", "text", "search_queries", "requires_documentary_support"})

# (template_id, version) -> (fixed relative resource name, pinned SHA-256 of the file bytes)
_REGISTRY: dict[tuple[str, int], tuple[tuple[str, ...], str]] = {
    ("vendor_security_review", 1): (
        ("data", "templates", "vendor_security_review_v1.toml"),
        "26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a",
    ),
}


# --- small checks ---------------------------------------------------------------------------------


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _is_identifier(value: object) -> bool:
    """``^[a-z][a-z0-9_]{0,31}$``, checked without a regular-expression import."""
    return (
        type(value) is str
        and 1 <= len(value) <= MAX_TEMPLATE_ID_CHARS
        and value[0] in _ID_START
        and all(character in _ID_REST for character in value)
    )


def _is_sha256(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


def _is_template_string(value: object, high: int) -> bool:
    """The template-string rule: an exact ``str`` of 1-``high`` code points, strictly UTF-8
    encodable, without NUL and equal to its own ``str.strip()`` (so never blank)."""
    return (
        type(value) is str
        and 1 <= len(value) <= high
        and "\x00" not in value
        and value == value.strip()
        and utf8_size(value) is not None
    )


def _question(
    question_id: object, text: object, queries: object, documentary: object
) -> EvidenceQuestion:
    """Build an ``EvidenceQuestion`` under the template-question rule. The built value must
    equal the supplied fields exactly, so the M1 whitespace stripping can never alter them."""
    require(type(question_id) is str and is_question_id(question_id))
    require(_is_template_string(text, MAX_QUESTION_TEXT_CHARS))
    require(type(queries) is tuple and 1 <= len(queries) <= MAX_QUERIES)
    assert isinstance(queries, tuple)
    require(all(_is_template_string(query, MAX_QUERY_CHARS) for query in queries))
    require(len(set(queries)) == len(queries))
    require(type(documentary) is bool)
    built = EvidenceQuestion.model_validate(
        {
            "question_id": question_id,
            "text": text,
            "search_queries": queries,
            "requires_documentary_support": documentary,
        }
    )
    require(
        type(built.question_id) is str
        and built.question_id == question_id
        and type(built.text) is str
        and built.text == text
        and type(built.search_queries) is tuple
        and built.search_queries == queries
        and built.requires_documentary_support is documentary
    )
    return built


def _template_question(value: object) -> EvidenceQuestion:
    """Rebuild a supplied ``EvidenceQuestion`` (including one built by bypassing validation)
    under the template-question rule."""
    require(type(value) is EvidenceQuestion)
    assert isinstance(value, EvidenceQuestion)
    return _question(
        value.question_id, value.text, value.search_queries, value.requires_documentary_support
    )


def _read_packaged(parts: tuple[str, ...], limit: int) -> bytes:
    """Read a packaged resource by its fixed relative name with a bounded read. Each request is
    bounded by the remaining allowance (``limit + 1`` minus the bytes already received) and short
    reads are continued, so under the reader contract no more than ``limit + 1`` bytes are
    received; more than ``limit`` bytes is rejected. The file is never read whole and then
    measured."""
    resource = files(_PACKAGE).joinpath(*parts)
    chunks: list[bytes] = []
    total = 0
    with resource.open("rb") as handle:
        while total <= limit:
            chunk = handle.read(limit + 1 - total)
            require(type(chunk) is bytes)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    require(total <= limit)
    return b"".join(chunks)


# --- values ---------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class TemplateRef:
    """A template identifier, version and SHA-256. Shape only: it does not prove that a
    packaged file has this digest."""

    template_id: str
    version: int
    sha256: str

    def __init__(self, *, template_id: str, version: int, sha256: str, **unknown: object) -> None:
        def build() -> None:
            require(not unknown and _is_identifier(template_id))
            require(_is_int(version, 1, MAX_TEMPLATE_VERSION) and _is_sha256(sha256))
            object.__setattr__(self, "template_id", template_id)
            object.__setattr__(self, "version", version)
            object.__setattr__(self, "sha256", sha256)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"TemplateRef(template_id={self.template_id!r}, version={self.version}, "
            f"sha256={self.sha256!r})"
        )

    __str__ = __repr__


def _rebuilt_ref(value: object) -> TemplateRef:
    require(type(value) is TemplateRef)
    assert isinstance(value, TemplateRef)
    return TemplateRef(template_id=value.template_id, version=value.version, sha256=value.sha256)


@dataclass(frozen=True, init=False, repr=False)
class ReviewTemplate:
    """A validated review template: its reference, title and 1-100 questions in file order."""

    ref: TemplateRef
    title: str
    questions: tuple[EvidenceQuestion, ...]

    def __init__(
        self,
        *,
        ref: TemplateRef,
        title: str,
        questions: tuple[EvidenceQuestion, ...],
        **unknown: object,
    ) -> None:
        def build() -> None:
            require(not unknown)
            checked_ref = _rebuilt_ref(ref)
            require(_is_template_string(title, MAX_TITLE_CHARS))
            require(type(questions) is tuple and 1 <= len(questions) <= MAX_QUESTIONS)
            checked = tuple(_template_question(question) for question in questions)
            require(len({question.question_id for question in checked}) == len(checked))
            object.__setattr__(self, "ref", checked_ref)
            object.__setattr__(self, "title", title)
            object.__setattr__(self, "questions", checked)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"ReviewTemplate(template_id={self.ref.template_id!r}, "
            f"version={self.ref.version}, questions={len(self.questions)})"
        )

    __str__ = __repr__


def _rebuilt_template(value: object) -> ReviewTemplate:
    require(type(value) is ReviewTemplate)
    assert isinstance(value, ReviewTemplate)
    return ReviewTemplate(ref=value.ref, title=value.title, questions=value.questions)


# --- parsing and loading --------------------------------------------------------------------------


def _parse(data: object) -> ReviewTemplate:
    require(type(data) is bytes)
    assert isinstance(data, bytes)
    require(len(data) <= MAX_TEMPLATE_BYTES and not data.startswith(_UTF8_BOM))
    document = tomllib.loads(data.decode("utf-8", errors="strict"))
    require(set(document) == _TOP_KEYS)
    require(type(document["format"]) is str and document["format"] == TEMPLATE_FORMAT)
    entries = document["questions"]
    require(type(entries) is list and 1 <= len(entries) <= MAX_QUESTIONS)
    questions: list[EvidenceQuestion] = []
    for entry in entries:
        require(type(entry) is dict and set(entry) == _QUESTION_KEYS)
        queries = entry["search_queries"]
        require(type(queries) is list)
        questions.append(
            _question(
                entry["id"],
                entry["text"],
                tuple(queries),
                entry["requires_documentary_support"],
            )
        )
    ref = TemplateRef(
        template_id=document["template_id"],
        version=document["version"],
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return ReviewTemplate(ref=ref, title=document["title"], questions=tuple(questions))


def parse_template(data: bytes) -> ReviewTemplate:
    """Parse and validate template bytes. The reference digest is the SHA-256 of exactly
    ``data``. Any failure, including a non-``bytes`` argument, is ``InvalidTemplateError``."""
    return run_guarded(lambda: _parse(data), InvalidTemplateError)


def _load(template_id: object, version: object) -> ReviewTemplate:
    if not (_is_identifier(template_id) and _is_int(version, 1, MAX_TEMPLATE_VERSION)):
        raise InvalidAgentArgumentError
    assert isinstance(template_id, str) and isinstance(version, int)
    entry = _REGISTRY.get((template_id, version))
    if entry is None:
        raise UnknownTemplateError
    parts, pinned = entry
    data = _read_packaged(parts, MAX_TEMPLATE_BYTES)
    require(hashlib.sha256(data).hexdigest() == pinned)
    template = _parse(data)
    require(template.ref == TemplateRef(template_id=template_id, version=version, sha256=pinned))
    return template


def load_template(template_id: str, version: int) -> ReviewTemplate:
    """Load a registered packaged template and check its pinned digest. Wrong argument types or
    shapes are ``InvalidAgentArgumentError``; an unregistered pair is ``UnknownTemplateError``;
    a missing, unreadable, oversize, altered or invalid resource is ``TemplateIntegrityError``."""
    return run_guarded(
        lambda: _load(template_id, version),
        TemplateIntegrityError,
        keep=(InvalidAgentArgumentError, UnknownTemplateError),
    )


def load_pinned_template(ref: TemplateRef) -> ReviewTemplate:
    """The trusted production and reload path: load the packaged template named by ``ref`` and
    require the complete loaded reference (ID, version and digest) to equal ``ref``."""

    def build() -> ReviewTemplate:
        checked = run_guarded(lambda: _rebuilt_ref(ref), InvalidAgentArgumentError)
        template = load_template(checked.template_id, checked.version)
        require(template.ref == checked)
        return template

    return run_guarded(
        build,
        TemplateIntegrityError,
        keep=(InvalidAgentArgumentError, UnknownTemplateError, TemplateIntegrityError),
    )
