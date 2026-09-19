"""
Currency-qualified money for Layer 2 (plan A12).

MoneyValue carries an amount and its ISO 4217 code together, so no call
site can lose the currency on the way to a brief. Addition and subtraction
are defined only within one currency and raise across currencies: VS-01
states no cross-currency total, because no FX rate set exists until VS-02.
This type is the seam VS-02's FX normalization plugs into without touching
any VS-01 call site.

The currency vocabulary is not redeclared here. It is read from the frozen
D1 configuration (config/mappings/normalization.yaml), so Layer 2 can never
accept a code Layer 1 would have rejected.

The builtin sum() is deliberately unsupported: it starts from the integer 0,
which is not money in any currency. Use MoneyValue.total() instead, which
states the currency it is totalling.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.intelligence.errors import ContractViolationError, CurrencyMismatchError
from app.normalization.config import default_config


@dataclass(frozen=True)
class MoneyValue:
    """An amount in exactly one ISO 4217 currency."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise ContractViolationError(
                f"MoneyValue.amount must be a Decimal, got {type(self.amount).__name__}"
            )
        if not self.amount.is_finite():
            raise ContractViolationError(f"MoneyValue.amount must be finite, got {self.amount}")
        if self.currency not in default_config().currency_codes:
            raise ContractViolationError(
                f"MoneyValue.currency {self.currency!r} is not a configured ISO 4217 code"
            )

    def __add__(self, other: object) -> MoneyValue:
        return self._combine(other, add=True)

    def __sub__(self, other: object) -> MoneyValue:
        return self._combine(other, add=False)

    def _combine(self, other: object, *, add: bool) -> MoneyValue:
        if not isinstance(other, MoneyValue):
            raise TypeError(
                f"MoneyValue can only be combined with MoneyValue, got {type(other).__name__}"
            )
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency} and {other.currency}: VS-01 has no FX rate set, "
                f"so no cross-currency total exists"
            )
        amount = self.amount + other.amount if add else self.amount - other.amount
        return MoneyValue(amount=amount, currency=self.currency)

    @classmethod
    def total(cls, currency: str, values: Iterable[MoneyValue]) -> MoneyValue:
        """Total values that are all in the named currency. Raises on any other."""
        result = cls(amount=Decimal("0"), currency=currency)
        for value in values:
            result = result + value
        return result

    def __str__(self) -> str:
        """Rendering is always currency-qualified (plan A12)."""
        return f"{self.currency} {self.amount}"
