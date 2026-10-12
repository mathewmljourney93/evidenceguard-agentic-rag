"""Documents and their revisions: pure values and lifecycle rules (M3c, ADR-0009).

Nothing here reads a clock or a database. Callers pass the current time explicitly (a fresh
PostgreSQL ``clock_timestamp()`` in practice); every time-dependent rule rejects a naive value.

Lifecycle (§4 of the plan, correction B):

- a revision is created ``pending``; ``start_processing`` makes it ``processing`` (repeating it
  under a newly claimed job attempt is a no-op);
- ``fail`` makes a ``pending`` or ``processing`` revision ``failed`` (a terminal state);
- ``settle`` decides a ``processing`` revision against the document's **currently active**
  revision: with none, or with an older one, the target becomes ``active`` and the old one
  ``superseded`` by it; with a newer one, the target goes straight to ``superseded`` by that
  newer revision and the active revision is untouched;
- ``failed`` and ``superseded`` are terminal; nothing returns to ``pending``.

A failed replacement never touches the active revision: ``fail`` changes only its own row.

Values are immutable. ``DocumentSnapshot`` and ``RevisionSnapshot`` never carry document
content. ``RevisionContent`` is built only from the exact uploaded bytes and never exposes its
text in ``repr`` or in an error.

Errors carry fixed messages only: never submitted content or other values.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from evidenceguard_domain._base import DomainModel
from evidenceguard_domain.errors import DomainError
from evidenceguard_domain.evidence import Authenticity, SourceType
from evidenceguard_domain.jobs import KIND_PATTERN, require_aware

DOCUMENT_KEY_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
DOCUMENT_KEY_MAX_LENGTH = 64
TITLE_MAX_LENGTH = 200
VERSION_LABEL_MAX_LENGTH = 64
FAILURE_CODE_PATTERN = KIND_PATTERN
SHA256_PATTERN = r"^[0-9a-f]{64}$"

_DOCUMENT_KEY = re.compile(DOCUMENT_KEY_PATTERN)
_SHA256 = re.compile(SHA256_PATTERN)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class RevisionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    FAILED = "failed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


SETTLED_STATUSES = frozenset({RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED})


class RevisionFailureCode(StrEnum):
    """Fixed codes stored in ``failure_reason``. Distinct from ``JobErrorCode``."""

    INGESTION_FAILED = "ingestion_failed"


class MediaType(StrEnum):
    """The media types v1 accepts (M3d parses them)."""

    TEXT_MARKDOWN = "text/markdown"
    TEXT_PLAIN = "text/plain"


# --- errors ------------------------------------------------------------------------------


class InvalidRevisionContentError(DomainError, ValueError):
    """The content is not acceptable. The message never contains any of it."""

    def __init__(self) -> None:
        super().__init__(
            "revision content must be non-empty strict UTF-8 text without NUL characters, of a "
            "supported media type, whose hash and size match its exact bytes"
        )


class InvalidRevisionTransitionError(DomainError):
    """The revision's state does not allow this transition. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the revision's state does not allow this transition")


