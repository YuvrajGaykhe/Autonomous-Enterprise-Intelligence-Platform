"""
FX normalization (VS-02 M1): shared infrastructure, introduced with VS-02.

No figure spanning two currencies exists except through a rate set (plan
A7.1). A rate set is a stated assumption with a declared base currency, and
convert() is the one explicit way an amount crosses into it. MoneyValue is
unchanged: adding two currencies still raises CurrencyMismatchError.

Public API:
    RateSet / load_rate_set / default_rate_set
                      the rate set: authored configuration with a version, a
                      date, a source note and a digest over all of them.
                      Loaded on first use, never at import or startup.
    convert           a NEW MoneyValue in the rate set's base currency,
                      rounded per amount to BASE_QUANTUM, half-even.
    arithmetic_context / ARITHMETIC_PRECISION / ROUNDING_MODE / BASE_QUANTUM
                      the explicit Decimal context VS-02's arithmetic runs
                      in; the process default context is never relied on.
    FxError / FxRateMissingError / FxConfigError
                      a missing rate is an error, never a default rate.

Determinism is structural: nothing here reads a clock, an environment
variable, a database or a network, and nothing is written anywhere. A
boundary test fails the build if any of that changes.
"""

from app.fx.convert import (
    ARITHMETIC_PRECISION,
    BASE_QUANTUM,
    ROUNDING_MODE,
    arithmetic_context,
    convert,
)
from app.fx.errors import FxConfigError, FxError, FxRateMissingError
from app.fx.rates import RateSet, default_rate_set, load_rate_set

__all__ = [
    "ARITHMETIC_PRECISION",
    "BASE_QUANTUM",
    "FxConfigError",
    "FxError",
    "FxRateMissingError",
    "ROUNDING_MODE",
    "RateSet",
    "arithmetic_context",
    "convert",
    "default_rate_set",
    "load_rate_set",
]
