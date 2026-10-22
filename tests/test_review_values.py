"""Review-creation values and canonical identity (``evidenceguard_domain.reviews``, M5d-A1,
ADR-0022), without a database or network.

The canonical texts are written by hand from the accepted ``eg-review-configuration-v1`` and
``eg-review-request-v1`` encodings; their SHA-256 values are literals computed independently with
the standard library, never by calling the code under test.
"""

import dataclasses
import hashlib
import socket
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from evidenceguard_domain import reviews
from evidenceguard_domain.embeddings import EmbeddingIdentity
from evidenceguard_domain.model_calls import PromptRef
from evidenceguard_domain.retrieval import (
    RETRIEVAL_CONFIG_V1,
    PendingExclusions,
    RetrievalSnapshot,
    RevisionBinding,
)
from evidenceguard_domain.reviews import (
    CreatedReview,
    InvalidReviewRequestError,
    InvalidReviewValueError,
    ReviewConfiguration,
    ReviewRequest,
    TrustedReview,
    request_canonical_bytes,
    request_sha256,
)
from evidenceguard_retrieval.embeddings import HASH_IDENTITY

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
VENDOR = UUID("22222222-2222-4222-8222-222222222222")
REV = UUID("33333333-3333-4333-8333-333333333333")
DOC = UUID("44444444-4444-4444-8444-444444444444")
INDEX = UUID("5b7601bd-c104-574b-afc4-8e43c3da8ecc")
KEY = "review-2026-10-22.a"
TEMPLATE_SHA = "26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a"
VERIFIER = PromptRef(
    prompt_id="verifier",
    version=1,
    sha256="629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d",
)
ANALYST = PromptRef(
    prompt_id="risk_analyst",
    version=1,
    sha256="f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29",
)

# Hand-written from the accepted encodings; digests computed independently (standard library).
CONFIGURATION_BYTES = (
    b'{"analyst_prompt":{"id":"risk_analyst","sha256":'
    b'"f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29","version":1},'
    b'"canonical":"eg-review-configuration-v1","kind":"review_configuration",'
    b'"model":{"max_output_tokens":4096,"model_id":"fake-scripted-v1","timeout_ms":60000},'
    b'"retrieval_k":8,'
    b'"template":{"id":"vendor_security_review","sha256":'
    b'"26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a","version":1},'
    b'"verifier_prompt":{"id":"verifier","sha256":'
    b'"629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d","version":1}}'
)
CONFIGURATION_SHA256 = "5e4d55313303ba6d0b663df2b618dd0e4a2770fd882a9862b319fe0394e8a7e6"
REQUEST_BYTES = (
    b'{"canonical":"eg-review-request-v1",'
    b'"configuration_sha256":"5e4d55313303ba6d0b663df2b618dd0e4a2770fd882a9862b319fe0394e8a7e6",'
    b'"embedding_profile":{"algorithm_version":"ascii-word-sha256-v1","dims":1024,'
    b'"fingerprint":"ad53bb3be5d8c50909b9f984294703d572e8f1844a43c5223ef86cd4a1162376",'
    b'"model_id":"fake-hash-v1","normalization":"l2","provider_id":"offline"},'
    b'"idempotency_key":"review-2026-10-22.a","kind":"review_request",'
    b'"retrieval_config":{"config_sha256":'
    b'"d1859e0b781951cd00bdc33eba80023593391a3e16e572334a477bc692de7196",'
    b'"version":"hybrid-rrf-v1"},'
    b'"tenant_id":"11111111-1111-4111-8111-111111111111",'
    b'"vendor_id":"22222222-2222-4222-8222-222222222222"}'
)
REQUEST_SHA256 = "b3b90c0b141c67c12ffbb538a16cafcaeb86c0b577e5d433ef39469492940bdf"
OTHER_TENANT_REQUEST_SHA256 = "99f15dcda5f66555044554fc3085137fcc9e60e109ceed0be6ce6f48301a7b6d"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def configuration(**changes: Any) -> ReviewConfiguration:
    values: dict[str, Any] = {
        "template_id": "vendor_security_review",
        "template_version": 1,
        "template_sha256": TEMPLATE_SHA,
        "verifier_prompt": VERIFIER,
        "analyst_prompt": ANALYST,
        "model_id": "fake-scripted-v1",
    }
    values.update(changes)
    return ReviewConfiguration(**values)


def request(**changes: Any) -> ReviewRequest:
    values: dict[str, Any] = {
        "vendor_id": VENDOR,
        "idempotency_key": KEY,
        "identity": HASH_IDENTITY,
        "configuration": configuration(),
    }
    values.update(changes)
    return ReviewRequest(**values)


