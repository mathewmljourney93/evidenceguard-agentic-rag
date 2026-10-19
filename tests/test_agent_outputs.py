"""M5a strict output schemas, two-pass parsing, immutability and error privacy (ADR-0019).

These run against the project's locked Pydantic and confirm the accepted parse path: strict
JSON mode accepts JSON enum strings and arrays, while direct construction is strict Python mode.
No test touches the network (autouse guard).
"""

import json
import logging
import socket
import traceback
from collections.abc import Callable, Iterator, Mapping
from typing import Any
from uuid import UUID

import pytest

from evidenceguard_domain import agent_outputs
from evidenceguard_domain.agent_outputs import (
    MAX_JSON_VALUES,
    OUTPUT_SCHEMAS,
    SCHEMAS_BY_ID,
    AnalystOutput,
    ClaimOutput,
    FindingOutput,
    QuoteRef,
    VerifierOutput,
    output_schema_for,
    parse_output,
    revalidated_output,
)
from evidenceguard_domain.evidence import Severity, Verdict
from evidenceguard_domain.model_calls import InvalidModelValueError, ModelPurpose

CANARY = "EG-M5A-CANARY-7731"
CHUNK = "00000000-0000-0000-0000-00000000000a"
V = ModelPurpose.VERIFIER
A = ModelPurpose.RISK_ANALYST


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def verifier_doc(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "verdict": "contradicted",
        "claims": [
            {
                "text": "Retention is 90 days.",
                "citations": [
                    {"chunk_id": CHUNK, "quote": "ninety (90) days"},
                    {"chunk_id": CHUNK, "quote": "thirty (30) days"},
                ],
            }
        ],
        "rationale": "Two documents disagree.",
    }
    doc.update(overrides)
    return doc


def analyst_doc(**overrides: Any) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "question_ids": ["RET-01", "CMP-01"],
        "title": "Conflicting retention",
        "severity": "medium",
        "statement": "The DPA and policy disagree.",
        "citations": [{"chunk_id": CHUNK, "quote": "thirty (30) days"}],
        "follow_up_questions": ["Which period applies?"],
    }
    finding.update(overrides)
    return {"findings": [finding]}


def text(doc: object) -> str:
    return json.dumps(doc)


# --- valid parsing -------------------------------------------------------------------------------


def test_verifier_json_enum_strings_and_arrays_decode_to_members_and_tuples() -> None:
    output = parse_output(V, text(verifier_doc()))
    assert type(output) is VerifierOutput
    assert output.verdict is Verdict.CONTRADICTED
    assert type(output.claims) is tuple and type(output.claims[0]) is ClaimOutput
    assert type(output.claims[0].citations) is tuple
    assert type(output.claims[0].citations[0]) is QuoteRef
    assert output.claims[0].citations[0].chunk_uuid == UUID(CHUNK)


def test_analyst_json_decodes_to_immutable_values() -> None:
    output = parse_output(A, text(analyst_doc()))
    assert type(output) is AnalystOutput
    finding = output.findings[0]
    assert finding.severity is Severity.MEDIUM
    assert finding.question_ids == ("RET-01", "CMP-01")
    for collection in (
        output.findings,
        finding.question_ids,
        finding.citations,
        finding.follow_up_questions,
    ):
        assert type(collection) is tuple


def test_optional_collections_default_to_empty_tuples() -> None:
    output = parse_output(V, text({"verdict": "insufficient_evidence", "rationale": "none"}))
    assert type(output) is VerifierOutput and output.claims == ()
    assert parse_output(A, text({})) == AnalystOutput()


def test_text_is_never_stripped_or_normalized() -> None:
    output = parse_output(V, text(verifier_doc(rationale="  Café  \t")))
    assert type(output) is VerifierOutput and output.rationale == "  Café  \t"


def test_surrounding_json_whitespace_is_accepted() -> None:
    assert parse_output(V, "\n  " + text(verifier_doc()) + "\n") is not None


