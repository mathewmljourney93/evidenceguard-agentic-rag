"""Corpus manifest, ground truth and suite validation for retrieval evaluation (M4e, ADR-0017).

Pure code over bytes and validated values: no file system, database or network access. The
worker's test-only orchestrator (``evidenceguard_worker.evaluation``) reads the files and passes
their bytes here.

- ``eg-corpus-v1`` (``corpus.toml``) and ``eg-ground-truth-v1`` (``ground_truth/<tenant>.toml``)
  are parsed with the standard library's ``tomllib``. Unknown keys are rejected at every level
  and every value must have the exact TOML type.
- Evidence is referenced only by the canonical ``tenant/vendor/document@rN#anchor`` string.
  Anchors live in ground truth as exact quotes; documents carry no markers.
- Quote and occurrence rules, reference checks, per-epoch cases and the clean/injected
  single-paragraph relationship are enforced before any database work.

Every failure raises ``EvaluationError`` with a fixed code. Messages never contain document,
quote, question or query text.
"""

import contextlib
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from evidenceguard_domain.evidence import EvidenceStatus, SourceType
from evidenceguard_domain.revisions import (
    MediaType,
    validate_document_key,
    validate_title,
    validate_version_label,
)

CORPUS_FORMAT = "eg-corpus-v1"
GROUND_TRUTH_FORMAT = "eg-ground-truth-v1"
CORPUS_FILE = "corpus.toml"
INJECTED = "injected"
CLEAN = "clean"
VARIANTS = (CLEAN, INJECTED)
INITIAL = "initial"
FINAL = "final"
EPOCHS = (INITIAL, FINAL)

MAX_TENANTS = 2
MAX_VENDORS = 8
MAX_DOCUMENTS = 64
MAX_REVISIONS = 4
MAX_ANCHORS = 256
MAX_QUESTIONS = 64
MAX_CASES = 2
MAX_PARTS = 8
MIN_PARTS = 2
MAX_QUOTE_CHARS = 4000
MAX_CLAIM_CHARS = 500
MAX_CLAIM_REFS = 8
MAX_QUESTION_TEXT = 500
MAX_QUERIES = 5
MAX_QUERY_CHARS = 200
MAX_NAME_CHARS = 200
MAX_SEGMENT_CHARS = 64

MAX_CORPUS_BYTES = 64 * 1024
MAX_GROUND_TRUTH_BYTES = 256 * 1024
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_FILE_SET_BYTES = 4 * 1024 * 1024

_SEGMENT = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_SEGMENT_RE = re.compile(_SEGMENT)
_REVISION_RE = re.compile(rf"({_SEGMENT})/({_SEGMENT})/({_SEGMENT})@r([1-9][0-9]*)")
_ANCHOR_RE = re.compile(rf"({_SEGMENT})/({_SEGMENT})/({_SEGMENT})@r([1-9][0-9]*)#({_SEGMENT})")
_QUESTION_ID_RE = re.compile(r"[A-Z][A-Z0-9]{1,9}-[0-9]{2,3}")
_QUOTE_FORBIDDEN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_EDGE_WHITESPACE = " \t\n"


class EvaluationError(Exception):
    """A fixed-code evaluation failure. ``code`` (and ``detail``, itself a fixed code) are the
    only content; counts, when present, are integers."""

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        counts: Mapping[str, int] | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
            raise ValueError("invalid evaluation error code")
        if detail is not None and not re.fullmatch(r"[a-z][a-z0-9_]*", detail):
            raise ValueError("invalid evaluation error detail")
        self.code = code
        self.detail = detail
        self.counts: dict[str, int] = dict(counts or {})
        super().__init__(code if detail is None else f"{code}:{detail}")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EvaluationError(code)


def _keys(table: object, required: set[str], optional: set[str], code: str) -> dict[str, Any]:
    _require(type(table) is dict, code)
    assert isinstance(table, dict)
    keys = set(table)
    _require(required <= keys and keys <= required | optional, code)
    return table


