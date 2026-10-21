"""Request assembly: settings, stage inputs, repair reasons and the Verifier, Risk Analyst and
repair request builders (M5c-B1, E1, F to F5; ADR-0021).

One path: JSON in, JSON out
---------------------------
The user text is one closed JSON object (``eg-verifier-input-v1`` or ``eg-analyst-input-v1``) in
which every untrusted string (document titles, section paths, version labels, headers, bodies and
earlier model-derived text) appears only as a JSON string value, serialized with
``json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
allow_nan=False)``. Delimiter-like text inside a document therefore cannot end a value or create a
field; this prevents structural forgery only, not semantic injection. A model reply is validated
by M5a ``parse_output`` with its existing two passes (a bounded preliminary JSON scan, then strict
JSON-mode schema validation of the same original response text); nothing here or in M5g decodes
the returned quotation strings again (no entity, escape, Unicode or JSON decoding).

Checks and boundaries
---------------------
Each builder rebuilds every input, applies the prompt binding (purpose, registry entry, pinned
digest and the exact system-text SHA-256, which ``StructuredRequest`` does not check) and the
stage's identity checks, checks every string in the user object for strict UTF-8 encodability,
serializes it and refuses a user text above 400,000 UTF-8 bytes (``RequestTooLargeError``) before
any request exists; nothing is dropped, shortened or reordered. The byte limit bounds accepted
requests, not peak memory, and there is no hard deadline. Trusted tenant, review, snapshot,
revision and document IDs are never inserted as metadata; document or model text that happens to
contain such strings is preserved unchanged. Assembly cannot prove that its evidence or Verifier
inputs came from trusted paths (M5g's obligation), and a request digest identifies content and
configuration, not tenant authorization or review identity.

Repair requests are built by reassembly: the unrepaired request is rebuilt from the supplied
inputs and must equal the supplied original in every field before one closed ``repair`` member
holding only fixed fields is added. This module cannot know how many repairs a stage has used;
the lifetime repair and call budget is enforced by M5g.
"""

import json
from dataclasses import dataclass

from evidenceguard_agents.artifact_errors import (
    InvalidAgentValueError,
    InvalidAssemblyInputError,
    RequestTooLargeError,
    require,
    run_guarded,
)
from evidenceguard_agents.prompts import PromptSpec, _is_bound, _rebuilt_spec
from evidenceguard_domain.evidence import EvidenceQuestion
from evidenceguard_domain.model_calls import (
    DEFAULT_TIMEOUT_MS,
    MAX_OUTPUT_TOKENS,
    MAX_TIMEOUT_MS,
    MAX_USER_TEXT_BYTES,
    MIN_TIMEOUT_MS,
    CallOutcome,
    ModelPurpose,
    PromptRef,
    StructuredRequest,
    is_model_id,
    is_question_id,
    utf8_size,
)
from evidenceguard_domain.provenance import (
    ProvenanceRejection,
    QuestionEvidence,
    RejectionReason,
    RejectionStage,
    VerifiedQuestion,
)

VERIFIER_INPUT_FORMAT = "eg-verifier-input-v1"
ANALYST_INPUT_FORMAT = "eg-analyst-input-v1"
DEFAULT_MAX_OUTPUT_TOKENS = 4_096

_STAGES = {
    ModelPurpose.VERIFIER: RejectionStage.VERIFICATION,
    ModelPurpose.RISK_ANALYST: RejectionStage.ANALYSIS,
}
_PURPOSES = {stage: purpose for purpose, stage in _STAGES.items()}


def _is_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


# --- rebuilding supplied domain values ------------------------------------------------------------


def _checked_question(value: object) -> EvidenceQuestion:
    """Check a supplied ``EvidenceQuestion``'s own field values at the M5c boundary, **before**
    any reconstruction that could normalize them (strip text, convert a list to a tuple or an
    integer to a ``bool``) or emit serializer warnings: exact ``str`` identifier and text, an
    exact ``tuple`` of exact ``str`` queries and an exact ``bool`` flag. The question is then
    rebuilt through public validation, and every rebuilt field must equal the supplied one with
    the same type."""
    require(type(value) is EvidenceQuestion)
    assert isinstance(value, EvidenceQuestion)
    question_id = value.question_id
    text = value.text
    queries = value.search_queries
    documentary = value.requires_documentary_support
    require(type(question_id) is str and type(text) is str)
    require(type(queries) is tuple and all(type(query) is str for query in queries))
    require(type(documentary) is bool)
    rebuilt = EvidenceQuestion.model_validate(
        {
            "question_id": question_id,
            "text": text,
            "search_queries": queries,
            "requires_documentary_support": documentary,
        }
    )
    require(type(rebuilt.question_id) is str and rebuilt.question_id == question_id)
    require(type(rebuilt.text) is str and rebuilt.text == text)
    require(type(rebuilt.search_queries) is tuple and rebuilt.search_queries == queries)
    require(all(type(query) is str for query in rebuilt.search_queries))
    require(rebuilt.requires_documentary_support is documentary)
    return rebuilt


