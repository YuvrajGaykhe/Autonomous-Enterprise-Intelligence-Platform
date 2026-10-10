"""
Failure model for FX normalization (VS-02 M1).

    FxError
        FxRateMissingError    the rate set holds no rate for a currency it
                              was asked to convert

FxConfigError is deliberately NOT an FxError, matching the D1, D2 and M1
convention: a rate file that cannot be loaded is a deployment fault, not a
conversion failure, and must be distinguishable at the call site.

There is no default rate and no skipped amount (plan A7.5): a currency the
rate set does not hold is an error, never a figure.
"""

from __future__ import annotations

from collections.abc import Iterable


class FxError(Exception):
    """Base exception for FX conversion."""


class FxRateMissingError(FxError):
    """The rate set holds no rate for a currency it was asked to convert."""

    def __init__(self, currencies: Iterable[str], rate_set_version: str) -> None:
        # A bare code is one currency, not an iterable of its letters.
        codes = (currencies,) if isinstance(currencies, str) else currencies
        ordered = tuple(sorted(set(codes)))
        super().__init__(f"rate set {rate_set_version!r} holds no rate for {', '.join(ordered)}")
        self.currencies = ordered
        self.rate_set_version = rate_set_version


class FxConfigError(Exception):
    """Raised when the rate-set configuration is missing or inconsistent."""