def _string(value: object, code: str, *, limit: int) -> str:
    _require(type(value) is str and 1 <= len(value) <= limit, code)
    assert isinstance(value, str)
    return value


def _segment(value: object, code: str) -> str:
    _require(
        type(value) is str
        and len(value) <= MAX_SEGMENT_CHARS
        and _SEGMENT_RE.fullmatch(value) is not None,
        code,
    )
    assert isinstance(value, str)
    return value


def _list(value: object, code: str, *, low: int, high: int) -> list[Any]:
    _require(type(value) is list and low <= len(value) <= high, code)
    assert isinstance(value, list)
    return value


def _parse_toml(data: bytes, limit: int, code: str) -> dict[str, Any]:
    _require(type(data) is bytes and len(data) <= limit, code)
    parsed: list[dict[str, Any]] = []
    with contextlib.suppress(UnicodeDecodeError, tomllib.TOMLDecodeError):
        parsed.append(tomllib.loads(data.decode("utf-8")))
    _require(bool(parsed), code)
    return parsed[0]


# --- references ----------------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class RevisionRef:
    """``tenant/vendor/document@rN``."""

    tenant: str
    vendor: str
    document: str
    n: int

    def __str__(self) -> str:
        return f"{self.tenant}/{self.vendor}/{self.document}@r{self.n}"


@dataclass(frozen=True, order=True)
class AnchorRef:
    """``tenant/vendor/document@rN#anchor``, the only accepted evidence reference."""

    revision: RevisionRef
    anchor: str

    def __str__(self) -> str:
        return f"{self.revision}#{self.anchor}"


def parse_revision_ref(value: object, code: str = "invalid_reference") -> RevisionRef:
    _require(type(value) is str, code)
    assert isinstance(value, str)
    match = _REVISION_RE.fullmatch(value)
    _require(match is not None, code)
    assert match is not None
    tenant, vendor, document, n = match.groups()
    _require(all(len(part) <= MAX_SEGMENT_CHARS for part in (tenant, vendor, document)), code)
    return RevisionRef(tenant, vendor, document, int(n))


def parse_anchor_ref(value: object, code: str = "invalid_reference") -> AnchorRef:
    _require(type(value) is str, code)
    assert isinstance(value, str)
    match = _ANCHOR_RE.fullmatch(value)
    _require(match is not None, code)
    assert match is not None
    tenant, vendor, document, n, anchor = match.groups()
    _require(all(len(p) <= MAX_SEGMENT_CHARS for p in (tenant, vendor, document, anchor)), code)
    return AnchorRef(RevisionRef(tenant, vendor, document, int(n)), anchor)


# --- corpus manifest --------------------------------------------------------------------------


@dataclass(frozen=True)
class Revision:
    n: int
    version_label: str | None
    effective_date: date | None


@dataclass(frozen=True)
class Document:
    key: str
    title: str
    source_type: SourceType
    media_type: MediaType
    revisions: tuple[Revision, ...]

    @property
    def latest(self) -> int:
        return self.revisions[-1].n


@dataclass(frozen=True)
class Vendor:
    slug: str
    name: str
    documents: tuple[Document, ...]


@dataclass(frozen=True)
class Tenant:
    slug: str
    vendors: tuple[Vendor, ...]


@dataclass(frozen=True)
class Corpus:
    tenants: tuple[Tenant, ...]
    injected: tuple[RevisionRef, ...]

    def revision_refs(self) -> tuple[RevisionRef, ...]:
        """Every revision, in deterministic order (tenant, vendor, document, n)."""
        return tuple(
            RevisionRef(tenant.slug, vendor.slug, document.key, revision.n)
            for tenant in self.tenants
            for vendor in tenant.vendors
            for document in vendor.documents
            for revision in document.revisions
        )

    def document(self, ref: RevisionRef) -> Document | None:
        for tenant in self.tenants:
            for vendor in tenant.vendors:
                for document in vendor.documents:
                    if (tenant.slug, vendor.slug, document.key) == (
                        ref.tenant,
                        ref.vendor,
                        ref.document,
                    ):
                        return document
        return None

    def vendor_name(self, tenant: str, vendor: str) -> str | None:
        for t in self.tenants:
            for v in t.vendors:
                if (t.slug, v.slug) == (tenant, vendor):
                    return v.name
        return None

    def has_revision(self, ref: RevisionRef) -> bool:
        document = self.document(ref)
        return document is not None and 1 <= ref.n <= document.latest


