"""API-key format, generation, parsing and digest checks. No I/O.

Key format (ADR-0005), exactly 64 ASCII characters::

    egk_<prefix>_<secret>

- ``egk_``: a fixed marker that makes keys recognisable to people and secret scanners.
- ``<prefix>``: 16 lowercase hex characters (64 random bits) from ``secrets.token_hex``. It is
  a lookup identifier, unique across all tenants, and is stored in plaintext. It is not secret.
- ``<secret>``: 43 URL-safe base64 characters (256 random bits) from ``secrets.token_urlsafe``.
  Only its SHA-256 hex digest is stored. A plain digest without salt or key stretching is
  appropriate here because the secret is uniformly random and long.

Because both parts have fixed lengths, parsing is unambiguous even though the secret alphabet
includes ``_``. Anything that does not match the exact pattern is rejected before any lookup.

Plaintext keys and secrets are only ever carried inside ``SecretStr``, whose ``repr`` and
``str`` are masked. Nothing here logs.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field

from pydantic import SecretStr

KEY_MARKER = "egk"
PREFIX_LENGTH = 16
SECRET_LENGTH = 43
KEY_LENGTH = len(KEY_MARKER) + 1 + PREFIX_LENGTH + 1 + SECRET_LENGTH
_PREFIX_BYTES = PREFIX_LENGTH // 2
_SECRET_BYTES = 32
_KEY_PATTERN = re.compile(
    rf"{KEY_MARKER}_(?P<prefix>[0-9a-f]{{{PREFIX_LENGTH}}})_(?P<secret>[A-Za-z0-9_-]{{{SECRET_LENGTH}}})"
)
_PREFIX_PATTERN = re.compile(rf"[0-9a-f]{{{PREFIX_LENGTH}}}")


@dataclass(frozen=True, slots=True)
class ParsedApiKey:
    """A syntactically valid presented key. The secret stays masked."""

    prefix: str
    secret: SecretStr


@dataclass(frozen=True, slots=True)
class NewApiKey:
    """A freshly generated key: what to store, and the plaintext to show exactly once."""

    prefix: str
    secret_sha256: str = field(repr=False)
    plaintext: SecretStr


def secret_sha256(secret: str) -> str:
    """Lowercase hex SHA-256 of the secret part of a key."""
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def generate_api_key() -> NewApiKey:
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    plaintext = f"{KEY_MARKER}_{prefix}_{secret}"
    # token_urlsafe(32) always yields 43 characters; fail loudly if that ever changes.
    if parse_api_key(plaintext) is None:
        raise RuntimeError("generated API key does not match the key format")
    return NewApiKey(
        prefix=prefix, secret_sha256=secret_sha256(secret), plaintext=SecretStr(plaintext)
    )


def parse_api_key(raw: str) -> ParsedApiKey | None:
    """Return the parsed key, or ``None`` for anything that is not exactly a valid key.

    The length is checked before the pattern, so oversized input is rejected cheaply.
    """
    if len(raw) != KEY_LENGTH:
        return None
    match = _KEY_PATTERN.fullmatch(raw)
    if match is None:
        return None
    return ParsedApiKey(prefix=match["prefix"], secret=SecretStr(match["secret"]))


def is_valid_prefix(prefix: str) -> bool:
    return _PREFIX_PATTERN.fullmatch(prefix) is not None


def digest_matches(key: ParsedApiKey, stored_sha256: str) -> bool:
    """Compare the presented secret's digest with the stored one in constant time."""
    presented = secret_sha256(key.secret.get_secret_value())
    return hmac.compare_digest(presented.encode("ascii"), stored_sha256.encode("ascii"))
