"""API-key primitives and the persistence authenticator, without a database.

The authenticator is exercised through a recording session double, so these tests check its
decisions and its session handling. Real PostgreSQL behaviour is in
``test_persistence_postgres.py``.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from evidenceguard_domain.context import ActorContext, Role
from evidenceguard_persistence.auth import ROLE_MAP, ApiKeyAuthenticator
from evidenceguard_persistence.credentials import (
    KEY_LENGTH,
    PREFIX_LENGTH,
    SECRET_LENGTH,
    generate_api_key,
    is_valid_prefix,
    parse_api_key,
    secret_sha256,
)
from evidenceguard_persistence.models import UserRole

# --- format and generation --------------------------------------------------------------


def test_generated_key_has_the_documented_format() -> None:
    key = generate_api_key()
    plaintext = key.plaintext.get_secret_value()

    assert len(plaintext) == KEY_LENGTH == 64
    marker, prefix, secret = plaintext[:3], plaintext[4:20], plaintext[21:]
    assert (marker, plaintext[3], plaintext[20]) == ("egk", "_", "_")
    assert prefix == key.prefix and len(prefix) == PREFIX_LENGTH and is_valid_prefix(prefix)
    assert len(secret) == SECRET_LENGTH
    assert key.secret_sha256 == secret_sha256(secret)
    parsed = parse_api_key(plaintext)
    assert parsed is not None and parsed.prefix == prefix


def test_generated_keys_are_unique_and_prefix_is_separate_randomness() -> None:
    keys = [generate_api_key() for _ in range(200)]
    plaintexts = {key.plaintext.get_secret_value() for key in keys}
    prefixes = {key.prefix for key in keys}

    assert len(plaintexts) == len(prefixes) == 200
    for key in keys:
        assert key.prefix not in key.plaintext.get_secret_value()[21:]


def test_secret_carries_256_bits() -> None:
    # 43 URL-safe base64 characters encode 32 random bytes (secrets.token_urlsafe(32)).
    assert SECRET_LENGTH * 6 >= 256


def test_representations_never_reveal_the_secret() -> None:
    key = generate_api_key()
    plaintext = key.plaintext.get_secret_value()
    parsed = parse_api_key(plaintext)
    assert parsed is not None
    secret = parsed.secret.get_secret_value()

    for text in (repr(key), str(key), repr(parsed), str(parsed), f"{key}", f"{parsed!r}"):
        assert plaintext not in text
        assert secret not in text
        assert key.secret_sha256 not in text


def _valid() -> str:
    return generate_api_key().plaintext.get_secret_value()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda k: "",
        lambda k: k[:-1],
        lambda k: k + "A",
        lambda k: "EGK" + k[3:],
        lambda k: "egx" + k[3:],
        lambda k: k[:3] + "-" + k[4:],
        lambda k: k[:20] + "-" + k[21:],
        lambda k: k[:4] + k[4:20].upper() + k[20:],
        lambda k: k[:4] + "g" + k[5:],
        lambda k: k[:30] + "=" + k[31:],
        lambda k: k[:30] + " " + k[31:],
        lambda k: k[:30] + "é" + k[31:],
        lambda k: " " + k[1:],
        lambda k: k * 100,
    ],
)
def test_malformed_keys_are_rejected(mutate: Any) -> None:
    assert parse_api_key(mutate(_valid())) is None


def test_prefix_validation() -> None:
    assert is_valid_prefix("0123456789abcdef")
    for bad in ("", "0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "g" * 16):
        assert not is_valid_prefix(bad)


# --- authenticator ----------------------------------------------------------------------


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[Any, ...] | None:
        return self._row


class _Session:
    def __init__(self, row: tuple[Any, ...] | None, error: Exception | None) -> None:
        self.row, self.error = row, error
        self.statements: list[Any] = []
        self.closed = False

    def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error
        return _Result(self.row)

    def close(self) -> None:
        self.closed = True


class _SessionFactory:
    def __init__(self, row: tuple[Any, ...] | None = None, error: Exception | None = None):
        self.row, self.error = row, error
        self.sessions: list[_Session] = []

    def __call__(self) -> _Session:
        session = _Session(self.row, self.error)
        self.sessions.append(session)
        return session


TENANT = UUID("11111111-1111-4111-8111-111111111111")
USER = UUID("22222222-2222-4222-8222-222222222222")


def _row(key_plaintext: str, *, role: str = "approver", revoked: bool = False) -> tuple[Any, ...]:
    secret = key_plaintext[21:]
    revoked_at = datetime(2026, 10, 12, tzinfo=UTC) if revoked else None
    return (secret_sha256(secret), revoked_at, TENANT, USER, role)


def _authenticate(factory: _SessionFactory, credential: str) -> ActorContext | None:
    return ApiKeyAuthenticator(factory)(credential)  # type: ignore[arg-type]


def test_valid_key_maps_stored_tenant_user_and_role() -> None:
    key = _valid()
    factory = _SessionFactory(row=_row(key, role="approver"))

    actor = _authenticate(factory, key)

    assert actor == ActorContext(tenant_id=TENANT, actor_id=USER, role=Role.APPROVER)
    (session,) = factory.sessions
    assert session.closed


def test_lookup_is_by_prefix_and_joins_user_on_tenant_and_id() -> None:
    key = _valid()
    factory = _SessionFactory(row=_row(key))
    _authenticate(factory, key)

    (statement,) = factory.sessions[0].statements
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    sql = " ".join(str(compiled).split())
    assert (
        "JOIN users ON users.tenant_id = api_keys.tenant_id AND users.id = api_keys.user_id" in sql
    )
    assert "WHERE api_keys.prefix = %(prefix_1)s" in sql
    assert compiled.params == {"prefix_1": key[4:20]}


@pytest.mark.parametrize("stored", [role.value for role in UserRole])
def test_every_stored_role_maps_explicitly(stored: str) -> None:
    key = _valid()
    actor = _authenticate(_SessionFactory(row=_row(key, role=stored)), key)

    assert actor is not None and actor.role.value == stored
    assert ROLE_MAP[stored].value == stored


def test_wrong_secret_is_rejected() -> None:
    key = _valid()
    other = key[:21] + _valid()[21:]
    factory = _SessionFactory(row=_row(key))

    assert _authenticate(factory, other) is None
    assert factory.sessions[0].closed


def test_unknown_prefix_is_rejected() -> None:
    factory = _SessionFactory(row=None)

    assert _authenticate(factory, _valid()) is None
    assert factory.sessions[0].closed


def test_revoked_key_is_rejected() -> None:
    key = _valid()
    factory = _SessionFactory(row=_row(key, revoked=True))

    assert _authenticate(factory, key) is None
    assert factory.sessions[0].closed


def test_unmapped_stored_role_is_rejected() -> None:
    key = _valid()
    assert _authenticate(_SessionFactory(row=_row(key, role="superuser")), key) is None


def test_malformed_credential_never_opens_a_session() -> None:
    factory = _SessionFactory(row=None)

    assert _authenticate(factory, "egk_not-a-key") is None
    assert _authenticate(factory, "x" * 10_000) is None
    assert factory.sessions == []


def test_session_is_closed_when_the_query_fails() -> None:
    factory = _SessionFactory(error=OperationalError("SELECT", {}, Exception("db down")))

    with pytest.raises(OperationalError):
        _authenticate(factory, _valid())
    assert factory.sessions[0].closed


def test_each_call_reads_current_records_without_caching() -> None:
    key = _valid()
    factory = _SessionFactory(row=_row(key, role="reviewer"))
    authenticator = ApiKeyAuthenticator(factory)  # type: ignore[arg-type]

    first = authenticator(key)
    factory.row = _row(key, role="admin")
    second = authenticator(key)
    factory.row = _row(key, role="admin", revoked=True)
    third = authenticator(key)

    assert first is not None and first.role is Role.REVIEWER
    assert second is not None and second.role is Role.ADMIN
    assert third is None
    assert len(factory.sessions) == 3 and all(s.closed for s in factory.sessions)


def test_other_tenant_identifiers_in_the_stored_row_are_what_is_returned() -> None:
    key = _valid()
    other_tenant, other_user = uuid4(), uuid4()
    row = (secret_sha256(key[21:]), None, other_tenant, other_user, "reviewer")

    actor = _authenticate(_SessionFactory(row=row), key)

    assert actor == ActorContext(tenant_id=other_tenant, actor_id=other_user, role=Role.REVIEWER)