def document_path(ref: RevisionRef, variant: str = CLEAN) -> str:
    """The relative POSIX path of a revision's file, built from validated segments only."""
    name = f"{ref.document}@r{ref.n}.md"
    if variant == INJECTED:
        return f"variants/injected/{ref.tenant}/{ref.vendor}/{name}"
    return f"documents/{ref.tenant}/{ref.vendor}/{name}"


def ground_truth_path(tenant: str) -> str:
    return f"ground_truth/{tenant}.toml"


def _revision(table: object) -> Revision:
    code = "corpus_invalid"
    t = _keys(table, {"n"}, {"version_label", "effective_date"}, code)
    _require(type(t["n"]) is int and t["n"] >= 1, code)
    label = t.get("version_label")
    if label is not None:
        _require(type(label) is str, code)
        _validated(validate_version_label, label, code)
    effective = t.get("effective_date")
    _require(effective is None or type(effective) is date, code)
    return Revision(t["n"], label, effective)


def _validated(validator: Any, value: object, code: str) -> None:
    failed = False
    try:
        validator(value)
    except ValueError:
        failed = True
    _require(not failed, code)


def _enum[E: (SourceType, MediaType, EvidenceStatus)](kind: type[E], value: object, code: str) -> E:
    _require(type(value) is str, code)
    for member in kind:
        if member.value == value:
            return member
    raise EvaluationError(code)


def _document(table: object) -> Document:
    code = "corpus_invalid"
    t = _keys(table, {"key", "title", "source_type", "media_type", "revisions"}, set(), code)
    _require(type(t["key"]) is str, code)
    _validated(validate_document_key, t["key"], code)
    _require(type(t["title"]) is str, code)
    _validated(validate_title, t["title"], code)
    revisions = tuple(_revision(r) for r in _list(t["revisions"], code, low=1, high=MAX_REVISIONS))
    _require([r.n for r in revisions] == list(range(1, len(revisions) + 1)), code)
    return Document(
        t["key"],
        t["title"],
        _enum(SourceType, t["source_type"], code),
        _enum(MediaType, t["media_type"], code),
        revisions,
    )


def _vendor(table: object) -> Vendor:
    code = "corpus_invalid"
    t = _keys(table, {"slug", "name", "documents"}, set(), code)
    name = _string(t["name"], code, limit=MAX_NAME_CHARS)
    _require(name.strip() != "" and _QUOTE_FORBIDDEN.search(name) is None, code)
    documents = tuple(_document(d) for d in _list(t["documents"], code, low=1, high=MAX_DOCUMENTS))
    _require(len({d.key for d in documents}) == len(documents), code)
    documents = tuple(sorted(documents, key=lambda d: d.key))
    return Vendor(_segment(t["slug"], code), name, documents)


def _tenant(table: object) -> Tenant:
    code = "corpus_invalid"
    t = _keys(table, {"slug", "vendors"}, set(), code)
    vendors = tuple(_vendor(v) for v in _list(t["vendors"], code, low=1, high=MAX_VENDORS))
    _require(len({v.slug for v in vendors}) == len(vendors), code)
    _require(sum(len(v.documents) for v in vendors) <= MAX_DOCUMENTS, code)
    return Tenant(_segment(t["slug"], code), tuple(sorted(vendors, key=lambda v: v.slug)))