def test_bounds_are_accepted_at_their_limits() -> None:
    claims = [
        {
            "text": "c" * 1000,
            "citations": [{"chunk_id": CHUNK, "quote": f"q{index}"} for index in range(8)],
        }
        for _ in range(10)
    ]
    assert parse_output(V, text(verifier_doc(claims=claims, rationale="r" * 2000))) is not None
    # Twenty findings with twenty IDs each fit the 65,536-byte output bound only with shorter
    # texts, so the per-field text limits are checked on one finding.
    findings = [
        {
            "question_ids": [f"QQ-{index:02d}" for index in range(20)],
            "title": "t" * 200,
            "severity": "info",
            "statement": "s" * 1500,
            "follow_up_questions": ["f"] * 5,
        }
    ] * 20
    assert parse_output(A, text({"findings": findings})) is not None
    longest = {
        "question_ids": ["RET-01"],
        "title": "t" * 200,
        "severity": "low",
        "statement": "s" * 2000,
        "follow_up_questions": ["f" * 500] * 5,
    }
    assert parse_output(A, text({"findings": [longest]})) is not None


# --- rejected output -----------------------------------------------------------------------------


INVALID_VERIFIER = [
    '{"verdict":"supported","verdict":"supported","rationale":"r"}',  # duplicate key
    '{"verdict":"supported","rationale":"r","claims":[{"text":"c","text":"d"}]}',
    '{"verdict":"supported","rationale":NaN}',
    '{"verdict":"supported","rationale":Infinity}',
    '{"verdict":"supported","rationale":-Infinity}',
    '{"verdict":"supported","rationale":"r","x":1e999}',
    '{"verdict":"supported","rationale":"r"} trailing prose',
    '{"verdict":"supported","rationale":"r"}{}',
    '```json\n{"verdict":"supported","rationale":"r"}\n```',
    'Here is my answer: {"verdict":"supported","rationale":"r"}',
    '[{"verdict":"supported","rationale":"r"}]',
    '"supported"',
    "",
    "null",
    '﻿{"verdict":"supported","rationale":"r"}',
    '{"verdict":"supported","rationale":"\\ud800"}',  # lone surrogate escape
    '{"verdict":"supported","rationale":"a\\u0000b"}',  # NUL
]


@pytest.mark.parametrize("payload", INVALID_VERIFIER)
def test_malformed_json_is_rejected(payload: str) -> None:
    assert parse_output(V, payload) is None


@pytest.mark.parametrize(
    "doc",
    [
        verifier_doc(extra=1),
        {"verdict": "supported"},  # missing rationale
        verifier_doc(verdict=1),  # numeric enum
        verifier_doc(verdict="yes"),
        verifier_doc(verdict="SUPPORTED"),
        verifier_doc(rationale=7),  # number for a string
        verifier_doc(rationale=""),
        verifier_doc(rationale="r" * 2001),
        verifier_doc(rationale=None),
        verifier_doc(claims="c"),
        verifier_doc(claims={"text": "c"}),
        verifier_doc(claims=[{"text": "c"}] * 11),
        verifier_doc(claims=[{"text": "c", "citations": [{"chunk_id": CHUNK, "quote": "q"}] * 2}]),
        verifier_doc(
            claims=[
                {
                    "text": "c",
                    "citations": [{"chunk_id": CHUNK, "quote": f"q{index}"} for index in range(9)],
                }
            ]
        ),
        verifier_doc(claims=[{"text": "c", "extra": True}]),
        verifier_doc(claims=[{"text": ""}]),
        verifier_doc(
            claims=[{"text": "c", "citations": [{"chunk_id": CHUNK.upper(), "quote": "q"}]}]
        ),
        verifier_doc(
            claims=[{"text": "c", "citations": [{"chunk_id": "{" + CHUNK + "}", "quote": "q"}]}]
        ),
        verifier_doc(
            claims=[
                {"text": "c", "citations": [{"chunk_id": CHUNK.replace("-", ""), "quote": "q"}]}
            ]
        ),
        verifier_doc(
            claims=[{"text": "c", "citations": [{"chunk_id": "urn:uuid:" + CHUNK, "quote": "q"}]}]
        ),
        verifier_doc(claims=[{"text": "c", "citations": [{"chunk_id": 10, "quote": "q"}]}]),
        verifier_doc(claims=[{"text": "c", "citations": [{"chunk_id": CHUNK, "quote": ""}]}]),
        verifier_doc(evidence_status="vendor_claim"),  # the model never supplies status
        analyst_doc(),  # the other purpose's schema
    ],
)
def test_schema_violations_are_rejected(doc: dict[str, Any]) -> None:
    assert parse_output(V, text(doc)) is None


