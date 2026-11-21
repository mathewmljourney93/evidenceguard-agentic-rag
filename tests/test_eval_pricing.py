"""M7 (ADR-0029): ``pricing.toml`` refuses without its date, source or an entry."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from evidenceguard_evaluation.config import EvaluationRefusal
from evidenceguard_evaluation.pricing import parse_pricing

ROOT = Path(__file__).resolve().parents[1]
VALID = b"""
as_of = "2026-11-01"
source_url = "https://example.invalid/pricing"
[models."model-a-20260101"]
input_usd_per_mtok = 0.8
output_usd_per_mtok = 4
"""


def test_the_committed_price_list_refuses_until_its_date_is_filled() -> None:
    data = (ROOT / "docs" / "evaluation" / "pricing.toml").read_bytes()
    assert b'as_of = ""' in data
    with pytest.raises(EvaluationRefusal, match="as_of is required"):
        parse_pricing(data)


@pytest.mark.parametrize("as_of", [b'as_of = ""\n', b"", b'as_of = "soon"\n'])
def test_a_missing_or_invalid_as_of_is_refused(as_of: bytes) -> None:
    data = VALID.replace(b'as_of = "2026-11-01"\n', as_of)
    with pytest.raises(EvaluationRefusal) as refused:
        parse_pricing(data)
    assert refused.value.exit_code == 3 and "soon" not in str(refused.value)


@pytest.mark.parametrize("url", [b"http://example.invalid/pricing", b"", b"ftp://x"])
def test_a_non_https_source_is_refused(url: bytes) -> None:
    data = VALID.replace(b"https://example.invalid/pricing", url)
    with pytest.raises(EvaluationRefusal, match="https"):
        parse_pricing(data)


def test_an_unknown_model_is_refused() -> None:
    pricing = parse_pricing(VALID)
    with pytest.raises(EvaluationRefusal, match="no entry"):
        pricing.price("model-z-20260101")


@pytest.mark.parametrize(
    "change",
    [
        (b"output_usd_per_mtok = 4", b"output_usd_per_mtok = 0"),
        (b"output_usd_per_mtok = 4", b"output_usd_per_mtok = -4"),
        (b"output_usd_per_mtok = 4", b"output_usd_per_mtok = 4\ncached = 1"),
        (b'source_url = "', b'currency = "usd"\nsource_url = "'),
    ],
)
def test_non_positive_prices_and_unknown_keys_are_refused(change: tuple[bytes, bytes]) -> None:
    with pytest.raises(EvaluationRefusal):
        parse_pricing(VALID.replace(*change))


def test_costs_use_exact_decimal_arithmetic() -> None:
    price = parse_pricing(VALID).price("model-a-20260101")
    assert price.input_usd_per_mtok == Decimal("0.8")
    assert price.cost(1_000_000, 0) == Decimal("0.8")
    assert price.cost(3, 7) == (Decimal(3) * Decimal("0.8") + Decimal(28)) / Decimal(1_000_000)
    assert price.cost(1, 1) + price.cost(2, 2) == price.cost(3, 3)


def test_a_stale_price_list_warns_but_is_accepted() -> None:
    pricing = parse_pricing(VALID)
    assert not pricing.is_stale(date(2026, 12, 1))
    assert pricing.is_stale(date(2026, 12, 2))