def parse_corpus(data: bytes) -> Corpus:
    """Parse and validate ``corpus.toml`` bytes."""
    code = "corpus_invalid"
    t = _keys(_parse_toml(data, MAX_CORPUS_BYTES, code), {"format", "tenants"}, {"variants"}, code)
    _require(t["format"] == CORPUS_FORMAT and type(t["format"]) is str, code)
    tenants = tuple(_tenant(x) for x in _list(t["tenants"], code, low=1, high=MAX_TENANTS))
    _require(len({x.slug for x in tenants}) == len(tenants), code)
    tenants = tuple(sorted(tenants, key=lambda x: x.slug))
    corpus = Corpus(tenants, ())
    injected: tuple[RevisionRef, ...] = ()
    if "variants" in t:
        variants = _keys(t["variants"], {INJECTED}, set(), code)
        table = _keys(variants[INJECTED], {"replaces"}, set(), code)
        refs = tuple(
            parse_revision_ref(r, code)
            for r in _list(table["replaces"], code, low=1, high=MAX_DOCUMENTS)
        )
        _require(len(set(refs)) == len(refs) and all(corpus.has_revision(r) for r in refs), code)
        injected = tuple(sorted(refs))
    return Corpus(tenants, injected)


# --- ground truth ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Part:
    quote: str
    occurrence: int | None


@dataclass(frozen=True)
class Anchor:
    ref: AnchorRef
    quote: str
    occurrence: int | None
    parts: tuple[Part, ...] | None


@dataclass(frozen=True)
class Claim:
    text: str
    refs: tuple[AnchorRef, ...]


@dataclass(frozen=True)
class Case:
    epochs: tuple[str, ...]
    expected_status: EvidenceStatus
    gold: tuple[AnchorRef, ...]
    forbidden: tuple[AnchorRef, ...]
    acceptable_claims: tuple[Claim, ...]
    wrong_claims: tuple[Claim, ...]


@dataclass(frozen=True)
class Question:
    tenant: str
    vendor: str
    id: str
    text: str
    search_queries: tuple[str, ...]
    cases: tuple[Case, ...]

    def case_for(self, epoch: str) -> Case | None:
        for case in self.cases:
            if epoch in case.epochs:
                return case
        return None


@dataclass(frozen=True)
class GroundTruth:
    tenant: str
    anchors: tuple[Anchor, ...]
    questions: tuple[Question, ...]


def validate_quote(value: object, code: str = "anchor_invalid") -> str:
    """The quote rules: an exact string of 1-4,000 code points, strictly UTF-8 encodable, without
    NUL, CR or other C0 controls except TAB and LF, and without leading or trailing whitespace."""
    _require(type(value) is str and 1 <= len(value) <= MAX_QUOTE_CHARS, code)
    assert isinstance(value, str)
    encodable = True
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        encodable = False
    _require(encodable, code)
    _require("\r" not in value and _QUOTE_FORBIDDEN.search(value) is None, code)
    _require(value[0] not in _EDGE_WHITESPACE and value[-1] not in _EDGE_WHITESPACE, code)
    return value


def _occurrence(value: object, code: str) -> int | None:
    if value is None:
        return None
    _require(type(value) is int and value >= 1, code)
    assert isinstance(value, int)
    return value


def _anchor(table: object, tenant: str) -> Anchor:
    code = "anchor_invalid"
    t = _keys(table, {"ref", "quote"}, {"occurrence", "parts"}, code)
    ref = parse_anchor_ref(t["ref"], code)
    _require(ref.revision.tenant == tenant, "foreign_anchor_definition")
    parts: tuple[Part, ...] | None = None
    if "parts" in t:
        items = _list(t["parts"], code, low=MIN_PARTS, high=MAX_PARTS)
        parts = tuple(
            Part(validate_quote(p["quote"]), _occurrence(p.get("occurrence"), code))
            for p in (_keys(item, {"quote"}, {"occurrence"}, code) for item in items)
        )
    return Anchor(ref, validate_quote(t["quote"]), _occurrence(t.get("occurrence"), code), parts)


