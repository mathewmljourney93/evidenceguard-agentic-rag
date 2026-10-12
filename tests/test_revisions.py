"""Pure document and revision rules (``evidenceguard_domain.revisions``, M3c, ADR-0009)."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from evidenceguard_domain.evidence import SourceType
from evidenceguard_domain.jobs import NAIVE_TIME_MESSAGE
from evidenceguard_domain.revisions import (
    DocumentSnapshot,
    InconsistentDocumentStateError,
    InvalidRevisionContentError,
    InvalidRevisionTransitionError,
    MediaType,
    RevisionContent,
    RevisionFailureCode,
    RevisionSnapshot,
    RevisionStatus,
    fail,
    next_revision_no,
    settle,
    start_processing,
    validate_document_key,
    validate_title,
    validate_version_label,
)

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)
TENANT = UUID("44444444-4444-4444-8444-444444444444")
DOCUMENT = UUID("55555555-5555-4555-8555-555555555555")
# Obviously fake marker standing in for private document text.
CONTENT_MARKER = "synthetic-private-content-marker"


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def document(**overrides: Any) -> DocumentSnapshot:
    values: dict[str, Any] = {
        "id": DOCUMENT,
        "tenant_id": TENANT,
        "vendor_id": uuid4(),
        "document_key": "data-retention-policy",
        "title": "Data retention policy",
        "source_type": SourceType.VENDOR_STATEMENT,
        "latest_revision_no": 3,
        "active_revision_id": None,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return DocumentSnapshot.model_validate(values)


def revision(status: RevisionStatus = RevisionStatus.PENDING, **overrides: Any) -> RevisionSnapshot:
    values: dict[str, Any] = {
        "id": uuid4(),
        "tenant_id": TENANT,
        "document_id": DOCUMENT,
        "revision_no": 1,
        "status": status,
        "sha256": _sha(str(uuid4())),
        "media_type": MediaType.TEXT_MARKDOWN,
        "byte_size": 10,
        "created_at": T0,
        "updated_at": T0,
    }
    if status is RevisionStatus.ACTIVE:
        values["activated_at"] = T0
    if status is RevisionStatus.FAILED:
        values.update(failure_reason=RevisionFailureCode.INGESTION_FAILED, failed_at=T0)
    if status is RevisionStatus.SUPERSEDED:
        values.update(superseded_at=T0, superseded_by_revision_id=uuid4())
    values.update(overrides)
    return RevisionSnapshot.model_validate(values)


# --- content -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"line one\nline two\n",
        b"line one\r\nline two\r\n",  # CRLF kept
        b"\xef\xbb\xbfwith a byte-order mark",  # BOM kept
        "caf\u00e9 and na\u00efve \U0001f600".encode(),  # non-ASCII
        "e\u0301 decomposed".encode(),  # no Unicode normalization
        b"  surrounding spaces  \n",  # no stripping
    ],
)
def test_hash_and_size_come_from_the_exact_bytes(data: bytes) -> None:
    content = RevisionContent.from_bytes(data, "text/plain")

    assert content.sha256 == hashlib.sha256(data).hexdigest()
    assert content.byte_size == len(data)
    assert content.text.encode("utf-8") == data
    assert content.media_type is MediaType.TEXT_PLAIN


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (b"", "text/plain"),
        (b"\xff\xfe invalid", "text/plain"),
        (b"\xc3", "text/plain"),  # truncated sequence
        (b"nul\x00inside", "text/plain"),
        (b"fine", "application/pdf"),
        (b"fine", "TEXT/PLAIN"),
    ],
)
def test_invalid_content_is_rejected_with_a_fixed_error(data: bytes, media_type: str) -> None:
    with pytest.raises(InvalidRevisionContentError) as error:
        RevisionContent.from_bytes(data, media_type)

    assert "invalid" not in str(error.value) and "nul" not in str(error.value)


def test_content_is_immutable_and_never_shown() -> None:
    content = RevisionContent.from_bytes(CONTENT_MARKER.encode(), "text/markdown")

    assert CONTENT_MARKER not in repr(content)
    assert CONTENT_MARKER not in str(content)
    with pytest.raises(AttributeError):
        content._text = "changed"
    with pytest.raises(TypeError):
        RevisionContent(b"x", "text/plain")


def test_errors_never_echo_submitted_content() -> None:
    with pytest.raises(InvalidRevisionContentError) as error:
        RevisionContent.from_bytes((CONTENT_MARKER + "\x00").encode(), "text/plain")

    assert CONTENT_MARKER not in str(error.value)
    assert CONTENT_MARKER not in repr(error.value)


def test_stored_fields_are_re_verified() -> None:
    data = "résumé\r\n".encode()
    content = RevisionContent.from_bytes(data, "text/plain")

    rebuilt = RevisionContent.from_stored(
        media_type="text/plain",
        content_text=content.text,
        sha256=content.sha256,
        byte_size=content.byte_size,
    )
    assert rebuilt == content
    for wrong in (
        {"sha256": _sha("other")},
        {"byte_size": content.byte_size + 1},
        {"content_text": content.text.strip()},
        {"content_text": "\ud800"},  # a lone surrogate cannot be encoded
    ):
        fields: dict[str, Any] = {
            "media_type": "text/plain",
            "content_text": content.text,
            "sha256": content.sha256,
            "byte_size": content.byte_size,
        }
        fields.update(wrong)
        with pytest.raises(InvalidRevisionContentError):
            RevisionContent.from_stored(**fields)


# --- input validation and snapshots ------------------------------------------------------------


@pytest.mark.parametrize("key", ["", "Upper", "two--hyphens", "-lead", "trail-", "a_b", "x" * 65])
def test_invalid_document_keys_are_rejected(key: str) -> None:
    with pytest.raises(ValueError):
        validate_document_key(key)


def test_titles_and_labels_are_kept_exactly_or_rejected() -> None:
    assert validate_title("  Policy v2  ") == "  Policy v2  "
    assert validate_version_label(None) is None
    assert validate_version_label("v2.1") == "v2.1"
    for bad in ("", "   ", "bad\x00title", "x" * 201):
        with pytest.raises(ValueError):
            validate_title(bad)
    for bad_label in ("", "  ", "tab\tlabel", "x" * 65):
        with pytest.raises(ValueError):
            validate_version_label(bad_label)


def test_snapshots_are_immutable_and_keep_strings_exactly() -> None:
    doc = document(title=" Spaced title ")

    assert doc.title == " Spaced title "
    with pytest.raises(ValidationError):
        doc.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("status", "overrides"),
    [
        (RevisionStatus.FAILED, {"failure_reason": None}),
        (RevisionStatus.FAILED, {"failed_at": None}),
        (RevisionStatus.PROCESSING, {"failed_at": T0}),
        (RevisionStatus.SUPERSEDED, {"superseded_at": None}),
        (RevisionStatus.SUPERSEDED, {"superseded_by_revision_id": None}),
        (RevisionStatus.PENDING, {"superseded_at": T0}),
        (RevisionStatus.ACTIVE, {"activated_at": None}),
        (RevisionStatus.PENDING, {"activated_at": T0}),
        (RevisionStatus.FAILED, {"activated_at": T0}),
        (RevisionStatus.PENDING, {"sha256": "ABC"}),
    ],
)
def test_partial_state_fields_are_rejected(
    status: RevisionStatus, overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        revision(status, **overrides)


def test_a_superseded_revision_may_keep_its_activation_time() -> None:
    assert revision(RevisionStatus.SUPERSEDED, activated_at=T0).activated_at == T0
    assert revision(RevisionStatus.SUPERSEDED).activated_at is None


def test_a_revision_cannot_supersede_itself() -> None:
    rid = uuid4()
    with pytest.raises(ValidationError):
        revision(RevisionStatus.SUPERSEDED, id=rid, superseded_by_revision_id=rid)


def test_next_revision_number_follows_the_counter() -> None:
    assert next_revision_no(document(latest_revision_no=0)) == 1
    assert next_revision_no(document(latest_revision_no=7)) == 8


# --- transitions ---------------------------------------------------------------------------------


def test_start_processing_moves_pending_and_repeats_as_a_no_op() -> None:
    pending = revision()
    processing = start_processing(pending, now=T1)

    assert processing.status is RevisionStatus.PROCESSING and processing.updated_at == T1
    assert start_processing(processing, now=T1 + timedelta(seconds=1)) is processing


@pytest.mark.parametrize(
    "status", [RevisionStatus.FAILED, RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED]
)
def test_start_processing_refuses_settled_or_failed(status: RevisionStatus) -> None:
    with pytest.raises(InvalidRevisionTransitionError):
        start_processing(revision(status), now=T1)


@pytest.mark.parametrize("status", [RevisionStatus.PENDING, RevisionStatus.PROCESSING])
def test_fail_records_the_fixed_code(status: RevisionStatus) -> None:
    failed = fail(revision(status), RevisionFailureCode.INGESTION_FAILED, now=T1)

    assert failed.status is RevisionStatus.FAILED
    assert failed.failure_reason is RevisionFailureCode.INGESTION_FAILED
    assert (failed.failed_at, failed.updated_at) == (T1, T1)


def test_failing_again_with_the_same_code_is_a_no_op() -> None:
    failed = revision(RevisionStatus.FAILED)

    assert fail(failed, RevisionFailureCode.INGESTION_FAILED, now=T1) is failed


@pytest.mark.parametrize("status", [RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED])
def test_settled_revisions_cannot_fail(status: RevisionStatus) -> None:
    with pytest.raises(InvalidRevisionTransitionError):
        fail(revision(status), RevisionFailureCode.INGESTION_FAILED, now=T1)


def test_fail_accepts_only_revision_failure_codes() -> None:
    with pytest.raises(TypeError):
        fail(revision(), cast(Any, "permanent_failure"), now=T1)


def test_first_activation_promotes_and_sets_the_pointer() -> None:
    target = revision(RevisionStatus.PROCESSING)

    result = settle(document(), target, None, now=T1)

    assert result.changed and result.demoted is None
    assert result.target.status is RevisionStatus.ACTIVE and result.target.activated_at == T1
    assert result.document is not None
    assert result.document.active_revision_id == target.id and result.document.updated_at == T1


def test_a_newer_revision_supersedes_the_active_one() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=1)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)

    result = settle(document(active_revision_id=active.id), target, active, now=T1)

    assert result.demoted is not None
    assert result.demoted.status is RevisionStatus.SUPERSEDED
    assert result.demoted.superseded_by_revision_id == target.id
    assert result.demoted.superseded_at == result.target.activated_at == T1
    assert result.demoted.activated_at == T0  # its earlier activation is kept
    assert result.document is not None and result.document.active_revision_id == target.id


def test_ordering_is_against_the_active_revision_not_the_latest_upload() -> None:
    # Revision 3 exists (latest_revision_no=3) but is not active: revision 2 still wins over 1.
    active = revision(RevisionStatus.ACTIVE, revision_no=1)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)

    result = settle(
        document(active_revision_id=active.id, latest_revision_no=3), target, active, now=T1
    )

    assert result.target.status is RevisionStatus.ACTIVE


def test_an_older_revision_finishing_late_is_superseded_alone() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=3)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)

    result = settle(document(active_revision_id=active.id), target, active, now=T1)

    assert result.changed and result.demoted is None and result.document is None
    assert result.target.status is RevisionStatus.SUPERSEDED
    assert result.target.superseded_by_revision_id == active.id
    assert result.target.activated_at is None


@pytest.mark.parametrize("status", [RevisionStatus.ACTIVE, RevisionStatus.SUPERSEDED])
def test_duplicate_activation_changes_nothing(status: RevisionStatus) -> None:
    target = revision(status)
    active = target if status is RevisionStatus.ACTIVE else revision(RevisionStatus.ACTIVE)
    doc = document(active_revision_id=active.id)

    result = settle(doc, target, active, now=T1)

    assert not result.changed
    assert result.target is target and result.demoted is None and result.document is None


@pytest.mark.parametrize("status", [RevisionStatus.PENDING, RevisionStatus.FAILED])
def test_only_processing_revisions_can_settle(status: RevisionStatus) -> None:
    with pytest.raises(InvalidRevisionTransitionError):
        settle(document(), revision(status), None, now=T1)


def test_inconsistent_pointers_are_refused() -> None:
    active = revision(RevisionStatus.ACTIVE)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(), target, active, now=T1)  # pointer is None
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=uuid4()), target, None, now=T1)
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(id=uuid4()), target, None, now=T1)  # another document's revision


def test_an_active_target_without_an_active_pointer_is_refused() -> None:
    # Previously accepted as a duplicate no-op.
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(), revision(RevisionStatus.ACTIVE), None, now=T1)


def test_an_active_target_must_be_the_pointed_to_revision() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=1)
    other_active = revision(RevisionStatus.ACTIVE, revision_no=2)

    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=active.id), other_active, active, now=T1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenant_id": UUID("99999999-9999-4999-8999-999999999999")},
        {"document_id": UUID("88888888-8888-4888-8888-888888888888")},
    ],
)
def test_the_active_snapshot_must_belong_to_the_document(overrides: dict[str, Any]) -> None:
    active = revision(RevisionStatus.ACTIVE, **overrides)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)

    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=active.id), target, active, now=T1)


def test_a_processing_target_cannot_share_the_active_revisions_id() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=1)
    target = revision(RevisionStatus.PROCESSING, id=active.id, revision_no=2)

    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=active.id), target, active, now=T1)


def test_a_processing_target_cannot_share_the_active_revisions_number() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=2)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)

    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=active.id), target, active, now=T1)


def test_revision_numbers_cannot_exceed_the_documents_counter() -> None:
    # document() has latest_revision_no=3.
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(), revision(RevisionStatus.PROCESSING, revision_no=4), None, now=T1)
    active = revision(RevisionStatus.ACTIVE, revision_no=4)
    target = revision(RevisionStatus.PROCESSING, revision_no=2)
    with pytest.raises(InconsistentDocumentStateError):
        settle(document(active_revision_id=active.id), target, active, now=T1)


def test_valid_retries_remain_no_ops_and_normal_activation_still_works() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=3)
    doc = document(active_revision_id=active.id)
    late = revision(RevisionStatus.SUPERSEDED, revision_no=2, superseded_by_revision_id=active.id)

    assert not settle(doc, active, active, now=T1).changed  # duplicate activation
    assert not settle(doc, late, active, now=T1).changed  # superseded retry
    first = settle(document(), revision(RevisionStatus.PROCESSING, revision_no=3), None, now=T1)
    assert first.changed and first.target.status is RevisionStatus.ACTIVE


def test_the_application_accepts_only_known_failure_codes() -> None:
    """PostgreSQL checks only the code pattern; the enum is the application's restriction."""
    with pytest.raises(ValidationError):
        revision(RevisionStatus.FAILED, failure_reason="parser_crashed")