def _rebuilt_evidence(value: object) -> QuestionEvidence:
    """Check the nested question first (M5b's reconstruction would normalize it), then rebuild
    the evidence from the checked question and require the stored question to be unchanged."""
    require(type(value) is QuestionEvidence)
    assert isinstance(value, QuestionEvidence)
    question = _checked_question(value.question)
    rebuilt = QuestionEvidence(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        snapshot_sha256=value.snapshot_sha256,
        question=question,
        result=value.result,
    )
    require(_checked_question(rebuilt.question) == question)
    return rebuilt


def _rebuilt_verified(value: object) -> VerifiedQuestion:
    require(type(value) is VerifiedQuestion)
    assert isinstance(value, VerifiedQuestion)
    return VerifiedQuestion(
        tenant_id=value.tenant_id,
        review_id=value.review_id,
        question_id=value.question_id,
        snapshot_sha256=value.snapshot_sha256,
        request_sha256=value.request_sha256,
        match_rules=value.match_rules,
        verification=value.verification,
        claims=value.claims,
        provenance=value.provenance,
    )


def _rebuilt_request(value: object) -> StructuredRequest:
    require(type(value) is StructuredRequest)
    assert isinstance(value, StructuredRequest)
    return StructuredRequest(
        purpose=value.purpose,
        prompt=value.prompt,
        model_id=value.model_id,
        question_id=value.question_id,
        system_text=value.system_text,
        user_text=value.user_text,
        max_output_tokens=value.max_output_tokens,
        timeout_ms=value.timeout_ms,
    )


# --- values ---------------------------------------------------------------------------------------


@dataclass(frozen=True, init=False, repr=False)
class ModelSettings:
    """The model and per-call limits from the trusted review configuration (never from a
    template or prompt)."""

    model_id: str
    max_output_tokens: int
    timeout_ms: int

    def __init__(
        self,
        *,
        model_id: str,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        **unknown: object,
    ) -> None:
        def build() -> None:
            require(not unknown and type(model_id) is str and is_model_id(model_id))
            require(_is_int(max_output_tokens, 1, MAX_OUTPUT_TOKENS))
            require(_is_int(timeout_ms, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS))
            object.__setattr__(self, "model_id", model_id)
            object.__setattr__(self, "max_output_tokens", max_output_tokens)
            object.__setattr__(self, "timeout_ms", timeout_ms)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"ModelSettings(model_id={self.model_id!r}, "
            f"max_output_tokens={self.max_output_tokens}, timeout_ms={self.timeout_ms})"
        )

    __str__ = __repr__


def _rebuilt_settings(value: object) -> ModelSettings:
    require(type(value) is ModelSettings)
    assert isinstance(value, ModelSettings)
    return ModelSettings(
        model_id=value.model_id,
        max_output_tokens=value.max_output_tokens,
        timeout_ms=value.timeout_ms,
    )


def _prompt_for(value: object, purpose: ModelPurpose) -> PromptSpec:
    checked = _rebuilt_spec(value)
    require(checked.purpose is purpose)
    return checked


