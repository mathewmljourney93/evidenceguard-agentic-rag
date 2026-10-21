"""Review templates, pinned packaged loading and the deterministic Planner
(``evidenceguard_agents.templates`` and ``planner``, M5c-B1, C, C1, C2 and D, ADR-0021), without a
database or network.

The packaged template's digest is a literal computed independently with ``sha256sum``; the
expected questions are the accepted M5c-C2 table written by hand. Only these tests read the
evaluation ground truth, to check that the template copies no answer-bearing label from it.
"""

import dataclasses
import hashlib
import logging
import socket
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from evidenceguard_agents import templates
from evidenceguard_agents.artifact_errors import (
    InvalidAgentArgumentError,
    InvalidAgentValueError,
    InvalidTemplateError,
    TemplateIntegrityError,
    UnknownTemplateError,
)
from evidenceguard_agents.planner import PlannedQuestion, plan_review
from evidenceguard_agents.templates import (
    ReviewTemplate,
    TemplateRef,
    load_pinned_template,
    load_template,
    parse_template,
)
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.retrieval import RetrievalRequest

TEMPLATE_SHA256 = "26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a"
PINNED_REF = TemplateRef(template_id="vendor_security_review", version=1, sha256=TEMPLATE_SHA256)
GROUND_TRUTH = Path(__file__).resolve().parents[1] / "sample_data" / "ground_truth"

# The accepted M5c-C2 table: ID, text, queries in order, documentary flag.
EXPECTED = [
    (
        "RET-01",
        "How long is customer data retained after termination?",
        ("customer data retention after contract termination", "data deletion after termination"),
        False,
    ),
    (
        "ENC-01",
        "Is customer data encrypted at rest?",
        ("customer data encryption at rest", "stored data encryption"),
        False,
    ),
    (
        "CMP-01",
        "Does the vendor hold an ISO 27001 certification?",
        ("ISO 27001 certificate", "information security management certification"),
        True,
    ),
    (
        "CMP-02",
        "Is the vendor HIPAA compliant?",
        ("HIPAA compliance status", "protected health information safeguards"),
        True,
    ),
    (
        "INC-01",
        "What is the breach-notification timeframe?",
        ("security breach notification period", "incident notification to customers"),
        False,
    ),
    (
        "BCP-01",
        "What is the recovery time objective for production?",
        ("recovery time objective production", "disaster recovery targets"),
        False,
    ),
    (
        "SUB-01",
        "Which subprocessors are used, and in which regions?",
        ("subprocessor list and regions", "third-party subprocessors data location"),
        False,
    ),
    (
        "SOC-01",
        "Is there an independent SOC 2 report?",
        ("SOC 2 report", "independent service auditor report"),
        True,
    ),
]


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


# --- helpers -------------------------------------------------------------------------------------


def packaged_bytes() -> bytes:
    resource = files("evidenceguard_agents").joinpath(
        "data", "templates", "vendor_security_review_v1.toml"
    )
    return resource.read_bytes()


def toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def question_table(
    question_id: str = "ENC-01",
    text: str = "Is customer data encrypted at rest?",
    queries: tuple[str, ...] = ("customer data encryption at rest",),
    documentary: str | None = "false",
    extra: str = "",
) -> str:
    lines = [
        "[[questions]]",
        f"id = {toml_string(question_id)}",
        f"text = {toml_string(text)}",
        "search_queries = [" + ", ".join(toml_string(q) for q in queries) + "]",
    ]
    if documentary is not None:
        lines.append(f"requires_documentary_support = {documentary}")
    if extra:
        lines.append(extra)
    return "\n".join(lines) + "\n"


def document(
    *questions: str,
    template_id: str = '"sample_template"',
    version: str = "3",
    title: str = '"Sample review"',
    form: str = '"eg-review-template-v1"',
    extra: str = "",
) -> bytes:
    head = (
        f"format = {form}\ntemplate_id = {template_id}\nversion = {version}\ntitle = {title}\n"
        + extra
    )
    body = "\n".join(questions or (question_table(),))
    return (head + "\n" + body).encode("utf-8")


class Stop(KeyboardInterrupt):
    pass


LIMIT_PLUS_ONE = 65_537


class FakeHandle:
    def __init__(self, data: bytes, requests: list[int], step: int | None) -> None:
        self.data, self.requests, self.step, self.offset = data, requests, step, 0

    def __enter__(self) -> "FakeHandle":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        assert size >= 0  # never an unbounded read
        # a request never exceeds the limit plus one byte minus what has already been read
        assert self.offset + size <= LIMIT_PLUS_ONE
        self.requests.append(size)
        count = size if self.step is None else min(size, self.step)
        chunk = self.data[self.offset : self.offset + count]
        self.offset += len(chunk)
        return chunk