@pytest.mark.parametrize(
    "doc",
    [
        analyst_doc(severity="critical"),
        analyst_doc(severity=1),
        analyst_doc(question_ids=[]),
        analyst_doc(question_ids=["RET-01", "RET-01"]),
        analyst_doc(question_ids=["ret-01"]),
        analyst_doc(question_ids="RET-01"),
        analyst_doc(question_ids=[f"QQ-{index:02d}" for index in range(21)]),
        analyst_doc(title="t" * 201),
        analyst_doc(follow_up_questions=["f"] * 6),
        analyst_doc(follow_up_questions=[""]),
        analyst_doc(citations=[{"chunk_id": CHUNK, "quote": "q"}] * 2),
        analyst_doc(source_type="contract"),
        {"findings": [analyst_doc()["findings"][0]] * 21},
        verifier_doc(),
    ],
)
def test_analyst_schema_violations_are_rejected(doc: dict[str, Any]) -> None:
    assert parse_output(A, text(doc)) is None


def test_oversized_text_is_rejected_before_parsing() -> None:
    padded = text(verifier_doc()) + " " * 65_536
    assert parse_output(V, padded) is None
    exact = text({"verdict": "supported", "rationale": "r"})
    assert parse_output(V, exact + " " * (65_536 - len(exact))) is not None


def test_depth_and_value_count_limits() -> None:
    nested: object = 1
    for _ in range(8):
        nested = [nested]
    assert not agent_outputs._scan(text({"a": nested}))  # depth 10 > 8
    assert agent_outputs._scan(text({"a": [[[[[[1]]]]]]}))  # depth 8
    many = {"values": list(range(MAX_JSON_VALUES - 2))}
    assert agent_outputs._scan(text(many))
    many = {"values": list(range(MAX_JSON_VALUES - 1))}
    assert not agent_outputs._scan(text(many))
    assert parse_output(V, "[" * 50_000) is None  # pathological nesting


def test_non_string_text_gives_no_output_and_a_bad_purpose_raises() -> None:
    assert parse_output(V, None) is None
    assert parse_output(V, b"{}") is None
    with pytest.raises(InvalidModelValueError):
        parse_output("verifier", text(verifier_doc()))  # type: ignore[arg-type]


# --- registry ------------------------------------------------------------------------------------


def test_the_schema_registry_is_closed() -> None:
    assert dict(OUTPUT_SCHEMAS) == {V: VerifierOutput, A: AnalystOutput}
    assert dict(SCHEMAS_BY_ID) == {
        "verifier_output_v1": VerifierOutput,
        "risk_analyst_output_v1": AnalystOutput,
    }
    with pytest.raises(TypeError):
        OUTPUT_SCHEMAS[V] = AnalystOutput  # type: ignore[index]
    assert output_schema_for(A) is AnalystOutput
    with pytest.raises(InvalidModelValueError):
        output_schema_for("risk_analyst")  # type: ignore[arg-type]


# --- direct construction, copies and immutability -----------------------------------------------


def quote(value: str = "q") -> QuoteRef:
    return QuoteRef(chunk_id=CHUNK, quote=value)


def test_direct_construction_is_strict_python_mode() -> None:
    claim = ClaimOutput(text="c", citations=(quote(),))
    assert VerifierOutput(verdict=Verdict.SUPPORTED, claims=(claim,), rationale="r")
    for kwargs in (
        {"verdict": "supported", "rationale": "r"},  # raw enum string
        {"verdict": Verdict.SUPPORTED, "claims": [claim], "rationale": "r"},  # list
        {"verdict": Verdict.SUPPORTED, "claims": ({"text": "c"},), "rationale": "r"},  # dict
        {"verdict": Verdict.SUPPORTED, "rationale": "r", "extra": 1},
        {"verdict": Verdict.SUPPORTED, "rationale": "a\x00b"},
        {"verdict": Verdict.SUPPORTED, "rationale": "\ud800"},
    ):
        with pytest.raises(InvalidModelValueError):
            VerifierOutput(**kwargs)
    with pytest.raises(InvalidModelValueError):
        ClaimOutput(text="c", citations=(quote(), quote()))  # duplicate
    with pytest.raises(InvalidModelValueError):
        ClaimOutput(text="c", citations=({"chunk_id": CHUNK, "quote": "q"},))  # type: ignore[arg-type]
    with pytest.raises(InvalidModelValueError):
        FindingOutput(
            question_ids=("RET-01",),
            title="t",
            severity="high",  # type: ignore[arg-type]
            statement="s",
        )
    with pytest.raises(InvalidModelValueError):
        AnalystOutput(findings=({"title": "t"},))  # type: ignore[arg-type]