class InconsistentDocumentStateError(DomainError):
    """A document's active pointer and its active revision disagree. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__("the document's active revision is inconsistent")


# --- input validation ----------------------------------------------------------------------


def validate_document_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > DOCUMENT_KEY_MAX_LENGTH
        or _DOCUMENT_KEY.fullmatch(value) is None
    ):
        raise ValueError(
            "document_key must be 1-64 lowercase letters and digits, joined by single hyphens"
        )
    return value


def validate_title(value: Any) -> str:
    """Accepted as given (never rewritten): 1-200 characters, not blank, no control
    characters."""
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= TITLE_MAX_LENGTH
        or not value.strip()
        or _CONTROL.search(value) is not None
    ):
        raise ValueError("title must be 1-200 characters, not blank, without control characters")
    return value


def validate_version_label(value: Any) -> str | None:
    """``None``, or 1-64 characters, not blank, no control characters; never rewritten."""
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= VERSION_LABEL_MAX_LENGTH
        or not value.strip()
        or _CONTROL.search(value) is not None
    ):
        raise ValueError(
            "version_label must be 1-64 characters, not blank, without control characters"
        )
    return value


# --- content -------------------------------------------------------------------------------


class RevisionContent:
    """The exact uploaded bytes of a revision, decoded and fingerprinted.

    Build it with ``from_bytes`` (new content) or ``from_stored`` (a stored row, re-verified).
    The text is the bytes decoded as strict UTF-8, with **no normalization** of newlines, a BOM
    or Unicode, and ``sha256`` and ``byte_size`` describe those same bytes. The value is
    immutable and its ``repr`` shows only the media type and size, never the text.
    """

    __slots__ = ("_byte_size", "_media_type", "_sha256", "_text")

    _media_type: MediaType
    _text: str
    _sha256: str
    _byte_size: int

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("use RevisionContent.from_bytes or RevisionContent.from_stored")

    @classmethod
    def _create(cls, media_type: MediaType, text: str, sha256: str, byte_size: int) -> Self:
        value = object.__new__(cls)
        object.__setattr__(value, "_media_type", media_type)
        object.__setattr__(value, "_text", text)
        object.__setattr__(value, "_sha256", sha256)
        object.__setattr__(value, "_byte_size", byte_size)
        return value

    @classmethod
    def from_bytes(cls, data: bytes, media_type: Any) -> Self:
        """Validate the exact uploaded bytes and derive the hash and size from them."""
        if not isinstance(data, bytes | bytearray) or not data:
            raise InvalidRevisionContentError()
        media = _media_type(media_type)
        raw = bytes(data)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise InvalidRevisionContentError() from None
        if "\x00" in text:
            raise InvalidRevisionContentError()
        return cls._create(media, text, hashlib.sha256(raw).hexdigest(), len(raw))

    @classmethod
    def from_stored(
        cls, *, media_type: Any, content_text: Any, sha256: Any, byte_size: Any
    ) -> Self:
        """Rebuild from stored fields and re-verify them: the text is re-encoded as UTF-8 and
        its hash and size must equal the stored ones."""
        if not isinstance(content_text, str) or not isinstance(sha256, str):
            raise InvalidRevisionContentError()
        try:
            data = content_text.encode("utf-8", errors="strict")
        except UnicodeEncodeError:  # e.g. lone surrogates
            raise InvalidRevisionContentError() from None
        content = cls.from_bytes(data, media_type)
        if content.sha256 != sha256 or content.byte_size != byte_size:
            raise InvalidRevisionContentError()
        return content

    @property
    def media_type(self) -> MediaType:
        return self._media_type

    @property
    def text(self) -> str:
        return self._text

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def byte_size(self) -> int:
        return self._byte_size

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("RevisionContent is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("RevisionContent is immutable")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RevisionContent):
            return NotImplemented
        return (self._media_type, self._sha256, self._byte_size, self._text) == (
            other._media_type,
            other._sha256,
            other._byte_size,
            other._text,
        )

    def __hash__(self) -> int:
        return hash((self._media_type, self._sha256, self._byte_size))

    def __repr__(self) -> str:
        return (
            f"RevisionContent(media_type={self._media_type.value!r}, byte_size={self._byte_size})"
        )

    __str__ = __repr__


def _media_type(value: Any) -> MediaType:
    try:
        return MediaType(value)
    except ValueError:
        raise InvalidRevisionContentError() from None


# --- snapshots ---------------------------------------------------------------------------


class _ExactModel(DomainModel):
    """A domain value whose strings are stored exactly as given (never stripped)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)


class DocumentSnapshot(_ExactModel):
    """A document as read from the database. Immutable; it never holds content."""

    id: UUID
    tenant_id: UUID
    vendor_id: UUID
    document_key: str
    title: str
    source_type: SourceType
    authenticity: Authenticity = Authenticity.NOT_ESTABLISHED
    latest_revision_no: int = Field(ge=0)
    active_revision_id: UUID | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("document_key", mode="before")
    @classmethod
    def _check_key(cls, value: Any) -> str:
        return validate_document_key(value)

    @field_validator("title", mode="before")
    @classmethod
    def _check_title(cls, value: Any) -> str:
        return validate_title(value)


class RevisionSnapshot(_ExactModel):
    """A revision as read from the database: metadata and state, never its content."""

    id: UUID
    tenant_id: UUID
    document_id: UUID
    revision_no: int = Field(ge=1)
    version_label: str | None = None
    effective_date: date | None = None
    status: RevisionStatus
    failure_reason: RevisionFailureCode | None = None
    sha256: str
    media_type: MediaType
    byte_size: int = Field(ge=1)
    activated_at: AwareDatetime | None = None
    failed_at: AwareDatetime | None = None
    superseded_at: AwareDatetime | None = None
    superseded_by_revision_id: UUID | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @field_validator("version_label", mode="before")
    @classmethod
    def _check_label(cls, value: Any) -> str | None:
        return validate_version_label(value)

    @field_validator("sha256", mode="before")
    @classmethod
    def _check_sha(cls, value: Any) -> str:
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def _check_state(self) -> Self:
        """The same rules as the database's named state checks."""
        failed = self.status is RevisionStatus.FAILED
        superseded = self.status is RevisionStatus.SUPERSEDED
        if failed != (self.failure_reason is not None) or failed != (self.failed_at is not None):
            raise ValueError("failure_reason and failed_at are set exactly for failed revisions")
        if superseded != (self.superseded_at is not None) or superseded != (
            self.superseded_by_revision_id is not None
        ):
            raise ValueError("supersession fields are set exactly for superseded revisions")
        if self.status is RevisionStatus.ACTIVE and self.activated_at is None:
            raise ValueError("an active revision has activated_at")
        if (
            self.status
            in {RevisionStatus.PENDING, RevisionStatus.PROCESSING, RevisionStatus.FAILED}
            and self.activated_at is not None
        ):
            raise ValueError("only active or superseded revisions may have activated_at")
        if self.superseded_by_revision_id == self.id:
            raise ValueError("a revision cannot supersede itself")
        return self

    @property
    def is_settled(self) -> bool:
        return self.status in SETTLED_STATUSES


