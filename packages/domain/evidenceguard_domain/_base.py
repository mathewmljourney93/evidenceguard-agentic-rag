"""Shared base class for immutable domain values."""

from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable, closed domain value.

    Deep immutability comes from three rules applied together:

    - every model is frozen, so attributes cannot be reassigned;
    - every collection field is a tuple, never a list, set or dict;
    - every nested value is another frozen ``DomainModel`` or an immutable scalar.

    Unknown fields are rejected, and surrounding whitespace is stripped from strings.

    ``model_copy`` re-runs validation (see below). Pydantic's ``model_construct`` and
    ``object.__setattr__`` can still bypass validation; domain code never uses them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Return a validated copy.

        Pydantic's default ``model_copy(update=...)`` skips validation, which could produce an
        invalid "validated" object. Here the update is applied to a plain dump and the result is
        validated like any new input. ``deep`` is accepted for compatibility; values are
        immutable, so a shallow copy is already safe.
        """
        data = self.model_dump()
        if update:
            data.update(update)
        return self.model_validate(data)