def test_public_validators_are_strict_and_take_no_options() -> None:
    claim = ClaimOutput(text="c")
    data = {"verdict": Verdict.SUPPORTED, "claims": (claim,), "rationale": "r"}
    assert VerifierOutput.model_validate(data).claims == (claim,)
    with pytest.raises(InvalidModelValueError):
        VerifierOutput.model_validate({**data, "claims": ({"text": "c"},)})
    with pytest.raises(InvalidModelValueError):
        VerifierOutput.model_validate({**data, "verdict": "supported"})
    with pytest.raises(InvalidModelValueError):
        VerifierOutput.model_validate(data, strict=False)
    with pytest.raises(InvalidModelValueError):
        VerifierOutput.model_validate_json(text(verifier_doc()), strict=False)
    with pytest.raises(InvalidModelValueError):
        VerifierOutput.model_validate_strings({"verdict": "supported"}, strict=False)
    assert type(VerifierOutput.model_validate_json(text(verifier_doc()))) is VerifierOutput


def test_pydantic_treats_the_wrapping_init_as_its_own() -> None:
    """Pins the Pydantic 2.14 dependency recorded in ADR-0019: without the base-init flag, JSON
    validation would call ``__init__`` with raw values and reject valid JSON enum strings."""
    for model in (QuoteRef, ClaimOutput, VerifierOutput, FindingOutput, AnalystOutput):
        assert model.__pydantic_custom_init__ is False


def test_outputs_are_deeply_immutable() -> None:
    output = parse_output(V, text(verifier_doc()))
    assert isinstance(output, VerifierOutput)
    with pytest.raises(InvalidModelValueError):
        output.rationale = "changed"  # type: ignore[misc]
    with pytest.raises(InvalidModelValueError):
        del output.rationale
    with pytest.raises(InvalidModelValueError):
        output.claims[0].citations[0].quote = "changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        output.claims.append(output.claims[0])  # type: ignore[attr-defined]
    for value in (output, *output.claims, *output.claims[0].citations):
        for name in type(value).model_fields:
            assert type(getattr(value, name)) not in (list, dict, set)


def test_model_copy_revalidates() -> None:
    output = VerifierOutput(verdict=Verdict.SUPPORTED, rationale="r")
    copy = output.model_copy(update={"rationale": "s"})
    assert copy.rationale == "s" and output.rationale == "r"
    for update in (
        {"rationale": ""},
        {"verdict": "supported"},
        {"claims": [ClaimOutput(text="c")]},
        {"unknown": 1},
    ):
        with pytest.raises(InvalidModelValueError):
            output.model_copy(update=update)
    with pytest.raises(InvalidModelValueError):
        output.model_copy(update=[("rationale", "s")])  # type: ignore[arg-type]
    assert output.model_copy(deep=True) == output


def test_bypassed_values_are_caught_on_revalidation() -> None:
    bad_claim = ClaimOutput.model_construct(text="", citations=())
    with pytest.raises(InvalidModelValueError):
        VerifierOutput(verdict=Verdict.SUPPORTED, claims=(bad_claim,), rationale="r")
    output = VerifierOutput(verdict=Verdict.SUPPORTED, rationale="r")
    object.__setattr__(output, "rationale", "")  # a deliberate bypass; not a security boundary
    with pytest.raises(InvalidModelValueError):
        revalidated_output(V, output)
    with pytest.raises(InvalidModelValueError):
        revalidated_output(A, VerifierOutput(verdict=Verdict.SUPPORTED, rationale="r"))


# --- privacy -------------------------------------------------------------------------------------


def assert_private(error: BaseException) -> None:
    assert type(error) is InvalidModelValueError
    assert str(error) == "invalid_model_value"
    assert error.__cause__ is None and error.__context__ is None
    rendered = "".join(traceback.format_exception(error)) + repr(error)
    assert CANARY not in rendered