@dataclass(frozen=True, init=False, repr=False)
class VerifierRequestInputs:
    """Everything a Verifier request is assembled from. Binding of the prompt to the registry
    and the system text is checked by assembly."""

    evidence: QuestionEvidence
    prompt: PromptSpec
    system_text: str
    settings: ModelSettings

    def __init__(
        self,
        *,
        evidence: QuestionEvidence,
        prompt: PromptSpec,
        system_text: str,
        settings: ModelSettings,
        **unknown: object,
    ) -> None:
        def build() -> None:
            require(not unknown and type(system_text) is str)
            checked_evidence = _rebuilt_evidence(evidence)
            checked_prompt = _prompt_for(prompt, ModelPurpose.VERIFIER)
            checked_settings = _rebuilt_settings(settings)
            object.__setattr__(self, "evidence", checked_evidence)
            object.__setattr__(self, "prompt", checked_prompt)
            object.__setattr__(self, "system_text", system_text)
            object.__setattr__(self, "settings", checked_settings)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"VerifierRequestInputs(question_id={self.evidence.question.question_id!r}, "
            f"items={len(self.evidence.result.items)}, "
            f"prompt_id={self.prompt.ref.prompt_id!r}, prompt_version={self.prompt.ref.version})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class AnalystRequestInputs:
    """Everything a Risk Analyst request is assembled from: the question's validated Verifier
    value (from ``verify_question`` or ``recheck_verified``, which this cannot prove), the
    question, the prompt, its system text and the settings."""

    owner: VerifiedQuestion
    question: EvidenceQuestion
    prompt: PromptSpec
    system_text: str
    settings: ModelSettings

    def __init__(
        self,
        *,
        owner: VerifiedQuestion,
        question: EvidenceQuestion,
        prompt: PromptSpec,
        system_text: str,
        settings: ModelSettings,
        **unknown: object,
    ) -> None:
        def build() -> None:
            require(not unknown and type(system_text) is str)
            checked_owner = _rebuilt_verified(owner)
            checked_question = _checked_question(question)
            require(checked_owner.question_id == checked_question.question_id)
            checked_prompt = _prompt_for(prompt, ModelPurpose.RISK_ANALYST)
            checked_settings = _rebuilt_settings(settings)
            object.__setattr__(self, "owner", checked_owner)
            object.__setattr__(self, "question", checked_question)
            object.__setattr__(self, "prompt", checked_prompt)
            object.__setattr__(self, "system_text", system_text)
            object.__setattr__(self, "settings", checked_settings)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"AnalystRequestInputs(question_id={self.question.question_id!r}, "
            f"claims={len(self.owner.claims)}, "
            f"citations={len(self.owner.verification.citations)}, "
            f"prompt_id={self.prompt.ref.prompt_id!r}, prompt_version={self.prompt.ref.version})"
        )

    __str__ = __repr__


@dataclass(frozen=True, init=False, repr=False)
class RepairReason:
    """Why one repair is requested: ``invalid_output`` (no positions, either purpose) or an M5b
    ``RejectionReason`` whose stage matches the purpose and whose positions follow the
    ``ProvenanceRejection`` rules. It carries no text."""

    purpose: ModelPurpose
    question_id: str
    code: CallOutcome | RejectionReason
    item_index: int | None
    citation_index: int | None

    def __init__(
        self,
        *,
        purpose: ModelPurpose,
        question_id: str,
        code: CallOutcome | RejectionReason,
        item_index: int | None = None,
        citation_index: int | None = None,
        **unknown: object,
    ) -> None:
        def build() -> None:
            require(not unknown and type(purpose) is ModelPurpose)
            require(type(question_id) is str and is_question_id(question_id))
            if type(code) is CallOutcome:
                require(code is CallOutcome.INVALID_OUTPUT)
                require(item_index is None and citation_index is None)
            else:
                require(type(code) is RejectionReason)
                assert isinstance(code, RejectionReason)
                # the exact M5b stage and position rules (a count of 1 is valid for every reason)
                ProvenanceRejection(
                    stage=_STAGES[purpose],
                    question_id=question_id,
                    reason=code,
                    item_index=item_index,
                    citation_index=citation_index,
                    rejected_count=1,
                )
            object.__setattr__(self, "purpose", purpose)
            object.__setattr__(self, "question_id", question_id)
            object.__setattr__(self, "code", code)
            object.__setattr__(self, "item_index", item_index)
            object.__setattr__(self, "citation_index", citation_index)

        run_guarded(build, InvalidAgentValueError)

    @classmethod
    def invalid_output(
        cls, *, purpose: ModelPurpose, question_id: str, **unknown: object
    ) -> "RepairReason":
        def build() -> RepairReason:
            require(not unknown)
            return cls(purpose=purpose, question_id=question_id, code=CallOutcome.INVALID_OUTPUT)

        return run_guarded(build, InvalidAgentValueError)

    @classmethod
    def from_rejection(cls, rejection: ProvenanceRejection) -> "RepairReason":
        """The repair reason for an M5b rejection (its ``rejected_count`` is not carried)."""

        def build() -> RepairReason:
            require(type(rejection) is ProvenanceRejection)
            checked = ProvenanceRejection(
                stage=rejection.stage,
                question_id=rejection.question_id,
                reason=rejection.reason,
                item_index=rejection.item_index,
                citation_index=rejection.citation_index,
                rejected_count=rejection.rejected_count,
            )
            return cls(
                purpose=_PURPOSES[checked.stage],
                question_id=checked.question_id,
                code=checked.reason,
                item_index=checked.item_index,
                citation_index=checked.citation_index,
            )

        return run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"RepairReason(purpose={self.purpose.value!r}, question_id={self.question_id!r}, "
            f"code={self.code.value!r}, item_index={self.item_index}, "
            f"citation_index={self.citation_index})"
        )

    __str__ = __repr__