def _refs(value: object, code: str, *, low: int, high: int) -> tuple[AnchorRef, ...]:
    refs = tuple(parse_anchor_ref(r, code) for r in _list(value, code, low=low, high=high))
    _require(len(set(refs)) == len(refs), code)
    return refs


def _claim(table: object) -> Claim:
    code = "ground_truth_invalid"
    t = _keys(table, {"text", "refs"}, set(), code)
    text = _string(t["text"], code, limit=MAX_CLAIM_CHARS)
    return Claim(text, _refs(t["refs"], code, low=1, high=MAX_CLAIM_REFS))


def _case(table: object) -> Case:
    code = "ground_truth_invalid"
    t = _keys(
        table,
        {"epochs", "expected_status", "gold", "forbidden", "acceptable_claims", "wrong_claims"},
        set(),
        code,
    )
    epochs = _list(t["epochs"], code, low=1, high=len(EPOCHS))
    _require(all(type(e) is str and e in EPOCHS for e in epochs), code)
    _require(len(set(epochs)) == len(epochs), code)
    return Case(
        tuple(e for e in EPOCHS if e in epochs),
        _enum(EvidenceStatus, t["expected_status"], code),
        _refs(t["gold"], code, low=0, high=MAX_ANCHORS),
        _refs(t["forbidden"], code, low=0, high=MAX_ANCHORS),
        tuple(_claim(c) for c in _list(t["acceptable_claims"], code, low=0, high=MAX_ANCHORS)),
        tuple(_claim(c) for c in _list(t["wrong_claims"], code, low=0, high=MAX_ANCHORS)),
    )


def _question(table: object, tenant: str) -> Question:
    code = "ground_truth_invalid"
    t = _keys(table, {"vendor", "id", "text", "search_queries", "cases"}, set(), code)
    _require(type(t["id"]) is str and _QUESTION_ID_RE.fullmatch(t["id"]) is not None, code)
    queries = _list(t["search_queries"], code, low=1, high=MAX_QUERIES)
    for query in queries:
        _string(query, code, limit=MAX_QUERY_CHARS)
        _require(not query.isspace() and "\x00" not in query, code)
    _require(len(set(queries)) == len(queries), code)
    cases = tuple(_case(c) for c in _list(t["cases"], code, low=1, high=MAX_CASES))
    covered = [epoch for case in cases for epoch in case.epochs]
    _require(len(set(covered)) == len(covered), code)  # epochs disjoint across cases
    return Question(
        tenant,
        _segment(t["vendor"], code),
        t["id"],
        _string(t["text"], code, limit=MAX_QUESTION_TEXT),
        tuple(queries),
        cases,
    )


def parse_ground_truth(data: bytes, tenant: str) -> GroundTruth:
    """Parse and validate ``ground_truth/<tenant>.toml`` bytes."""
    code = "ground_truth_invalid"
    t = _keys(
        _parse_toml(data, MAX_GROUND_TRUTH_BYTES, code),
        {"format", "tenant", "anchors", "questions"},
        set(),
        code,
    )
    _require(type(t["format"]) is str and t["format"] == GROUND_TRUTH_FORMAT, code)
    _require(type(t["tenant"]) is str and t["tenant"] == tenant, code)
    anchors = tuple(_anchor(a, tenant) for a in _list(t["anchors"], code, low=0, high=MAX_ANCHORS))
    _require(len({a.ref for a in anchors}) == len(anchors), "duplicate_anchor")
    questions = tuple(
        _question(q, tenant) for q in _list(t["questions"], code, low=0, high=MAX_QUESTIONS)
    )
    keys = [(q.vendor, q.id) for q in questions]
    _require(len(set(keys)) == len(keys), code)
    return GroundTruth(tenant, anchors, questions)


# --- documents and variants --------------------------------------------------------------------