class FakeResource:
    def __init__(
        self,
        data: bytes | None,
        failure: BaseException | None,
        requests: list[int],
        step: int | None,
    ) -> None:
        self.data, self.failure, self.requests, self.step = data, failure, requests, step
        self.names: list[tuple[str, ...]] = []
        self.handles: list[FakeHandle] = []

    def joinpath(self, *parts: str) -> "FakeResource":
        self.names.append(parts)
        return self

    def open(self, mode: str) -> FakeHandle:
        assert mode == "rb"
        if self.failure is not None:
            raise self.failure
        assert self.data is not None
        self.handles.append(FakeHandle(self.data, self.requests, self.step))
        return self.handles[-1]


def fake_resource(
    monkeypatch: pytest.MonkeyPatch,
    data: bytes | None = None,
    *,
    failure: BaseException | None = None,
    step: int | None = None,
) -> FakeResource:
    resource = FakeResource(data, failure, [], step)
    monkeypatch.setattr(templates, "files", lambda package: resource)
    return resource


def assert_fixed(error: BaseException, code: str) -> None:
    assert str(error) == code and error.args == (code,)
    assert error.__cause__ is None and error.__context__ is None


# --- the packaged template -----------------------------------------------------------------------


def test_packaged_template_has_the_pinned_digest_and_the_accepted_table() -> None:
    data = packaged_bytes()
    assert hashlib.sha256(data).hexdigest() == TEMPLATE_SHA256
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    template = load_template("vendor_security_review", 1)
    assert template.ref == PINNED_REF
    assert template.title == "Vendor security review"
    assert [
        (q.question_id, q.text, q.search_queries, q.requires_documentary_support)
        for q in template.questions
    ] == EXPECTED
    assert load_pinned_template(PINNED_REF) == template
    assert parse_template(data) == template


def test_template_shares_only_question_ids_and_texts_with_the_ground_truth() -> None:
    template_text = packaged_bytes().decode("utf-8")
    shared: dict[str, str] = {}
    queries: set[str] = set()
    labels: set[str] = set()

    def leaves(node: Any) -> list[str]:
        """Answer-bearing strings: anchors, gold and forbidden lists, acceptable claims and
        quotes. Epoch names and expected-status enum values are not answer text (a status
        value such as ``documentary_support`` also names the template's own flag)."""
        if isinstance(node, str):
            return [node]
        if isinstance(node, dict):
            return [
                s
                for key, item in node.items()
                if key not in {"epochs", "expected_status"}
                for s in leaves(item)
            ]
        if isinstance(node, list):
            return [s for item in node for s in leaves(item)]
        return []

    for path in sorted(GROUND_TRUTH.glob("*.toml")):
        truth = tomllib.loads(path.read_text(encoding="utf-8"))
        labels.update(leaves(truth.get("anchors", [])))
        for question in truth["questions"]:
            shared[question["id"]] = question["text"]
            queries.update(question["search_queries"])
            labels.update(leaves(question.get("cases", [])))
    template = load_template("vendor_security_review", 1)
    for question in template.questions:
        assert shared[question.question_id] == question.text
        assert not set(question.search_queries) & queries
    assert labels
    assert not [label for label in labels if label in template_text]


# --- parsing -------------------------------------------------------------------------------------


def test_parse_template_digest_covers_the_exact_bytes() -> None:
    data = document()
    template = parse_template(data)
    assert template.ref == TemplateRef(
        template_id="sample_template", version=3, sha256=hashlib.sha256(data).hexdigest()
    )
    for variant in (data.replace(b"\n", b"\r\n"), data + b"\n", data.rstrip(b"\n")):
        parsed = parse_template(variant)
        assert parsed.ref.sha256 == hashlib.sha256(variant).hexdigest() != template.ref.sha256
        assert parsed.questions == template.questions


def test_file_order_is_preserved() -> None:
    first = question_table("ZZZ-99", "Last by ID?", ("z",))
    second = question_table("AAA-01", "First by ID?", ("a",))
    template = parse_template(document(first, second))
    assert [q.question_id for q in template.questions] == ["ZZZ-99", "AAA-01"]


def padded_to(size: int) -> bytes:
    data = document()
    return data + b"#" + b"x" * (size - len(data) - 2) + b"\n"


def test_size_limit_is_inclusive() -> None:
    assert len(padded_to(65_536)) == 65_536
    assert parse_template(padded_to(65_536))
    with pytest.raises(InvalidTemplateError):
        parse_template(padded_to(65_537))