# --- rules -----------------------------------------------------------------------------------


def next_revision_no(document: DocumentSnapshot) -> int:
    """The number for a new revision. The caller holds the document lock."""
    return document.latest_revision_no + 1


def start_processing(revision: RevisionSnapshot, *, now: datetime) -> RevisionSnapshot:
    """``pending`` → ``processing``; repeating it while ``processing`` is a no-op."""
    require_aware(now)
    if revision.status is RevisionStatus.PROCESSING:
        return revision
    if revision.status is not RevisionStatus.PENDING:
        raise InvalidRevisionTransitionError()
    return revision.model_copy(update={"status": RevisionStatus.PROCESSING, "updated_at": now})


def fail(
    revision: RevisionSnapshot, code: RevisionFailureCode, *, now: datetime
) -> RevisionSnapshot:
    """``pending`` or ``processing`` → ``failed``. Repeating it with the same code is a no-op;
    a different code is refused."""
    require_aware(now)
    if not isinstance(code, RevisionFailureCode):
        raise TypeError("code must be a RevisionFailureCode")
    if revision.status is RevisionStatus.FAILED:
        if revision.failure_reason is code:
            return revision
        raise InvalidRevisionTransitionError()
    if revision.status not in {RevisionStatus.PENDING, RevisionStatus.PROCESSING}:
        raise InvalidRevisionTransitionError()
    return revision.model_copy(
        update={
            "status": RevisionStatus.FAILED,
            "failure_reason": code,
            "failed_at": now,
            "updated_at": now,
        }
    )


@dataclass(frozen=True)
class Settlement:
    """The result of ``settle``: the writes to make, in this order.

    ``demoted`` (the previously active revision, now superseded), then ``target``, then
    ``document`` (the new pointer). A ``None`` entry, or an unchanged target, means "do not
    write". ``changed`` is false for a duplicate activation, which writes nothing at all.
    """

    target: RevisionSnapshot
    demoted: RevisionSnapshot | None
    document: DocumentSnapshot | None
    changed: bool


def settle(
    document: DocumentSnapshot,
    target: RevisionSnapshot,
    active: RevisionSnapshot | None,
    *,
    now: datetime,
) -> Settlement:
    """Decide ``target`` against the document's **currently active** revision ``active``."""
    require_aware(now)
    _require_consistent(document, target, active)
    if target.is_settled:
        return Settlement(target=target, demoted=None, document=None, changed=False)
    if target.status is not RevisionStatus.PROCESSING:
        raise InvalidRevisionTransitionError()

    if active is not None and active.revision_no > target.revision_no:
        late = target.model_copy(
            update={
                "status": RevisionStatus.SUPERSEDED,
                "superseded_at": now,
                "superseded_by_revision_id": active.id,
                "updated_at": now,
            }
        )
        return Settlement(target=late, demoted=None, document=None, changed=True)

    demoted = None
    if active is not None:
        demoted = active.model_copy(
            update={
                "status": RevisionStatus.SUPERSEDED,
                "superseded_at": now,
                "superseded_by_revision_id": target.id,
                "updated_at": now,
            }
        )
    promoted = target.model_copy(
        update={"status": RevisionStatus.ACTIVE, "activated_at": now, "updated_at": now}
    )
    pointer = document.model_copy(update={"active_revision_id": target.id, "updated_at": now})
    return Settlement(target=promoted, demoted=demoted, document=pointer, changed=True)


def _require_consistent(
    document: DocumentSnapshot, target: RevisionSnapshot, active: RevisionSnapshot | None
) -> None:
    """Refuse any combination the locked rows could not legitimately form, before ``settle``
    returns a no-op or builds a transition.

    - the target belongs to the document, and its number was allocated by it;
    - an active snapshot is given exactly when the document has an active pointer, and it is the
      pointed-to ``active`` revision of the same tenant and document, with an allocated number;
    - an ``active`` target is that pointed-to revision;
    - a ``processing`` target is a different revision, with a different number.
    """
    if (
        target.document_id != document.id
        or target.tenant_id != document.tenant_id
        or target.revision_no > document.latest_revision_no
    ):
        raise InconsistentDocumentStateError()
    if (active is None) != (document.active_revision_id is None):
        raise InconsistentDocumentStateError()
    if active is not None and (
        active.id != document.active_revision_id
        or active.status is not RevisionStatus.ACTIVE
        or active.document_id != document.id
        or active.tenant_id != document.tenant_id
        or active.revision_no > document.latest_revision_no
    ):
        raise InconsistentDocumentStateError()
    if target.status is RevisionStatus.ACTIVE and (active is None or target.id != active.id):
        raise InconsistentDocumentStateError()
    if (
        target.status is RevisionStatus.PROCESSING
        and active is not None
        and (target.id == active.id or target.revision_no == active.revision_no)
    ):
        raise InconsistentDocumentStateError()