def validate_document_text(data: bytes) -> str:
    """Strict UTF-8, 1 byte to 256 KiB, no NUL and LF-only line endings."""
    code = "corpus_document_invalid"
    _require(type(data) is bytes and 1 <= len(data) <= MAX_DOCUMENT_BYTES, code)
    texts: list[str] = []
    with contextlib.suppress(UnicodeDecodeError):
        texts.append(data.decode("utf-8", errors="strict"))
    _require(bool(texts), code)
    text = texts[0]
    _require("\x00" not in text and "\r" not in text and text.strip() != "", code)
    return text


def check_injected_variant(clean: str, injected: str) -> None:
    """The injected text equals the clean text with exactly one paragraph inserted: splitting
    both on blank lines (``"\\n\\n"``), the injected paragraphs are the clean ones with one
    additional nonblank paragraph, and joining them reproduces both texts exactly."""
    code = "corpus_variant_invalid"
    before, after = clean.split("\n\n"), injected.split("\n\n")
    _require(len(after) == len(before) + 1, code)
    for index, paragraph in enumerate(after):
        if after[:index] + after[index + 1 :] == before:
            _require(paragraph.strip() != "" and "\n\n" not in paragraph, code)
            return
    raise EvaluationError(code)


# --- the validated suite ------------------------------------------------------------------------


@dataclass(frozen=True)
class Suite:
    """One schema-validated variant: corpus, ground truth per tenant, revision texts, the
    effective file set (relative paths and bytes, for the corpus digest), every anchor by
    reference, and ``source_files``: every file validation used (the effective set plus, for the
    injected variant, each replaced clean document), from which the suite can be rebuilt.

    A ``Suite`` from ``build_suite`` has **not** had its anchors located or mapped; the complete
    validation is ``anchors.validate_suite``, and the worker entry points re-derive it from
    ``source_files`` (``anchors.revalidate``) rather than trusting a supplied value."""

    variant: str
    corpus: Corpus
    ground_truth: tuple[GroundTruth, ...]
    texts: Mapping[RevisionRef, str]
    effective_files: tuple[tuple[str, bytes], ...]
    anchors: Mapping[AnchorRef, Anchor]
    source_files: tuple[tuple[str, bytes], ...]

    def questions(self) -> tuple[Question, ...]:
        return tuple(q for gt in self.ground_truth for q in gt.questions)


def expected_paths(corpus: Corpus) -> frozenset[str]:
    """Every file the corpus root may contain under ``documents/``, ``variants/`` and
    ``ground_truth/``; anything else is unexpected."""
    paths = {document_path(ref) for ref in corpus.revision_refs()}
    paths |= {document_path(ref, INJECTED) for ref in corpus.injected}
    paths |= {ground_truth_path(t.slug) for t in corpus.tenants}
    return frozenset(paths)


def effective_paths(corpus: Corpus, variant: str) -> tuple[str, ...]:
    """The selected variant's file set: ``corpus.toml``, every ground-truth file and the
    variant's documents (replaced documents under their ``variants/injected`` paths)."""
    _require(variant in VARIANTS, "corpus_variant_invalid")
    _require(variant == CLEAN or bool(corpus.injected), "corpus_variant_invalid")
    paths = [CORPUS_FILE] + [ground_truth_path(t.slug) for t in corpus.tenants]
    for ref in corpus.revision_refs():
        replaced = variant == INJECTED and ref in corpus.injected
        paths.append(document_path(ref, INJECTED if replaced else CLEAN))
    return tuple(paths)


def validation_paths(corpus: Corpus, variant: str) -> tuple[str, ...]:
    """Every file needed to validate ``variant``: the effective set, then, for the injected
    variant, the clean document each replacement is compared with."""
    effective = effective_paths(corpus, variant)
    if variant != INJECTED:
        return effective
    return effective + tuple(document_path(ref) for ref in sorted(corpus.injected))


def file_limit(path: str) -> int:
    """The per-file byte bound for a corpus-relative path."""
    if path == CORPUS_FILE:
        return MAX_CORPUS_BYTES
    if path.startswith("ground_truth/"):
        return MAX_GROUND_TRUTH_BYTES
    return MAX_DOCUMENT_BYTES


