"""
Configuration for the Layer 2 risk rules (config/intelligence/risk_rules.yaml).

The file carries what the foundation needs and what M3 measures with:

    rules_version         the version every assessment identity is bound to
    linker_version        the M4 document-linker version every derived link
                          is stamped with, as a non-empty string
    acceptance_as_of      the pinned evaluation date (plan A27), so no
                          acceptance run ever depends on a clock
    layer1_fingerprints   the Layer 1 snapshot each source system is
                          expected to present
    lookback_days         how far back from as_of a signal may look
                          (strategy 4.4), so a January burst does not
                          escalate a customer forever
    sla_resolution_targets  DOC-003's resolution targets, in business days
    escalation            DOC-003's window and ticket threshold, with the
                          document the rule is quoted from
    bands                 the M3 decision table (plan A5)

The fingerprint pin is the gate M0 chose (closure report 1.8 D). A database
prepared the wrong way - most plausibly by `make verify-layer1`, which
ingests five of seven entity types and then injects malformed fixture rows
into the csv_demo scope - produces a different fingerprint and is refused
at the door, instead of silently yielding a citation-free brief.

Unknown keys are refused, so adding a section is a deliberate edit rather
than a silent one, and plan A23's "invalid rules refused at load naming the
broken rule" is satisfied here rather than at evaluation time.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType

import yaml

from app.intelligence.bands import BandRule, parse_band_rules
from app.intelligence.errors import IntelligenceConfigError
from app.normalization.config import default_config

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "intelligence" / "risk_rules.yaml"
)

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class EscalationPolicy:
    """DOC-003's escalation rule, with the document it is quoted from."""

    window_days: int
    ticket_threshold: int
    because_documents: tuple[str, ...]


@dataclass(frozen=True)
class RiskRulesConfig:
    """Complete, validated, immutable Layer 2 risk-rule configuration."""

    rules_version: int
    linker_version: str
    acceptance_as_of: date
    layer1_fingerprints: Mapping[str, str]
    lookback_days: int
    sla_resolution_targets: Mapping[str, int]
    escalation: EscalationPolicy
    band_rules: tuple[BandRule, ...]

    def pinned_fingerprint(self, source_system: str) -> str:
        """The Layer 1 fingerprint this source system must present."""
        fingerprint = self.layer1_fingerprints.get(source_system)
        if fingerprint is None:
            raise IntelligenceConfigError(
                f"no layer1_fingerprint is pinned for source_system {source_system!r}"
            )
        return fingerprint


@functools.lru_cache(maxsize=1)
def default_risk_rules() -> RiskRulesConfig:
    """Load (once) the repository risk-rule configuration."""
    return load_risk_rules(DEFAULT_CONFIG_PATH)


