"""
Per-deal values and the arithmetic they are computed with (VS-02 plan A9).

Every figure VS-02 states is a sum of the four values a valued deal has:

    native_unweighted   the deal's amount, as stored
    native_weighted     amount x probability / 100, rounded to WEIGHT_QUANTUM
    base_unweighted     convert(native_unweighted)
    base_weighted       convert(native_weighted): of the ALREADY-rounded
                        weighted amount, never of the unrounded one

Rounding is per deal and half-even. An aggregate is the sum of these values
over a bucket's deals and is computed no other way (A9.4 item 3), which is
what makes every partition reconcile exactly to the total: a bucket is never
rounded as a whole, and a native total is never converted.

All arithmetic is Decimal, in the context app.fx states for itself (A9.1).
That covers addition as well: the frozen MoneyValue.total adds in whatever
context is current, so total() here calls it inside the explicit one. The
process default context is never relied on, so no precision or rounding mode
set elsewhere can change a figure.

This module is pure. It receives no band, no session and no clock, and it
never loads a rate set: it is handed one. The currency of an amount is
never crossed except by convert().
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.fx.convert import ROUNDING_MODE, arithmetic_context, convert
from app.fx.rates import RateSet
from app.intelligence.money import MoneyValue

#: Plan A9.2: a weighted amount is stated to 0.01 of its own currency.
WEIGHT_QUANTUM = Decimal("0.01")
#: Plan A11: a concentration share is stated to four decimal places. Defined
#: here from VS02-M2 because the methodology digest covers it (OD-2); nothing
#: computes a share before VS02-M3.
SHARE_QUANTUM = Decimal("0.0001")

#: A probability is the source system's stated percentage (plan A9.2).
_PERCENT = Decimal(100)


@dataclass(frozen=True)
class DealValues:
    """The four values of one valued deal (plan A9.2, A9.3)."""

    native_unweighted: MoneyValue
    native_weighted: MoneyValue
    base_unweighted: MoneyValue
    base_weighted: MoneyValue


def weigh(amount: MoneyValue, probability: Decimal) -> MoneyValue:
    """The probability-weighted amount, in the amount's own currency (plan A9.2)."""
    with localcontext(arithmetic_context()):
        weighted = (amount.amount * probability / _PERCENT).quantize(
            WEIGHT_QUANTUM, rounding=ROUNDING_MODE)
    return MoneyValue(amount=weighted, currency=amount.currency)


def deal_values(amount: MoneyValue, probability: Decimal, rate_set: RateSet) -> DealValues:
    """
    One valued deal's four values.

    A currency the rate set does not hold raises convert()'s own
    FxRateMissingError (plan A7.5 item 3). It is not caught: there is no
    default rate and no skipped deal.
    """
    weighted = weigh(amount, probability)
    return DealValues(
        native_unweighted=amount,
        native_weighted=weighted,
        base_unweighted=convert(amount, rate_set),
        base_weighted=convert(weighted, rate_set),
    )


def total(currency: str, values: Iterable[MoneyValue]) -> MoneyValue:
    """
    The sum of values that are all in the named currency (plan A7.5 item 5).

    MoneyValue.total raises on any other currency, and nothing here catches
    it: two currencies are never added. The sum is taken inside the explicit
    arithmetic context (A9.1 item 4).
    """
    with localcontext(arithmetic_context()):
        return MoneyValue.total(currency, values)