def _check_reference(
    question: Question, case: Case, suite_anchors: Mapping[AnchorRef, Anchor], corpus: Corpus
) -> None:
    gold_set = set(case.gold)
    _require(not gold_set & set(case.forbidden), "gold_forbidden_conflict")
    for ref in case.forbidden:
        _require(ref in suite_anchors, "unknown_reference")
    own = [*case.gold, *(r for c in (*case.acceptable_claims, *case.wrong_claims) for r in c.refs)]
    for ref in own:
        _require(ref in suite_anchors, "unknown_reference")
        _require(
            (ref.revision.tenant, ref.revision.vendor) == (question.tenant, question.vendor),
            "foreign_gold_reference",
        )
    for ref in case.gold:
        document = corpus.document(ref.revision)
        assert document is not None
        for epoch in case.epochs:
            eligible = 1 if epoch == INITIAL else document.latest
            _require(ref.revision.n == eligible, "gold_not_eligible_in_epoch")


def build_suite(variant: str, files: Mapping[str, bytes]) -> Suite:
    """Validate one variant from the bytes of every file the reader found (relative path →
    bytes). Raises ``EvaluationError`` before any database work."""
    _require(CORPUS_FILE in files, "corpus_invalid")
    corpus = parse_corpus(files[CORPUS_FILE])
    allowed = expected_paths(corpus) | {CORPUS_FILE}
    _require(set(files) <= allowed, "corpus_unexpected_file")
    effective = effective_paths(corpus, variant)
    _require(all(path in files for path in effective), "corpus_file_missing")
    _require(sum(len(files[p]) for p in effective) <= MAX_FILE_SET_BYTES, "corpus_too_large")

    texts: dict[RevisionRef, str] = {}
    for ref in corpus.revision_refs():
        clean = validate_document_text(files[document_path(ref)])
        if variant == INJECTED and ref in corpus.injected:
            injected_path = document_path(ref, INJECTED)
            _require(injected_path in files, "corpus_file_missing")
            injected = validate_document_text(files[injected_path])
            check_injected_variant(clean, injected)
            texts[ref] = injected
        else:
            texts[ref] = clean

    ground_truth = tuple(
        parse_ground_truth(files[ground_truth_path(t.slug)], t.slug) for t in corpus.tenants
    )
    anchors: dict[AnchorRef, Anchor] = {}
    for gt in ground_truth:
        for anchor in gt.anchors:
            _require(corpus.has_revision(anchor.ref.revision), "unknown_reference")
            anchors[anchor.ref] = anchor
    for gt in ground_truth:
        for question in gt.questions:
            _require(
                corpus.vendor_name(question.tenant, question.vendor) is not None,
                "ground_truth_invalid",
            )
            for case in question.cases:
                _check_reference(question, case, anchors, corpus)
    return Suite(
        variant,
        corpus,
        ground_truth,
        texts,
        tuple((path, files[path]) for path in effective),
        anchors,
        tuple((path, files[path]) for path in validation_paths(corpus, variant)),
    )


def eligible_revision(document: Document, epoch: str) -> int:
    """``r1`` for ``initial``; the highest revision for ``final``."""
    return 1 if epoch == INITIAL else document.latest


def group_keys(suite: Suite) -> tuple[tuple[str, str, str], ...]:
    """Every evaluated ``(tenant, vendor, epoch)``: tenant and vendor pairs with questions, and
    the epochs their cases cover, sorted."""
    keys = {
        (q.tenant, q.vendor, epoch)
        for q in suite.questions()
        for case in q.cases
        for epoch in case.epochs
    }
    return tuple(sorted(keys, key=lambda k: (k[0], k[1], EPOCHS.index(k[2]))))


def vendors_with_questions(suite: Suite) -> tuple[tuple[str, str], ...]:
    return tuple(sorted({(q.tenant, q.vendor) for q in suite.questions()}))
