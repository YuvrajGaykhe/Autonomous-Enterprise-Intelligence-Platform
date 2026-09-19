"""
Configuration for the Layer 2 risk rules (config/intelligence/risk_rules.yaml).

At M1 the file carries only what the foundation needs:

    rules_version         the version every assessment identity is bound to
    acceptance_as_of      the pinned evaluation date (plan A27), so no
                          acceptance run ever depends on a clock
    layer1_fingerprints   the Layer 1 snapshot each source system is
                          expected to present

The fingerprint pin is the gate M0 chose (closure report 1.8 D). A database
prepared the wrong way - most plausibly by `make verify-layer1`, which
ingests five of seven entity types and then injects malformed fixture rows
into the csv_demo scope - produces a different fingerprint and is refused
at the door, instead of silently yielding a citation-free brief.

The band decision table arrives with M3. Unknown keys are refused now so
that addition is a deliberate edit, not a silent one.
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

from app.intelligence.errors import IntelligenceConfigError
from app.normalization.config import default_config

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "intelligence" / "risk_rules.yaml"
)

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class RiskRulesConfig:
    """Complete, validated, immutable Layer 2 risk-rule configuration."""

    rules_version: int
    acceptance_as_of: date
    layer1_fingerprints: Mapping[str, str]

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
    data = _section(data, where, {"version", "rules_version", "acceptance_as_of",
                                  "layer1_fingerprints"})
    if data["version"] != 1:
        raise IntelligenceConfigError(f"{where}: unsupported version {data['version']!r}")
    return RiskRulesConfig(
        rules_version=_positive_int(data["rules_version"], f"{where}: rules_version"),
        acceptance_as_of=_plain_date(data["acceptance_as_of"], f"{where}: acceptance_as_of"),
        layer1_fingerprints=_fingerprints(data["layer1_fingerprints"],
                                          f"{where}: layer1_fingerprints"),
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


def _plain_date(value: object, loc: str) -> date:
    """A calendar date, never a timestamp: an as_of with a time is not a date."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise IntelligenceConfigError(f"{loc}: expected a YYYY-MM-DD date")
    return value