def test_validation_errors_never_carry_input(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    bad = f"{CANARY}\x00"
    attempts: list[Callable[[], object]] = [
        lambda: VerifierOutput(verdict=Verdict.SUPPORTED, rationale=bad),
        lambda: VerifierOutput(verdict=CANARY, rationale="r"),  # type: ignore[arg-type]
        lambda: ClaimOutput(text=CANARY * 100),
        lambda: QuoteRef(chunk_id=CANARY, quote="q"),
        lambda: FindingOutput(
            question_ids=(CANARY,), title="t", severity=Severity.LOW, statement="s"
        ),
        lambda: AnalystOutput(findings=(CANARY,)),  # type: ignore[arg-type]
        lambda: VerifierOutput.model_validate({"verdict": CANARY, "rationale": CANARY}),
        lambda: VerifierOutput.model_validate_json(f'{{"verdict":"{CANARY}"}}'),
        lambda: VerifierOutput.model_validate_strings({"verdict": CANARY}),
        lambda: VerifierOutput(verdict=Verdict.SUPPORTED, rationale="r").model_copy(
            update={"rationale": bad}
        ),
        lambda: setattr(VerifierOutput(verdict=Verdict.SUPPORTED, rationale="r"), "x", CANARY),
    ]
    for attempt in attempts:
        with pytest.raises(InvalidModelValueError) as caught:
            attempt()
        assert_private(caught.value)
    assert not caplog.records


def test_representations_show_counts_only() -> None:
    values: list[object] = [
        QuoteRef(chunk_id=CHUNK, quote=CANARY),
        ClaimOutput(text=CANARY, citations=(QuoteRef(chunk_id=CHUNK, quote=CANARY),)),
        VerifierOutput(
            verdict=Verdict.SUPPORTED, claims=(ClaimOutput(text=CANARY),), rationale=CANARY
        ),
        FindingOutput(
            question_ids=("RET-01",),
            title=CANARY,
            severity=Severity.LOW,
            statement=CANARY,
            follow_up_questions=(CANARY,),
        ),
    ]
    values.append(AnalystOutput(findings=(values[3],)))  # type: ignore[arg-type]
    for value in values:
        assert CANARY not in repr(value) and CANARY not in str(value)
        assert CANARY not in repr(list(value.__repr_args__()))  # type: ignore[attr-defined]
    assert repr(values[2]) == "VerifierOutput(claims=1)"
    assert repr(values[3]) == "FindingOutput(question_ids=1, citations=0, follow_up_questions=1)"
    assert repr(values[0]) == "QuoteRef()"


# --- Prompt 172 regressions: public validation boundaries ----------------------------------------


class RaisingMapping(dict[str, Any]):
    """A ``dict`` whose selected methods raise ``error``. This exercises error normalization
    for supported inputs; it is not a sandbox test."""

    def __init__(self, data: dict[str, Any], error: BaseException, methods: set[str]) -> None:
        super().__init__(data)
        self._error = error
        self._methods = methods

    def _maybe(self, name: str) -> None:
        if name in self._methods:
            raise self._error

    def __contains__(self, key: object) -> bool:
        self._maybe("__contains__")
        return super().__contains__(key)

    def __getitem__(self, key: str) -> Any:
        self._maybe("__getitem__")
        return super().__getitem__(key)

    def __iter__(self) -> Any:
        self._maybe("__iter__")
        return super().__iter__()

    def items(self) -> Any:
        self._maybe("items")
        return super().items()

    def keys(self) -> Any:
        self._maybe("keys")
        return super().keys()


VALID_PYTHON: dict[str, Any] = {"verdict": Verdict.SUPPORTED, "rationale": "r"}
RAW_SEVERITY: dict[str, Any] = {
    "question_ids": ("RET-01",),
    "title": "t",
    "severity": "high",
    "statement": "s",
}


@pytest.mark.parametrize(
    ("model", "data"),
    [
        (VerifierOutput, {"verdict": "supported", "rationale": "r"}),
        (VerifierOutput, {"verdict": "supported", "rationale": "r", "claims": ()}),
        (FindingOutput, RAW_SEVERITY),
        (AnalystOutput, {"findings": (RAW_SEVERITY,)}),
        (VerifierOutput, {"verdict": Verdict.SUPPORTED, "rationale": "r", "claims": []}),
        (ClaimOutput, {"text": "c", "citations": ({"chunk_id": CHUNK, "quote": "q"},)}),
    ],
)
def test_strings_validation_rejects_disallowed_python_inputs(
    model: type[Any], data: dict[str, Any]
) -> None:
    """Finding A: string mode must not coerce what the Python-mode entry points reject."""
    with pytest.raises(InvalidModelValueError) as caught:
        model.model_validate_strings(data)
    assert_private(caught.value)
    with pytest.raises(InvalidModelValueError):
        model.model_validate(data)


def test_strings_validation_accepts_what_model_validate_accepts() -> None:
    assert VerifierOutput.model_validate_strings(VALID_PYTHON) == VerifierOutput(**VALID_PYTHON)
    claim = ClaimOutput(text="c", citations=(QuoteRef(chunk_id=CHUNK, quote="q"),))
    built = VerifierOutput.model_validate_strings({**VALID_PYTHON, "claims": (claim,)})
    assert built.claims == (claim,)


def test_valid_json_equivalents_still_parse() -> None:
    document = '{"verdict":"supported","rationale":"r"}'
    assert parse_output(V, document) == VerifierOutput(**VALID_PYTHON)
    assert VerifierOutput.model_validate_json(document) == VerifierOutput(**VALID_PYTHON)
    finding = (
        '{"findings":[{"question_ids":["RET-01"],"title":"t","severity":"high","statement":"s"}]}'
    )
    parsed = parse_output(A, finding)
    assert type(parsed) is AnalystOutput and parsed.findings[0].severity is Severity.HIGH


@pytest.mark.parametrize("method", ["model_validate", "model_validate_strings"])
@pytest.mark.parametrize("raising", ["__contains__", "__getitem__"])
def test_mapping_failures_during_validation_are_fixed_errors(
    method: str,
    raising: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Finding B (a, b): a failing mapping method becomes a fresh fixed error."""
    caplog.set_level(logging.DEBUG)
    data = RaisingMapping(
        {**VALID_PYTHON, "claims": (ClaimOutput(text="c"),)}, RuntimeError(CANARY), {raising}
    )
    with pytest.raises(InvalidModelValueError) as caught:
        getattr(VerifierOutput, method)(data)
    assert_private(caught.value)
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err
    assert not caplog.records


class RaisingUpdate(Mapping[str, Any]):
    """A non-``dict`` mapping: ``items()`` iterates it and reads its values, so a failing
    ``__iter__`` or ``__getitem__`` surfaces while the update is read."""

    def __init__(self, error: BaseException, methods: set[str]) -> None:
        self._data = {"rationale": "s"}
        self._error = error
        self._methods = methods

    def __getitem__(self, key: str) -> Any:
        if "__getitem__" in self._methods:
            raise self._error
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        if "__iter__" in self._methods:
            raise self._error
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def failing_updates(error: BaseException) -> list[Mapping[str, Any]]:
    return [
        RaisingMapping({"rationale": "s"}, error, {"items"}),
        RaisingUpdate(error, {"__iter__"}),
        RaisingUpdate(error, {"__getitem__"}),
    ]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_mapping_failures_during_copy_updates_are_fixed_errors(
    index: int, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Finding B (c): reading the update mapping is inside the same error boundary."""
    caplog.set_level(logging.DEBUG)
    output = VerifierOutput(**VALID_PYTHON)
    update = failing_updates(RuntimeError(CANARY))[index]
    with pytest.raises(InvalidModelValueError) as caught:
        output.model_copy(update=update)
    assert_private(caught.value)
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err
    assert not caplog.records
    assert output.model_copy(update={"rationale": "s"}).rationale == "s"


@pytest.mark.parametrize("raising", ["__iter__", "keys", "__getitem__"])
def test_a_dict_update_never_leaks_a_raw_error(raising: str) -> None:
    """The reviewer's probe (c) used a ``dict`` subclass whose ``__iter__`` raises. The
    corrected copy reads the update through ``items()``, which for a ``dict`` does not call
    these overrides, so the copy succeeds with validated content; whatever happens, no raw
    error escapes."""
    update = RaisingMapping({"rationale": "s"}, RuntimeError(CANARY), {raising})
    try:
        copy = VerifierOutput(**VALID_PYTHON).model_copy(update=update)
    except InvalidModelValueError as error:
        assert_private(error)
    else:
        assert copy.rationale == "s"


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(4)])
def test_process_control_through_validation_traversal_propagates_unchanged(
    error: BaseException,
) -> None:
    for method in ("model_validate", "model_validate_strings"):
        data = RaisingMapping(dict(VALID_PYTHON), error, {"__contains__", "__getitem__"})
        with pytest.raises(type(error)) as caught:
            getattr(VerifierOutput, method)(data)
        assert caught.value is error
    for update in failing_updates(error):
        with pytest.raises(type(error)) as caught:
            VerifierOutput(**VALID_PYTHON).model_copy(update=update)
        assert caught.value is error
