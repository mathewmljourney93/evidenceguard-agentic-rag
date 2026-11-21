"""Worst-case spend control for live runs: the preflight ceiling and ``BudgetGuard``.

**Preflight.** Before any call, the ceiling of one invocation is

    reviews x (8 questions x 2 stages x 3 reservations + 1 repair)

calls, each priced at ``MAX_SYSTEM_TEXT_BYTES + MAX_USER_TEXT_BYTES + 512`` input tokens (one
token per byte is an upper bound for UTF-8 text) plus the configured ``max_output_tokens``. The
run is refused with exit 4, before anything is called, when the ceiling exceeds ``--budget-usd``
or the ceiling plus the cost of committed runs exceeds the selection's ``total_usd_cap``.

**Guard.** ``BudgetGuard`` wraps the model provider. Each ``generate`` first reserves
``utf8(system_text + user_text) + 512`` input tokens plus ``max_output_tokens`` at the model's
prices; if the spent amount plus that reservation exceeds the budget it raises
``BudgetExhaustedError`` without dispatching. After the call it charges the actual usage, or the
full reservation when the call raised or reported no usage. When actual input tokens exceed the
reservation the token-per-byte assumption is broken: the guard marks itself stopped, and the
runner starts no new review and writes a partial record marked ``budget_stopped`` (exit 6).
"""

import threading
from dataclasses import dataclass
from decimal import Decimal

from evidenceguard_agents.providers import ModelProvider
from evidenceguard_domain.model_calls import (
    MAX_SYSTEM_TEXT_BYTES,
    MAX_USER_TEXT_BYTES,
    ProviderResponse,
    StructuredRequest,
)
from evidenceguard_evaluation.config import EXIT_BUDGET_PREFLIGHT, refuse
from evidenceguard_evaluation.pricing import ModelPrice

QUESTIONS_PER_REVIEW = 8
STAGES_PER_QUESTION = 2
RESERVATIONS_PER_STAGE = 3
REPAIRS_PER_REVIEW = 1
REQUEST_OVERHEAD_TOKENS = 512
MAX_REQUEST_INPUT_TOKENS = MAX_SYSTEM_TEXT_BYTES + MAX_USER_TEXT_BYTES + REQUEST_OVERHEAD_TOKENS


class BudgetExhaustedError(RuntimeError):
    """The next reservation would cross the budget; nothing was dispatched. Carries nothing."""

    def __init__(self) -> None:
        super().__init__("budget_exhausted")


def calls_per_review() -> int:
    return QUESTIONS_PER_REVIEW * STAGES_PER_QUESTION * RESERVATIONS_PER_STAGE + REPAIRS_PER_REVIEW


def preflight_ceiling(*, reviews: int, price: ModelPrice, max_output_tokens: int) -> Decimal:
    """The worst-case cost of ``reviews`` reviews (see the module docstring)."""
    if reviews < 0 or max_output_tokens < 1:
        raise ValueError("invalid preflight arguments")
    per_call = price.cost(MAX_REQUEST_INPUT_TOKENS, max_output_tokens)
    return per_call * reviews * calls_per_review()


def check_preflight(
    *, ceiling: Decimal, budget_usd: Decimal, total_cap: Decimal, committed_usd: Decimal
) -> None:
    """Refuse with exit 4 when the ceiling exceeds the run budget or the remaining total cap."""
    if budget_usd <= 0 or ceiling > budget_usd:
        raise refuse("the worst-case ceiling exceeds --budget-usd", EXIT_BUDGET_PREFLIGHT)
    if ceiling + committed_usd > total_cap:
        raise refuse(
            "the worst-case ceiling exceeds the remaining total cap", EXIT_BUDGET_PREFLIGHT
        )


def require_open_cap(*, total_cap: Decimal, committed_usd: Decimal, budget_usd: Decimal) -> None:
    """The first live check: with no remaining cap (the committed cap is 0) or a non-positive
    run budget, no ceiling can fit, so the run is refused with exit 4 before anything else."""
    if total_cap - committed_usd <= 0:
        raise refuse(
            "the total spend cap in selection.toml allows no live run", EXIT_BUDGET_PREFLIGHT
        )
    if budget_usd <= 0:
        raise refuse("--budget-usd must be positive", EXIT_BUDGET_PREFLIGHT)


@dataclass
class BudgetTotals:
    reserved_calls: int = 0
    dispatched_calls: int = 0
    refused_calls: int = 0
    spent_usd: Decimal = Decimal(0)


class BudgetGuard:
    """A ``ModelProvider`` that enforces a budget around another provider (module docstring)."""

    def __init__(self, provider: ModelProvider, *, price: ModelPrice, budget_usd: Decimal) -> None:
        if budget_usd <= 0:
            raise ValueError("budget must be positive")
        self._provider = provider
        self._price = price
        self._budget = budget_usd
        self._lock = threading.Lock()
        self.totals = BudgetTotals()
        self.stopped = False

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    @property
    def budget_usd(self) -> Decimal:
        return self._budget

    @property
    def exhausted(self) -> bool:
        return self.stopped or self.totals.refused_calls > 0

    def reservation(self, request: StructuredRequest) -> tuple[int, int, Decimal]:
        size = len(request.system_text.encode("utf-8")) + len(request.user_text.encode("utf-8"))
        input_tokens = size + REQUEST_OVERHEAD_TOKENS
        output_tokens = request.max_output_tokens
        return input_tokens, output_tokens, self._price.cost(input_tokens, output_tokens)

    def generate(self, request: StructuredRequest) -> ProviderResponse:
        input_reserved, _, reserved = self.reservation(request)
        with self._lock:
            if self.stopped or self.totals.spent_usd + reserved > self._budget:
                self.totals.refused_calls += 1
                raise BudgetExhaustedError()
            self.totals.reserved_calls += 1
            self.totals.dispatched_calls += 1
        try:
            response = self._provider.generate(request)
        except BaseException:
            with self._lock:
                self.totals.spent_usd += reserved  # no usage came back: charge the reservation
            raise
        usage = response.usage
        with self._lock:
            if usage.input_tokens == 0 and usage.output_tokens == 0:
                self.totals.spent_usd += reserved
            else:
                self.totals.spent_usd += self._price.cost(usage.input_tokens, usage.output_tokens)
            if usage.input_tokens > input_reserved:
                self.stopped = True
        return response
