"""Model prices ``docs/evaluation/pricing.toml`` (stdlib ``tomllib``; no new dependency).

Format::

    as_of = "YYYY-MM-DD"            # required: the day the prices were read
    source_url = "https://..."      # required: where they were read
    [models."<full dated model id>"]
    input_usd_per_mtok = 1.0
    output_usd_per_mtok = 5.0

Prices are ``Decimal`` (US dollars per million tokens), parsed from the TOML text of each number,
so no binary float rounding enters a cost. Refusals: an empty or missing ``as_of``, a
``source_url`` that is not https, a non-positive price, an unknown key, or a model without an
entry. A price list older than 30 days is accepted with a warning. The committed file has an
empty ``as_of``, so every live run refuses until the owner fills it.
"""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from evidenceguard_evaluation.config import MODEL_ID, refuse

MAX_PRICING_BYTES = 64 * 1024
STALE_AFTER_DAYS = 30
MILLION = Decimal(1_000_000)
_NUMBER = re.compile(r"^[0-9]+(\.[0-9]+)?$")


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * self.input_usd_per_mtok
            + Decimal(output_tokens) * self.output_usd_per_mtok
        ) / MILLION


@dataclass(frozen=True)
class Pricing:
    as_of: date
    source_url: str
    models: MappingProxyType[str, ModelPrice]
    digest: str

    def price(self, model: str) -> ModelPrice:
        found = self.models.get(model)
        if found is None:
            raise refuse("pricing.toml has no entry for the model")
        return found

    def is_stale(self, today: date) -> bool:
        return (today - self.as_of).days > STALE_AFTER_DAYS


def _price(value: object, name: str) -> Decimal:
    if type(value) not in (int, float, str):
        raise refuse(f"pricing.toml: {name} must be a number")
    text = str(value)
    if _NUMBER.fullmatch(text) is None:
        raise refuse(f"pricing.toml: {name} must be a positive number")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise refuse(f"pricing.toml: {name} must be a positive number") from None
    if number <= 0:
        raise refuse(f"pricing.toml: {name} must be a positive number")
    return number


def parse_pricing(data: bytes) -> Pricing:
    """Parse and validate ``pricing.toml`` bytes, or raise ``EvaluationRefusal`` (exit 3)."""
    if len(data) > MAX_PRICING_BYTES:
        raise refuse("pricing.toml is too large")
    try:
        document: dict[str, Any] = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise refuse("pricing.toml is not valid TOML") from None
    if set(document) - {"as_of", "source_url", "models"}:
        raise refuse("pricing.toml has an unknown key")
    as_of = document.get("as_of")
    if isinstance(as_of, str) and as_of:
        try:
            as_of = date.fromisoformat(as_of)
        except ValueError:
            raise refuse("pricing.toml: as_of must be an ISO date") from None
    if type(as_of) is not date:
        raise refuse("pricing.toml: as_of is required (fill it from the provider's price page)")
    source_url = document.get("source_url")
    if type(source_url) is not str or not source_url.startswith("https://") or " " in source_url:
        raise refuse("pricing.toml: source_url must be an https URL")
    models_table = document.get("models", {})
    if not isinstance(models_table, dict):
        raise refuse("pricing.toml: [models] must be a table")
    models: dict[str, ModelPrice] = {}
    for model, entry in models_table.items():
        if MODEL_ID.fullmatch(model) is None:
            raise refuse("pricing.toml has an invalid model id")
        if not isinstance(entry, dict) or set(entry) != {
            "input_usd_per_mtok",
            "output_usd_per_mtok",
        }:
            raise refuse("pricing.toml: each model needs exactly the two prices")
        models[model] = ModelPrice(
            _price(entry["input_usd_per_mtok"], "input_usd_per_mtok"),
            _price(entry["output_usd_per_mtok"], "output_usd_per_mtok"),
        )
    return Pricing(
        as_of=as_of,
        source_url=source_url,
        models=MappingProxyType(models),
        digest=hashlib.sha256(data).hexdigest(),
    )


def pricing_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