def test_failing_a_replacement_leaves_the_active_revision_alone() -> None:
    active = revision(RevisionStatus.ACTIVE, revision_no=1)
    replacement = revision(RevisionStatus.PROCESSING, revision_no=2)

    failed = fail(replacement, RevisionFailureCode.INGESTION_FAILED, now=T1)

    assert failed.id == replacement.id and active.status is RevisionStatus.ACTIVE


def test_transitions_never_change_immutable_fields() -> None:
    target = revision(
        RevisionStatus.PROCESSING, version_label="v2", effective_date=date(2026, 1, 1)
    )
    settled = settle(document(), target, None, now=T1).target
    immutable = (
        "id",
        "tenant_id",
        "document_id",
        "revision_no",
        "version_label",
        "effective_date",
        "sha256",
        "media_type",
        "byte_size",
        "created_at",
    )
    for name in immutable:
        assert getattr(settled, name) == getattr(target, name)


def test_every_time_dependent_rule_rejects_naive_time() -> None:
    naive = datetime(2026, 10, 12, 12, 0)
    for call in (
        lambda: start_processing(revision(), now=naive),
        lambda: fail(revision(), RevisionFailureCode.INGESTION_FAILED, now=naive),
        lambda: settle(document(), revision(RevisionStatus.PROCESSING), None, now=naive),
    ):
        with pytest.raises(ValueError, match=NAIVE_TIME_MESSAGE):
            call()


def test_error_messages_are_fixed() -> None:
    assert (
        str(InvalidRevisionTransitionError())
        == "the revision's state does not allow this transition"
    )
    assert str(InconsistentDocumentStateError()) == "the document's active revision is inconsistent"