def test_question_count_limit() -> None:
    hundred = [question_table(f"QQ-{i:03d}", f"Question {i}?", (f"query {i}",)) for i in range(100)]
    assert len(parse_template(document(*hundred)).questions) == 100
    extra = question_table("QQ-100", "Question 100?", ("query 100",))
    with pytest.raises(InvalidTemplateError):
        parse_template(document(*hundred, extra))


INVALID_DOCUMENTS = [
    b"\xef\xbb\xbf" + document(),
    document().replace(b"Sample review", b"Sample \xff review"),
    b"",
    b"not toml = = 1",
    document(form='"eg-review-template-v2"'),
    document(form="1"),
    document(extra="owner = 'someone'\n"),
    document(template_id='"Sample"'),
    document(template_id='"9sample"'),
    document(template_id='"' + "a" * 33 + '"'),
    document(version="0"),
    document(version="1000"),
    document(version="true"),
    document(version="1.0"),
    document(version='"1"'),
    document(title='""'),
    document(title='" padded"'),
    document(title='"padded "'),
    document(title='"' + "t" * 201 + '"'),
    document(title='"NUL \\u0000 inside"'),
    document(question_table(extra='notes = "x"')),
    document(question_table(documentary=None)),
    document(question_table(documentary='"false"')),
    document(question_table(question_id="enc-01")),
    document(question_table(text="")),
    document(question_table(text=" Leading space?")),
    document(question_table(text="Tab at end?\t")),
    document(question_table(text="q" * 501)),
    document(question_table(queries=())),
    document(question_table(queries=("one", "two", "three", "four", "five", "six"))),
    document(question_table(queries=("same", "same"))),
    document(question_table(queries=("trailing ",))),
    document(question_table(queries=("q" * 201,))),
    document(question_table(), question_table()),
    document(form='"eg-review-template-v1"', extra="").replace(b"[[questions]]", b"[questions]"),
    document().replace(b'search_queries = ["', b'search_queries = "').replace(b'"]', b'"'),
]


@pytest.mark.parametrize("data", INVALID_DOCUMENTS, ids=lambda _: "document")
def test_invalid_documents(data: bytes) -> None:
    with pytest.raises(InvalidTemplateError) as caught:
        parse_template(data)
    assert_fixed(caught.value, "invalid_review_template")


def test_bounds_are_inclusive_at_the_upper_limits() -> None:
    data = document(
        question_table(text="q" * 500, queries=tuple(f"{i}" * 200 for i in range(5))),
        title='"' + "t" * 200 + '"',
        template_id='"' + "a" * 32 + '"',
        version="999",
    )
    template = parse_template(data)
    assert template.ref.version == 999 and len(template.title) == 200


@pytest.mark.parametrize("data", ["text", bytearray(document()), memoryview(document()), None])
def test_parse_template_requires_bytes(data: Any) -> None:
    with pytest.raises(InvalidTemplateError):
        parse_template(data)


# --- values --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"template_id": "Bad", "version": 1, "sha256": "a" * 64},
        {"template_id": "ok", "version": 0, "sha256": "a" * 64},
        {"template_id": "ok", "version": True, "sha256": "a" * 64},
        {"template_id": "ok", "version": 1, "sha256": "A" * 64},
        {"template_id": "ok", "version": 1, "sha256": "a" * 63},
        {"template_id": "ok", "version": 1, "sha256": "a" * 64, "extra": 1},
    ],
)
def test_template_ref_bounds(kwargs: dict[str, Any]) -> None:
    with pytest.raises(InvalidAgentValueError) as caught:
        TemplateRef(**kwargs)
    assert_fixed(caught.value, "invalid_agent_value")


def question(**changes: Any) -> EvidenceQuestion:
    values: dict[str, Any] = {
        "question_id": "ENC-01",
        "text": "Is customer data encrypted at rest?",
        "search_queries": ("customer data encryption at rest",),
        "requires_documentary_support": False,
    }
    values.update(changes)
    return EvidenceQuestion.model_construct(**values)