def _rebuilt_reason(value: object) -> RepairReason:
    require(type(value) is RepairReason)
    assert isinstance(value, RepairReason)
    return RepairReason(
        purpose=value.purpose,
        question_id=value.question_id,
        code=value.code,
        item_index=value.item_index,
        citation_index=value.citation_index,
    )


# --- user objects ---------------------------------------------------------------------------------


def _question_object(question: EvidenceQuestion) -> dict[str, object]:
    return {
        "id": question.question_id,
        "requires_documentary_support": question.requires_documentary_support,
        "text": question.text,
    }


def _verifier_object(evidence: QuestionEvidence) -> dict[str, object]:
    entries: list[object] = []
    for item in evidence.result.items:
        chunk = item.evidence
        entries.append(
            {
                "body": chunk.body_text,
                "chunk_id": str(chunk.chunk_id),
                "document": {
                    "authenticity": chunk.authenticity.value,
                    "effective_date": (
                        None if chunk.effective_date is None else chunk.effective_date.isoformat()
                    ),
                    "revision_no": chunk.revision_no,
                    "section_path": list(chunk.section_path),
                    "source_type": chunk.source_type.value,
                    "title": chunk.title,
                    "version_label": chunk.version_label,
                },
                "header": chunk.header_text,
                "rank": item.fused_rank,
            }
        )
    return {
        "evidence": entries,
        "format": VERIFIER_INPUT_FORMAT,
        "question": _question_object(evidence.question),
    }


def _analyst_object(owner: VerifiedQuestion, question: EvidenceQuestion) -> dict[str, object]:
    verification = owner.verification
    return {
        "citations": [
            {
                "authenticity": citation.authenticity.value,
                "chunk_id": str(citation.chunk_id),
                "index": index,
                "quote": citation.quote,
                "source_type": citation.source_type.value,
            }
            for index, citation in enumerate(verification.citations)
        ],
        "claims": [
            {"citation_indexes": list(claim.citation_indexes), "text": claim.text}
            for claim in owner.claims
        ],
        "format": ANALYST_INPUT_FORMAT,
        "question": _question_object(question),
        "verification": {
            "evidence_status": verification.evidence_status.value,
            "rationale": verification.rationale,
            "verdict": verification.verdict.value,
        },
    }


def _all_encodable(value: object) -> bool:
    """Every string in the user object (keys and values, at any depth) is strictly UTF-8
    encodable; metadata strings are not guaranteed to be by ``ChunkEvidence``."""
    if type(value) is str:
        return utf8_size(value) is not None
    if type(value) is dict:
        return all(_all_encodable(key) and _all_encodable(item) for key, item in value.items())
    if type(value) is list:
        return all(_all_encodable(item) for item in value)
    return value is None or type(value) in (bool, int)


# --- assembly -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Prepared:
    """A fully checked, not yet serialized request (internal)."""

    purpose: ModelPurpose
    prompt: PromptRef
    question_id: str
    system_text: str
    settings: ModelSettings
    user_object: dict[str, object]


