"""
Failure model for the Layer 2 intelligence foundation (VS-01 M1).

Every failure here is a SYSTEM failure: a caller fault, a configuration
fault, or a broken invariant. Nothing in this package processes source
records, so there is no DATA failure category and nothing is ever
quarantined. The package fails closed: an assessment is never produced
from a scope it cannot prove.

    IntelligenceError
        ContractViolationError      a contract type was built inconsistently
        CurrencyMismatchError       money was combined across currencies
        ScopeResolutionError        the scope has no defensible as_of
        FingerprintMismatchError    the Layer 1 snapshot is not the expected one

IntelligenceConfigError is deliberately NOT an IntelligenceError, matching
the D1/D2 convention: a broken configuration is a deployment fault, not a
runtime contract violation, and must be distinguishable at the call site.
"""

from __future__ import annotations


class IntelligenceError(Exception):
    """Base exception for the Layer 2 intelligence foundation."""


class ContractViolationError(IntelligenceError):
    """A contract object was constructed in a state its invariants forbid."""


class CurrencyMismatchError(IntelligenceError):
    """Monetary values of different currencies were combined."""


class ScopeResolutionError(IntelligenceError):
    """A scope cannot be resolved deterministically."""


class FingerprintMismatchError(IntelligenceError):
    """The computed Layer 1 fingerprint is not the expected one."""

    def __init__(self, source_system: str, expected: str, computed: str) -> None:
        super().__init__(
            f"layer1_fingerprint mismatch for source_system={source_system!r}: "
            f"expected {expected}, computed {computed}. The Layer 1 snapshot is not the one "
            f"this configuration was pinned to; rebuild the database from the clean "
            f"full-dataset path before assessing."
        )
        self.source_system = source_system
        self.expected = expected
        self.computed = computed


class IntelligenceConfigError(Exception):
    """Raised when the intelligence configuration is missing or inconsistent."""