def load_risk_rules(path: str | Path) -> RiskRulesConfig:
    """Load and validate a risk-rule configuration file."""
    path = Path(path)
    where = str(path)
    if not path.is_file():
        raise IntelligenceConfigError(f"Risk rules configuration file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise IntelligenceConfigError(f"{where}: invalid YAML: {exc}") from exc
    data = _section(data, where, {"version", "rules_version", "linker_version",
                                  "acceptance_as_of", "layer1_fingerprints",
                                  "lookback_days", "sla_resolution_targets",
                                  "escalation", "bands"})
    if data["version"] != 1:
        raise IntelligenceConfigError(f"{where}: unsupported version {data['version']!r}")
    return RiskRulesConfig(
        rules_version=_positive_int(data["rules_version"], f"{where}: rules_version"),
        linker_version=_non_empty_text(data["linker_version"], f"{where}: linker_version"),
        acceptance_as_of=_plain_date(data["acceptance_as_of"], f"{where}: acceptance_as_of"),
        layer1_fingerprints=_fingerprints(data["layer1_fingerprints"],
                                          f"{where}: layer1_fingerprints"),
        lookback_days=_positive_int(data["lookback_days"], f"{where}: lookback_days"),
        sla_resolution_targets=_sla_targets(data["sla_resolution_targets"],
                                            f"{where}: sla_resolution_targets"),
        escalation=_escalation(data["escalation"], f"{where}: escalation"),
        band_rules=parse_band_rules(data["bands"], f"{where}: bands"),
    )


def _sla_targets(raw: object, loc: str) -> Mapping[str, int]:
    """
    DOC-003's resolution targets in business days, keyed by priority.

    A priority the mapping does not name has no target and therefore never
    breaches. That is deliberate: inventing a target for an unmapped
    priority would manufacture breaches the policy document never states.
    """
    if not isinstance(raw, dict) or not raw:
        raise IntelligenceConfigError(f"{loc}: expected a non-empty mapping")
    targets = {}
    for priority, days in raw.items():
        name = str(priority)
        if name not in default_config().fields["support_tickets"]["priority"].enum_values:
            raise IntelligenceConfigError(
                f"{loc}.{name}: {name!r} is not a Layer 1 priority value"
            )
        targets[name] = _positive_int(days, f"{loc}.{name}")
    return MappingProxyType(targets)


def _escalation(raw: object, loc: str) -> EscalationPolicy:
    """DOC-003's window and threshold. Both come from the document, not from taste."""
    if not isinstance(raw, dict):
        raise IntelligenceConfigError(f"{loc}: expected a mapping")
    expected = {"window_days", "ticket_threshold", "because_documents"}
    missing = expected - set(raw)
    unknown = set(map(str, raw)) - expected
    if missing or unknown:
        raise IntelligenceConfigError(
            f"{loc}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}"
        )
    documents = raw["because_documents"]
    if not isinstance(documents, list) or not documents:
        raise IntelligenceConfigError(
            f"{loc}.because_documents: a policy rule must name the document it came from"
        )
    for index, document in enumerate(documents):
        if not isinstance(document, str) or not document.strip():
            raise IntelligenceConfigError(
                f"{loc}.because_documents[{index}]: expected a document id"
            )
    return EscalationPolicy(
        window_days=_positive_int(raw["window_days"], f"{loc}: window_days"),
        ticket_threshold=_positive_int(raw["ticket_threshold"], f"{loc}: ticket_threshold"),
        because_documents=tuple(documents),
    )


def _fingerprints(raw: object, loc: str) -> Mapping[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise IntelligenceConfigError(f"{loc}: expected a non-empty mapping")
    known = set(default_config().source_systems)
    pinned = {}
    for source_system, fingerprint in raw.items():
        if source_system not in known:
            raise IntelligenceConfigError(
                f"{loc}: {source_system!r} is not a configured source system"
            )
        if not isinstance(fingerprint, str) or not _SHA256_HEX.fullmatch(fingerprint):
            raise IntelligenceConfigError(
                f"{loc}.{source_system}: expected a 64-character hex SHA-256 digest"
            )
        pinned[source_system] = fingerprint
    return MappingProxyType(pinned)


def _section(data: object, loc: str, expected: set[str]) -> dict[str, object]:
    """Return a configuration mapping after checking it has exactly the expected keys."""
    if not isinstance(data, dict):
        raise IntelligenceConfigError(f"{loc}: expected a mapping")
    missing = expected - set(data)
    unknown = set(map(str, data)) - expected
    if missing or unknown:
        raise IntelligenceConfigError(
            f"{loc}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}"
        )
    return data


def _positive_int(value: object, loc: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise IntelligenceConfigError(f"{loc}: expected an integer of at least 1")
    return value


def _non_empty_text(value: object, loc: str) -> str:
    """
    A non-empty string.

    Deliberately not modelled on rules_version's positive int: DerivedLink
    validates linker_version as a non-empty string, so a YAML integer would
    be refused by the frozen contract at link-construction time rather than
    here. Refusing it at load is what plan A23 asks for.
    """
    if not isinstance(value, str) or not value.strip():
        raise IntelligenceConfigError(f"{loc}: expected a non-empty string")
    return value


def _plain_date(value: object, loc: str) -> date:
    """A calendar date, never a timestamp: an as_of with a time is not a date."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise IntelligenceConfigError(f"{loc}: expected a YYYY-MM-DD date")
    return value