def test_review_template_construction_and_representation() -> None:
    template = ReviewTemplate(ref=PINNED_REF, title="Title", questions=(question(),))
    assert repr(template) == str(template)
    assert repr(template) == (
        "ReviewTemplate(template_id='vendor_security_review', version=1, questions=1)"
    )
    assert "Title" not in repr(template) and "encrypted" not in repr(template)
    assert repr(PINNED_REF) == (
        f"TemplateRef(template_id='vendor_security_review', version=1, sha256='{TEMPLATE_SHA256}')"
    )
    assert dataclasses.replace(template, title="Other").title == "Other"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": "Title \ud800"},
        {"title": "NUL \x00"},
        {"title": " Title"},
        {"title": ""},
        {"questions": ()},
        {"questions": [question()]},
        {"questions": (question(), question())},
        {"questions": (question(text="Lone \ud800?"),)},
        {"questions": (question(text="NUL \x00?"),)},
        {"questions": (question(text=" padded"),)},
        {"questions": (question(search_queries=["a list"]),)},
        {"questions": (question(search_queries=("dup", "dup")),)},
        {"questions": (question(search_queries=("tail\n",)),)},
        {"questions": (question(requires_documentary_support=1),)},
        {"questions": (question(question_id="bad"),)},
        {"questions": ("ENC-01",)},
        {"ref": ("vendor_security_review", 1, TEMPLATE_SHA256)},
        {"extra": 1},
    ],
)
def test_review_template_rejects_invalid_and_bypass_built_values(kwargs: dict[str, Any]) -> None:
    values: dict[str, Any] = {"ref": PINNED_REF, "title": "Title", "questions": (question(),)}
    values.update(kwargs)
    with pytest.raises(InvalidAgentValueError) as caught:
        ReviewTemplate(**values)
    assert_fixed(caught.value, "invalid_agent_value")


def test_subclasses_and_bypassed_references_are_rejected() -> None:
    class Question(EvidenceQuestion):
        pass

    sub = Question(
        question_id="ENC-01",
        text="Is customer data encrypted at rest?",
        search_queries=("q",),
    )
    with pytest.raises(InvalidAgentValueError):
        ReviewTemplate(ref=PINNED_REF, title="Title", questions=(sub,))
    ref = TemplateRef(template_id="ok", version=1, sha256="a" * 64)
    object.__setattr__(ref, "version", 0)
    with pytest.raises(InvalidAgentValueError):
        ReviewTemplate(ref=ref, title="Title", questions=(question(),))
    with pytest.raises(InvalidAgentValueError):
        dataclasses.replace(
            ReviewTemplate(ref=PINNED_REF, title="T", questions=(question(),)), title=""
        )


def test_direct_construction_does_not_prove_packaged_origin() -> None:
    loaded = load_pinned_template(PINNED_REF)
    altered = ReviewTemplate(
        ref=PINNED_REF, title=loaded.title, questions=(question(text="Forged question?"),)
    )
    assert altered.ref == loaded.ref and altered != loaded
    assert load_pinned_template(altered.ref) == loaded


# --- loading -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template_id", "version"),
    [
        ("vendor_security_review", "1"),
        ("vendor_security_review", True),
        ("vendor_security_review", 0),
        ("vendor_security_review", 1000),
        ("Vendor", 1),
        (1, 1),
        ("", 1),
    ],
)
def test_load_template_argument_errors(template_id: Any, version: Any) -> None:
    with pytest.raises(InvalidAgentArgumentError) as caught:
        load_template(template_id, version)
    assert_fixed(caught.value, "invalid_agent_argument")


@pytest.mark.parametrize(
    ("template_id", "version"), [("vendor_security_review", 2), ("other_template", 1)]
)
def test_unknown_templates(template_id: str, version: int) -> None:
    with pytest.raises(UnknownTemplateError) as caught:
        load_template(template_id, version)
    assert_fixed(caught.value, "unknown_review_template")
    with pytest.raises(UnknownTemplateError):
        load_pinned_template(TemplateRef(template_id=template_id, version=version, sha256="a" * 64))


def test_tampered_missing_and_oversize_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    data = packaged_bytes()
    tampered = data.replace(b"Vendor security review", b"Vendor security reviev")
    for resource_data, failure in (
        (tampered, None),
        (data + b"\n", None),
        (data + b"#" * 65_536, None),
        (None, FileNotFoundError("missing")),
        (None, PermissionError("denied")),
    ):
        fake_resource(monkeypatch, resource_data, failure=failure)
        with pytest.raises(TemplateIntegrityError) as caught:
            load_template("vendor_security_review", 1)
        assert_fixed(caught.value, "template_integrity_failed")


def test_registry_key_mismatch_is_an_integrity_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = templates._REGISTRY[("vendor_security_review", 1)]
    monkeypatch.setitem(templates._REGISTRY, ("renamed_template", 1), entry)
    with pytest.raises(TemplateIntegrityError):
        load_template("renamed_template", 1)