def snapshot(tenant: UUID = TENANT, vendor: UUID = VENDOR) -> RetrievalSnapshot:
    from evidenceguard_domain.embedding_storage import index_id, profile_id

    profile = profile_id(tenant, HASH_IDENTITY.fingerprint)
    binding = RevisionBinding(
        REV, DOC, index_id(tenant, REV, "md-v1", profile), "md-v1", 2, "a" * 64, "b" * 64
    )
    return RetrievalSnapshot(
        tenant,
        vendor,
        HASH_IDENTITY,
        RETRIEVAL_CONFIG_V1,
        (binding,),
        PendingExclusions(0, (), False),
        datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC),
    )


def assert_fixed(error: BaseException, code: str) -> None:
    assert str(error) == code and error.args == (code,)
    assert error.__cause__ is None and error.__context__ is None


# --- configuration -------------------------------------------------------------------------------


def test_configuration_canonical_bytes_and_digest_are_pinned() -> None:
    assert hashlib.sha256(CONFIGURATION_BYTES).hexdigest() == CONFIGURATION_SHA256
    value = configuration()
    assert value.canonical_bytes() == CONFIGURATION_BYTES
    assert value.configuration_sha256 == CONFIGURATION_SHA256
    assert (value.max_output_tokens, value.timeout_ms, value.retrieval_k) == (4096, 60000, 8)


def test_every_pinned_setting_changes_the_configuration_digest() -> None:
    base = configuration().configuration_sha256
    for changes in (
        {"template_version": 2},
        {"template_sha256": "0" * 64},
        {"verifier_prompt": PromptRef(prompt_id="verifier", version=2, sha256="1" * 64)},
        {"analyst_prompt": PromptRef(prompt_id="risk_analyst", version=1, sha256="2" * 64)},
        {"model_id": "model-b"},
        {"max_output_tokens": 2048},
        {"timeout_ms": 30000},
        {"retrieval_k": 9},
    ):
        assert configuration(**changes).configuration_sha256 != base


@pytest.mark.parametrize(
    "changes",
    [
        {"template_id": "Vendor"},
        {"template_id": "9vendor"},
        {"template_id": "a" * 33},
        {"template_version": 0},
        {"template_version": 1000},
        {"template_version": True},
        {"template_sha256": "A" * 64},
        {"template_sha256": "a" * 63},
        {"verifier_prompt": ("verifier", 1, "a" * 64)},
        {"analyst_prompt": VERIFIER},  # same prompt ID twice
        {"model_id": "Model A"},
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
        {"max_output_tokens": True},
        {"timeout_ms": 999},
        {"timeout_ms": 120001},
        {"retrieval_k": 0},
        {"retrieval_k": 21},
        {"retrieval_k": 8.0},
        {"extra": 1},
    ],
)
def test_configuration_bounds(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidReviewValueError) as caught:
        configuration(**changes)
    assert_fixed(caught.value, "invalid_review_value")


def test_configuration_limits_are_inclusive_and_replacement_is_validated() -> None:
    assert configuration(max_output_tokens=1, timeout_ms=1000, retrieval_k=1)
    assert configuration(max_output_tokens=8192, timeout_ms=120000, retrieval_k=20)
    assert configuration(template_version=999, template_id="a" * 32)
    value = configuration()
    assert dataclasses.replace(value, retrieval_k=9).retrieval_k == 9
    with pytest.raises(InvalidReviewValueError):
        dataclasses.replace(value, retrieval_k=0)


def test_bypass_built_nested_prompt_references_are_revalidated() -> None:
    bad = PromptRef(prompt_id="verifier", version=1, sha256="a" * 64)
    object.__setattr__(bad, "version", 0)
    with pytest.raises(InvalidReviewValueError):
        configuration(verifier_prompt=bad)


# --- request and tenant binding ------------------------------------------------------------------


def test_request_canonical_bytes_and_digest_are_pinned_and_tenant_bound() -> None:
    assert hashlib.sha256(REQUEST_BYTES).hexdigest() == REQUEST_SHA256
    value = request()
    assert request_canonical_bytes(value, tenant_id=TENANT) == REQUEST_BYTES
    assert request_sha256(value, tenant_id=TENANT) == REQUEST_SHA256
    assert request_sha256(value, tenant_id=OTHER_TENANT) == OTHER_TENANT_REQUEST_SHA256
    assert REQUEST_SHA256 != OTHER_TENANT_REQUEST_SHA256


def test_the_request_digest_is_not_an_argument_free_property() -> None:
    value = request()
    assert not hasattr(value, "request_sha256") and not hasattr(value, "tenant_id")
    for tenant in (None, str(TENANT), TENANT.int):
        with pytest.raises(InvalidReviewRequestError) as caught:
            request_sha256(value, tenant_id=tenant)  # type: ignore[arg-type]
        assert_fixed(caught.value, "invalid_review_request")
    with pytest.raises(InvalidReviewRequestError):
        request_sha256("request", tenant_id=TENANT)  # type: ignore[arg-type]


