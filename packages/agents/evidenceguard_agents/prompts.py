"""Versioned system prompts: ``PromptSpec``, pinned packaged loading and the prompt binding
(M5c-B1, E, E1; ADR-0021).

Each registered prompt is one packaged Markdown file with a pinned SHA-256 of its exact bytes and
a fixed ``ModelPurpose``. ``load_prompt`` reads it with a bounded read and returns the **exact
decoded text** as the system text: no templating, substitution or trimming. The file is strict
UTF-8 without BOM, so re-encoding the text gives the same bytes and the text's SHA-256 equals the
file digest. ``load_pinned_prompt`` is the trusted production and reload path; it compares the
complete loaded reference and purpose with the review's pinned configuration.

M5a's ``StructuredRequest`` accepts any well-formed prompt reference with any system text, so the
binding between them is checked here (``_is_bound``) and applied by request assembly before any
serialization. Published prompt files are immutable: a change is a new version with a new file
and pinned digest. Nothing here reads a caller-supplied path, the environment or the network,
and nothing logs.
"""

import hashlib
from dataclasses import dataclass

from evidenceguard_agents.artifact_errors import (
    InvalidAgentArgumentError,
    InvalidAgentValueError,
    PromptIntegrityError,
    UnknownPromptError,
    require,
    run_guarded,
)
from evidenceguard_agents.templates import _read_packaged
from evidenceguard_domain.model_calls import (
    MAX_SYSTEM_TEXT_BYTES,
    ModelPurpose,
    PromptRef,
    utf8_size,
)

MAX_PROMPT_BYTES = MAX_SYSTEM_TEXT_BYTES  # 64,000

_UTF8_BOM = b"\xef\xbb\xbf"
_SHAPE_DIGEST = "0" * 64  # only used to check an ID and version shape through ``PromptRef``

# (prompt_id, version) -> (fixed relative resource name, pinned SHA-256 of the bytes, purpose)
_REGISTRY: dict[tuple[str, int], tuple[tuple[str, ...], str, ModelPurpose]] = {
    ("verifier", 1): (
        ("data", "prompts", "verifier", "v1.md"),
        "629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d",
        ModelPurpose.VERIFIER,
    ),
    ("risk_analyst", 1): (
        ("data", "prompts", "risk_analyst", "v1.md"),
        "f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29",
        ModelPurpose.RISK_ANALYST,
    ),
}


def _rebuilt_prompt_ref(value: object) -> PromptRef:
    require(type(value) is PromptRef)
    assert isinstance(value, PromptRef)
    return PromptRef(prompt_id=value.prompt_id, version=value.version, sha256=value.sha256)


@dataclass(frozen=True, init=False, repr=False)
class PromptSpec:
    """A prompt reference and its purpose. Shape only: registry membership, purpose and digest
    are checked by the loaders and by request assembly."""

    ref: PromptRef
    purpose: ModelPurpose

    def __init__(self, *, ref: PromptRef, purpose: ModelPurpose, **unknown: object) -> None:
        def build() -> None:
            require(not unknown and type(purpose) is ModelPurpose)
            checked = _rebuilt_prompt_ref(ref)
            object.__setattr__(self, "ref", checked)
            object.__setattr__(self, "purpose", purpose)

        run_guarded(build, InvalidAgentValueError)

    def __repr__(self) -> str:
        return (
            f"PromptSpec(prompt_id={self.ref.prompt_id!r}, version={self.ref.version}, "
            f"purpose={self.purpose.value!r})"
        )

    __str__ = __repr__


def _rebuilt_spec(value: object) -> PromptSpec:
    require(type(value) is PromptSpec)
    assert isinstance(value, PromptSpec)
    return PromptSpec(ref=value.ref, purpose=value.purpose)


def _load(prompt_id: object, version: object) -> tuple[PromptSpec, str]:
    if type(prompt_id) is not str or type(version) is not int:
        raise InvalidAgentArgumentError
    assert isinstance(prompt_id, str) and isinstance(version, int)
    name: str = prompt_id
    number: int = version
    shape = run_guarded(
        lambda: PromptRef(prompt_id=name, version=number, sha256=_SHAPE_DIGEST),
        InvalidAgentArgumentError,
    )
    entry = _REGISTRY.get((shape.prompt_id, shape.version))
    if entry is None:
        raise UnknownPromptError
    parts, pinned, purpose = entry
    data = _read_packaged(parts, MAX_PROMPT_BYTES)
    require(1 <= len(data) <= MAX_PROMPT_BYTES and not data.startswith(_UTF8_BOM))
    require(b"\x00" not in data and hashlib.sha256(data).hexdigest() == pinned)
    text = data.decode("utf-8", errors="strict")
    spec = PromptSpec(
        ref=PromptRef(prompt_id=shape.prompt_id, version=shape.version, sha256=pinned),
        purpose=purpose,
    )
    return spec, text


def load_prompt(prompt_id: str, version: int) -> tuple[PromptSpec, str]:
    """Load a registered packaged prompt and return its spec and exact system text. Wrong
    argument types or shapes are ``InvalidAgentArgumentError``; an unregistered pair is
    ``UnknownPromptError``; a missing, unreadable, oversize, empty, BOM-prefixed, non-UTF-8,
    NUL-bearing or altered resource is ``PromptIntegrityError``."""
    return run_guarded(
        lambda: _load(prompt_id, version),
        PromptIntegrityError,
        keep=(InvalidAgentArgumentError, UnknownPromptError),
    )


def load_pinned_prompt(ref: PromptRef, purpose: ModelPurpose) -> tuple[PromptSpec, str]:
    """The trusted production and reload path: load the prompt named by ``ref`` and require the
    complete loaded reference to equal ``ref`` and its registered purpose to equal
    ``purpose``."""

    def build() -> tuple[PromptSpec, str]:
        checked = run_guarded(lambda: _rebuilt_prompt_ref(ref), InvalidAgentArgumentError)
        if type(purpose) is not ModelPurpose:
            raise InvalidAgentArgumentError
        spec, text = load_prompt(checked.prompt_id, checked.version)
        require(spec.ref == checked and spec.purpose is purpose)
        return spec, text

    return run_guarded(
        build,
        PromptIntegrityError,
        keep=(InvalidAgentArgumentError, UnknownPromptError, PromptIntegrityError),
    )


def _is_bound(spec: PromptSpec, purpose: ModelPurpose, system_text: object) -> bool:
    """The M5c-E1 binding, steps 2-4: the spec has ``purpose``; its reference names a
    registered prompt of that purpose whose pinned digest equals the reference digest; and the
    system text is 1-64,000 strict UTF-8 bytes without NUL whose SHA-256 equals that digest."""
    if spec.purpose is not purpose:
        return False
    entry = _REGISTRY.get((spec.ref.prompt_id, spec.ref.version))
    if entry is None or entry[2] is not purpose or entry[1] != spec.ref.sha256:
        return False
    size = utf8_size(system_text)
    if size is None or not 1 <= size <= MAX_PROMPT_BYTES:
        return False
    assert isinstance(system_text, str)
    if "\x00" in system_text:
        return False
    return hashlib.sha256(system_text.encode("utf-8")).hexdigest() == spec.ref.sha256
