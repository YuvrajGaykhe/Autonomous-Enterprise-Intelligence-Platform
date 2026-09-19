"""
Layer 2 intelligence foundation (VS-01 M1).

The vocabulary and the invariants every later VS-01 milestone depends on.
Layer 1 is frozen: this package reads its canonical rows and its
configuration, and changes neither.

Public API:
    Scope / resolve_scope / resolve_pinned_scope / layer1_fingerprint
                      what an assessment was computed over, and the Layer 1
                      snapshot it is bound to. Fails closed when the
                      snapshot is not the pinned one.
    MoneyValue        currency-qualified money that refuses to be summed
                      across currencies.
    Contract types    RiskBand, EdgeBasis, LinkBasis, LinkConfidence,
                      Function, Stance, ActionId, EvidenceKind, Citation,
                      Evidence, EntityRef, DerivedLink, DealSignal,
                      SignalSet, Position, Conflict, ConflictResolution.
    timeutil          UTC bucketing, closed date windows, business days.

Determinism is structural, not advisory: nothing here reads a clock, and a
boundary test fails the build if datetime.now, date.today or utcnow appears
anywhere under this package.
"""

from app.intelligence.config import RiskRulesConfig, default_risk_rules, load_risk_rules
from app.intelligence.contract import (
    ActionId,
    Citation,
    Conflict,
    ConflictResolution,
    DealSignal,
    DerivedLink,
    DocumentCitation,
    EdgeBasis,
    EntityRef,
    Evidence,
    EvidenceKind,
    Function,
    LinkBasis,
    LinkConfidence,
    Position,
    RecordCitation,
    RiskBand,
    SignalSet,
    Stance,
)
from app.intelligence.errors import (
    ContractViolationError,
    CurrencyMismatchError,
    FingerprintMismatchError,
    IntelligenceConfigError,
    IntelligenceError,
    ScopeResolutionError,
)
from app.intelligence.money import MoneyValue
from app.intelligence.scope import (
    DEFAULT_SOURCE_SYSTEM,
    AsOfSource,
    Scope,
    layer1_fingerprint,
    resolve_pinned_scope,
    resolve_scope,
)
from app.intelligence.timeutil import (
    business_days_between,
    closed_window,
    days_between,
    utc_date,
)

__all__ = [
    "ActionId",
    "AsOfSource",
    "Citation",
    "Conflict",
    "ConflictResolution",
    "ContractViolationError",
    "CurrencyMismatchError",
    "DEFAULT_SOURCE_SYSTEM",
    "DealSignal",
    "DerivedLink",
    "DocumentCitation",
    "EdgeBasis",
    "EntityRef",
    "Evidence",
    "EvidenceKind",
    "FingerprintMismatchError",
    "Function",
    "IntelligenceConfigError",
    "IntelligenceError",
    "LinkBasis",
    "LinkConfidence",
    "MoneyValue",
    "Position",
    "RecordCitation",
    "RiskBand",
    "RiskRulesConfig",
    "Scope",
    "ScopeResolutionError",
    "SignalSet",
    "Stance",
    "business_days_between",
    "closed_window",
    "days_between",
    "default_risk_rules",
    "layer1_fingerprint",
    "load_risk_rules",
    "resolve_pinned_scope",
    "resolve_scope",
    "utc_date",
]
