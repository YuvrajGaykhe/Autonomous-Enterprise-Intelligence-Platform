"""
Conversion to the base currency (VS-02 plan A7.5, A9.1).

convert() is the one explicit way an amount crosses currencies. MoneyValue
is untouched: adding two currencies still raises CurrencyMismatchError, and
a converted amount is a NEW MoneyValue in the rate set's base currency.

All arithmetic is Decimal, in a context this module states for itself. The
process default context is never relied on, so no precision or rounding
mode set elsewhere can change a figure. Rounding to a quantum is always an
explicit quantize. A rate holds at most 18 significant digits (plan A7.2),
so at 50 digits the product is exact for any amount of up to 32.

There is no default rate and nothing is skipped: a currency the rate set
does not hold raises FxRateMissingError.
"""

from __future__ import annotations

from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

from app.fx.errors import FxRateMissingError
from app.fx.rates import RateSet
from app.intelligence.money import MoneyValue

#: Plan A9.1: the precision and the rounding mode every multiplication and
#: division runs at.
ARITHMETIC_PRECISION = 50
ROUNDING_MODE = ROUND_HALF_EVEN
#: Plan A7.5: a converted amount is stated to 0.01 of the base currency.
BASE_QUANTUM = Decimal("0.01")


def arithmetic_context() -> Context:
    """
    The arithmetic context of plan A9.1: a new one each time, shared with nothing.

    Every field that can change a result, or refuse one, is stated, so
    nothing is taken from the process default context: the precision and
    the rounding mode, the widest exponents, and the three signals that mean
    a result is not a number.
    """
    return Context(prec=ARITHMETIC_PRECISION, rounding=ROUNDING_MODE, Emin=MIN_EMIN, Emax=MAX_EMAX,
                   traps=[InvalidOperation, DivisionByZero, Overflow])


def convert(value: MoneyValue, rate_set: RateSet) -> MoneyValue:
    """
    A new MoneyValue in the rate set's base currency.

    An amount already in the base currency is multiplied by its rate of 1
    and quantized the same way as any other.
    """
    rate = rate_set.rates.get(value.currency)
    if rate is None:
        raise FxRateMissingError((value.currency,), rate_set.rate_set_version)
    with localcontext(arithmetic_context()):
        amount = (value.amount * rate).quantize(BASE_QUANTUM, rounding=ROUNDING_MODE)
    return MoneyValue(amount=amount, currency=rate_set.base_currency)