def _prepare(inputs: object, purpose: ModelPurpose) -> _Prepared:
    """Steps 1 and 2 of M5c-F: rebuild every input, apply the prompt binding and the stage's
    identity checks, build the user object and check its Unicode."""
    user_object: dict[str, object]
    if purpose is ModelPurpose.VERIFIER:
        require(type(inputs) is VerifierRequestInputs)
        assert isinstance(inputs, VerifierRequestInputs)
        verifier = VerifierRequestInputs(
            evidence=inputs.evidence,
            prompt=inputs.prompt,
            system_text=inputs.system_text,
            settings=inputs.settings,
        )
        prompt, system_text, settings = verifier.prompt, verifier.system_text, verifier.settings
        require(_is_bound(prompt, purpose, system_text))
        question_id = verifier.evidence.question.question_id
        user_object = _verifier_object(verifier.evidence)
    else:
        require(type(inputs) is AnalystRequestInputs)
        assert isinstance(inputs, AnalystRequestInputs)
        analyst = AnalystRequestInputs(
            owner=inputs.owner,
            question=inputs.question,
            prompt=inputs.prompt,
            system_text=inputs.system_text,
            settings=inputs.settings,
        )
        prompt, system_text, settings = analyst.prompt, analyst.system_text, analyst.settings
        require(_is_bound(prompt, purpose, system_text))
        question_id = analyst.question.question_id
        require(analyst.owner.question_id == question_id)
        require(analyst.owner.verification.question_id == question_id)
        user_object = _analyst_object(analyst.owner, analyst.question)
    require(_all_encodable(user_object))
    return _Prepared(purpose, prompt.ref, question_id, system_text, settings, user_object)


def _serialized(user_object: dict[str, object]) -> str:
    return json.dumps(
        user_object, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _finish(prepared: _Prepared, user_object: dict[str, object]) -> StructuredRequest:
    """Steps 3 and 4: serialize, refuse an oversize user text, construct the request."""
    user_text = _serialized(user_object)
    if len(user_text.encode("utf-8", errors="strict")) > MAX_USER_TEXT_BYTES:
        raise RequestTooLargeError
    return StructuredRequest(
        purpose=prepared.purpose,
        prompt=prepared.prompt,
        model_id=prepared.settings.model_id,
        question_id=prepared.question_id,
        system_text=prepared.system_text,
        user_text=user_text,
        max_output_tokens=prepared.settings.max_output_tokens,
        timeout_ms=prepared.settings.timeout_ms,
    )


def assemble_verifier_request(inputs: VerifierRequestInputs) -> StructuredRequest:
    """Build the ``eg-verifier-input-v1`` request. Invalid or mismatched inputs are
    ``InvalidAssemblyInputError``; a user text above 400,000 bytes is ``RequestTooLargeError``
    and no request is created."""

    def build() -> StructuredRequest:
        prepared = _prepare(inputs, ModelPurpose.VERIFIER)
        return _finish(prepared, prepared.user_object)

    return run_guarded(build, InvalidAssemblyInputError, keep=(RequestTooLargeError,))


def assemble_analyst_request(inputs: AnalystRequestInputs) -> StructuredRequest:
    """Build the ``eg-analyst-input-v1`` request from validated Verifier values only. Errors as
    for ``assemble_verifier_request``."""

    def build() -> StructuredRequest:
        prepared = _prepare(inputs, ModelPurpose.RISK_ANALYST)
        return _finish(prepared, prepared.user_object)

    return run_guarded(build, InvalidAssemblyInputError, keep=(RequestTooLargeError,))


def assemble_repair_request(
    original: StructuredRequest,
    inputs: VerifierRequestInputs | AnalystRequestInputs,
    reason: RepairReason,
) -> StructuredRequest:
    """Build one repair request by reassembly (M5c-F5): rebuild ``original``, ``inputs`` and
    ``reason``; reassemble the unrepaired request from ``inputs`` and require it to equal
    ``original`` in every field (so an already-repaired request is rejected); then add the
    closed ``repair`` member and keep the purpose, prompt, system text, model, question, token
    limit and timeout. Mismatches are ``InvalidAssemblyInputError``; an oversize repaired text
    is ``RequestTooLargeError``. The lifetime repair budget is not known or enforced here."""

    def build() -> StructuredRequest:
        checked_original = _rebuilt_request(original)
        if type(inputs) is VerifierRequestInputs:
            purpose = ModelPurpose.VERIFIER
        else:
            require(type(inputs) is AnalystRequestInputs)
            purpose = ModelPurpose.RISK_ANALYST
        checked_reason = _rebuilt_reason(reason)
        require(checked_original.purpose is purpose and checked_reason.purpose is purpose)
        require(checked_reason.question_id == checked_original.question_id)
        prepared = _prepare(inputs, purpose)
        require(_finish(prepared, prepared.user_object) == checked_original)
        repaired = dict(prepared.user_object)
        repaired["repair"] = {
            "citation_index": checked_reason.citation_index,
            "item_index": checked_reason.item_index,
            "reason": checked_reason.code.value,
        }
        return _finish(prepared, repaired)

    return run_guarded(build, InvalidAssemblyInputError, keep=(RequestTooLargeError,))