def test_logical_identity_excludes_nothing_pinned_and_includes_no_generated_value() -> None:
    base = request_sha256(request(), tenant_id=TENANT)
    assert request_sha256(request(idempotency_key="other-key"), tenant_id=TENANT) != base
    assert request_sha256(request(vendor_id=UUID(int=5)), tenant_id=TENANT) != base
    timeout = request(configuration=configuration(timeout_ms=30000))
    assert request_sha256(timeout, tenant_id=TENANT) != base
    k = request(configuration=configuration(retrieval_k=9))
    assert request_sha256(k, tenant_id=TENANT) != base
    for word in (b"captured_at", b"snapshot", b"review_id", b"job_id"):
        assert word not in REQUEST_BYTES


@pytest.mark.parametrize(
    "changes",
    [
        {"vendor_id": str(VENDOR)},
        {"idempotency_key": ""},
        {"idempotency_key": "-leading"},
        {"idempotency_key": "has space"},
        {"idempotency_key": "a" * 129},
        {"idempotency_key": "café"},
        {"identity": EmbeddingIdentity("offline", "m", "a", 512, "l2")},
        {"identity": ("offline",)},
        {"configuration": "configuration"},
        {"extra": 1},
    ],
)
def test_request_bounds(changes: dict[str, Any]) -> None:
    with pytest.raises(InvalidReviewValueError):
        request(**changes)


def test_request_config_must_be_v1_and_key_never_appears_in_representations() -> None:
    assert request(idempotency_key="a" * 128)
    config = dataclasses.replace(RETRIEVAL_CONFIG_V1)
    object.__setattr__(config, "default_k", 7)
    with pytest.raises(InvalidReviewValueError):
        request(config=config)
    value = request()
    assert KEY not in repr(value) and KEY not in str(value)
    with pytest.raises(InvalidReviewValueError) as caught:
        request(idempotency_key="bad key")
    assert "bad key" not in str(caught.value)


# --- results -------------------------------------------------------------------------------------


def created(**changes: Any) -> CreatedReview:
    values: dict[str, Any] = {
        "review_id": UUID(int=10),
        "tenant_id": TENANT,
        "vendor_id": VENDOR,
        "request_sha256": REQUEST_SHA256,
        "snapshot_sha256": "c" * 64,
        "configuration_sha256": CONFIGURATION_SHA256,
        "captured_at": datetime(2026, 10, 22, 9, 30, tzinfo=UTC),
        "job_id": UUID(int=11),
        "replayed": False,
    }
    values.update(changes)
    return CreatedReview(**values)


def test_created_review_normalizes_to_utc_and_validates() -> None:
    plus_two = timezone(timedelta(hours=2))
    value = created(captured_at=datetime(2026, 10, 22, 11, 30, tzinfo=plus_two))
    assert value.captured_at == datetime(2026, 10, 22, 9, 30, tzinfo=UTC)
    assert value.captured_at.tzinfo is UTC
    for changes in (
        {"captured_at": datetime(2026, 10, 22, 9, 30)},
        {"replayed": 0},
        {"job_id": str(UUID(int=11))},
        {"snapshot_sha256": "x" * 64},
        {"extra": True},
    ):
        with pytest.raises(InvalidReviewValueError):
            created(**changes)


def trusted(**changes: Any) -> TrustedReview:
    values: dict[str, Any] = {
        "review_id": UUID(int=10),
        "tenant_id": TENANT,
        "request": request(),
        "request_sha256": REQUEST_SHA256,
        "snapshot": snapshot(),
        "job_id": UUID(int=11),
    }
    values.update(changes)
    return TrustedReview(**values)


def test_trusted_review_cross_field_consistency() -> None:
    value = trusted()
    assert value.request_sha256 == REQUEST_SHA256 and value.snapshot == snapshot()
    assert KEY not in repr(value)
    for changes in (
        {"request_sha256": OTHER_TENANT_REQUEST_SHA256},  # bound to another tenant
        {"tenant_id": OTHER_TENANT},  # snapshot and digest disagree with the tenant
        {"snapshot": snapshot(vendor=UUID(int=5))},
        {"request": request(vendor_id=UUID(int=5))},
        {"snapshot": "snapshot"},
    ):
        with pytest.raises(InvalidReviewValueError):
            trusted(**changes)
    tampered = snapshot()
    object.__setattr__(tampered, "captured_at", datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(InvalidReviewValueError):
        trusted(snapshot=tampered)


class Stop(KeyboardInterrupt):
    pass


def test_process_control_propagates_as_the_same_object(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = Stop()

    def interrupt(*args: object, **kwargs: object) -> None:
        raise marker

    monkeypatch.setattr(reviews, "is_model_id", interrupt)
    with pytest.raises(Stop) as caught:
        configuration()
    assert caught.value is marker