def test_the_read_is_bounded_and_uses_the_fixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    data = packaged_bytes()
    resource = fake_resource(monkeypatch, data, step=700)
    assert load_template("vendor_security_review", 1).ref == PINNED_REF
    assert resource.names == [("data", "templates", "vendor_security_review_v1.toml")]
    assert resource.handles[0].offset == len(data)  # short reads are continued to the end
    assert resource.requests[0] == LIMIT_PLUS_ONE
    huge = data + b"#" * 1_000_000
    for step in (None, 4096):
        resource = fake_resource(monkeypatch, huge, step=step)
        with pytest.raises(TemplateIntegrityError):
            load_template("vendor_security_review", 1)
        assert resource.handles[0].offset == LIMIT_PLUS_ONE  # stops after one byte too many


def test_load_pinned_template_compares_the_complete_reference() -> None:
    assert load_pinned_template(PINNED_REF).ref == PINNED_REF
    wrong = dataclasses.replace(PINNED_REF, sha256="0" * 64)
    with pytest.raises(TemplateIntegrityError) as caught:
        load_pinned_template(wrong)
    assert_fixed(caught.value, "template_integrity_failed")
    for argument in (("vendor_security_review", 1), "vendor_security_review", None):
        with pytest.raises(InvalidAgentArgumentError):
            load_pinned_template(argument)  # type: ignore[arg-type]
    bypassed = TemplateRef(template_id="ok", version=1, sha256="a" * 64)
    object.__setattr__(bypassed, "template_id", "Not Valid")
    with pytest.raises(InvalidAgentArgumentError):
        load_pinned_template(bypassed)


def test_process_control_and_logging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    marker = Stop()
    fake_resource(monkeypatch, failure=marker)
    with pytest.raises(Stop) as caught:
        load_template("vendor_security_review", 1)
    assert caught.value is marker
    with pytest.raises(Stop) as caught:
        load_pinned_template(PINNED_REF)
    assert caught.value is marker
    monkeypatch.undo()

    def interrupt(text: str) -> dict[str, Any]:
        raise marker

    monkeypatch.setattr(tomllib, "loads", interrupt)
    with pytest.raises(Stop) as caught:
        parse_template(document())
    assert caught.value is marker
    assert caplog.records == []


# --- planner -------------------------------------------------------------------------------------


def test_plan_review_is_deterministic_and_keeps_queries_in_order() -> None:
    template = load_pinned_template(PINNED_REF)
    planned = plan_review(template)
    assert [p.question for p in planned] == list(template.questions)
    assert [p.retrieval.queries for p in planned] == [queries for _, _, queries, _ in EXPECTED]
    assert {p.retrieval.k for p in planned} == {8}
    assert plan_review(template) == planned
    assert [p.retrieval.k for p in plan_review(template, k=1)] == [1] * 8
    assert [p.retrieval.k for p in plan_review(template, k=20)] == [20] * 8
    assert repr(planned[0]) == "PlannedQuestion(question_id='RET-01', queries=2, k=8)"


@pytest.mark.parametrize("k", [0, 21, True, "8", 8.0])
def test_plan_review_k_bounds(k: Any) -> None:
    with pytest.raises(InvalidAgentArgumentError) as caught:
        plan_review(load_template("vendor_security_review", 1), k=k)
    assert_fixed(caught.value, "invalid_agent_argument")


def test_plan_review_rejects_invalid_templates() -> None:
    template = load_template("vendor_security_review", 1)
    object.__setattr__(template, "title", " padded")
    for argument in (template, "template", PINNED_REF):
        with pytest.raises(InvalidAgentArgumentError):
            plan_review(argument)  # type: ignore[arg-type]


def test_planned_question_binds_queries_to_the_question() -> None:
    value = question(search_queries=("first", "second"))
    assert PlannedQuestion(question=value, retrieval=RetrievalRequest(("first", "second"), 5))
    for queries in (("second", "first"), ("first",), ("first", "second", "third")):
        with pytest.raises(InvalidAgentValueError):
            PlannedQuestion(question=value, retrieval=RetrievalRequest(queries, 5))
    bypassed = RetrievalRequest(("first", "second"), 5)
    object.__setattr__(bypassed, "k", 50)
    with pytest.raises(InvalidAgentValueError):
        PlannedQuestion(question=value, retrieval=bypassed)
    with pytest.raises(InvalidAgentValueError):
        PlannedQuestion(question=question(text=" padded"), retrieval=bypassed)
    with pytest.raises(InvalidAgentValueError):
        PlannedQuestion(question=value, retrieval=RetrievalRequest(("first", "second"), 5), extra=1)
    planned = PlannedQuestion(question=value, retrieval=RetrievalRequest(("first", "second"), 5))
    with pytest.raises(InvalidAgentValueError):
        dataclasses.replace(planned, retrieval=RetrievalRequest(("first",), 5))
