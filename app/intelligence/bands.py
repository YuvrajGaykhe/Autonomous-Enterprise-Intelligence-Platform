"""
The risk band decision table and its evaluation (VS-01 M3).

A band is assigned by a versioned table in configuration, never by a score.
Strategy section 4.2 is the reason: arbitrary weights are unfalsifiable, so
there are none. Every rule the signals satisfy is reported, and that list is
the explanation - not a rationalisation written after the fact.

Three properties are structural here rather than asserted by a test:

    Band inputs are closed    Only the seven signals plan A10 marks "band
                              input: yes" may be named by a rule. A table
                              naming exposure_by_currency, sla_breach_count
                              or stale_open_ticket_count is refused at load,
                              by name, rather than silently evaluating.
    Money cannot reach a band The two measured traps of strategy 4.3 and 4.4
                              are a blended score that surfaces the wrong
                              customer, and a backlog signal that ranks a
                              January ticket above an active deterioration.
                              Neither S12 nor S9 is a permitted input, so
                              neither can be reintroduced by editing YAML.
    Highest band wins         Bands are ordinal (M1's RiskBand.rank), so the
                              assigned band is the maximum over the satisfied
                              rules. Table order decides only the order the
                              satisfied ids are reported in.

A missing signal value is not a satisfied condition. days_since_last_ticket
is None for a customer who has never raised a ticket, and "at most 30 days
since the last ticket" is false for a customer who has no last ticket rather
than trivially true - which is what keeps the 15 ticketless customers at
NONE instead of collecting a recency rule.

Nothing here reads a clock, a database or a file. The table is parsed from
data the caller loaded; evaluation is a pure function of a SignalSet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.intelligence.contract import RiskBand, SignalSet
from app.intelligence.errors import IntelligenceConfigError

#: Boolean signals a band rule may name (plan A10, S5).
BOOLEAN_BAND_INPUTS = frozenset({"policy_escalation_state"})

#: Counted signals a band rule may name (plan A10: S1, S2, S3, S4, S6, S8).
NUMERIC_BAND_INPUTS = frozenset({
    "open_ticket_count",
    "open_high_priority_count",
    "tickets_in_lookback",
    "max_tickets_in_14d_window",
    "days_since_last_ticket",
    "open_sla_breach_high_count",
})

#: Every signal a band may be computed from. Plan A10 marks exactly these
#: seven "band input: yes". S7, S9, S10, S11, S12, S13, S14 and S15 are
#: deliberately absent: they are context, backlog, money or evidence, and a
#: band computed from any of them is the failure strategy 4.3 measured.
BAND_INPUT_SIGNALS = BOOLEAN_BAND_INPUTS | NUMERIC_BAND_INPUTS

#: The band vocabulary, as names. M1's, and not redeclared: a table naming
#: a fifth band is refused rather than widening the scale.
_BAND_NAMES = frozenset(str(band) for band in RiskBand)

#: Suffixes that turn a signal name into a numeric comparison.
_AT_LEAST = "_at_least"
_AT_MOST = "_at_most"


class Comparison(StrEnum):
    """How a rule compares a signal to its threshold."""

    IS = "IS"
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


@dataclass(frozen=True)
class Condition:
    """One signal compared to one threshold."""

    signal: str
    comparison: Comparison
    threshold: int | bool

    def holds_for(self, signals: SignalSet) -> bool:
        """Whether a signal set satisfies this condition."""
        value = getattr(signals, self.signal)
        if self.comparison is Comparison.IS:
            return bool(value) is bool(self.threshold)
        if value is None:
            # A customer with no ticket has no "days since last ticket". The
            # absence is not a small number and not a large one, so neither
            # bound holds; treating it as either would band a customer on a
            # value that was never measured.
            return False
        if self.comparison is Comparison.AT_LEAST:
            return int(value) >= int(self.threshold)
        return int(value) <= int(self.threshold)

    def to_payload(self) -> dict[str, object]:
        return {"signal": self.signal, "comparison": str(self.comparison),
                "threshold": self.threshold}


@dataclass(frozen=True)
class BandRule:
    """One row of the decision table."""

    rule_id: str
    band: str
    conditions: tuple[Condition, ...]
    description: str
    because_documents: tuple[str, ...]

    def holds_for(self, signals: SignalSet) -> bool:
        """Every condition must hold. An empty rule would match everything."""
        return all(condition.holds_for(signals) for condition in self.conditions)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.rule_id,
            "band": self.band,
            "conditions": [condition.to_payload() for condition in self.conditions],
            "because_documents": list(self.because_documents),
        }


@dataclass(frozen=True)
class BandAssignment:
    """A band and the rule ids that produced it."""

    band: str
    satisfied_rules: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {"band": self.band, "satisfied_rules": list(self.satisfied_rules)}


def parse_band_rules(raw: object, loc: str) -> tuple[BandRule, ...]:
    """
    Parse and validate the decision table, refusing a broken rule by name.

    Plan A23: invalid rule configuration is refused at load naming the broken
    rule, and no partial assessment is produced. A table that half-loads is
    worse than one that does not load, because the band it assigns is
    plausible and wrong.
    """
    if not isinstance(raw, list) or not raw:
        raise IntelligenceConfigError(f"{loc}: expected a non-empty list of band rules")
    rules = tuple(
        _band_rule(entry, f"{loc}[{index}]") for index, entry in enumerate(raw)
    )
    for index, rule in enumerate(rules):
        if any(earlier.rule_id == rule.rule_id for earlier in rules[:index]):
            raise IntelligenceConfigError(
                f"{loc}[{index}].id: {rule.rule_id!r} is already defined. Two rules sharing "
                f"an id make the satisfied-rule list ambiguous, and that list is the "
                f"explanation a brief prints"
            )
    return rules


def assign_band(signals: SignalSet, rules: Sequence[BandRule], *, floor: str) -> BandAssignment:
    """
    The highest band whose rule the signals satisfy, with every satisfied id.

    `floor` is the band of a customer no rule speaks about - NONE in the
    shipped configuration. It is a parameter rather than a literal so the
    caller names it and a reader can see there is no hidden default.
    """
    matched = tuple(rule for rule in rules if rule.holds_for(signals))
    band = max((rule.band for rule in matched), key=_rank, default=floor)
    return BandAssignment(
        band=band, satisfied_rules=tuple(rule.rule_id for rule in matched)
    )


def ranking_key(
    customer_source_id: str, assignment: BandAssignment, signals: SignalSet
) -> tuple[int, int, int, str]:
    """
    The plan A15 order: band desc, S8 desc, S4 desc, source_id asc.

    Money is never a sort key. Strategy 4.3 measured what happens when it is:
    CUST-007 is 22nd of 23 on weighted exposure, so a monetary sort surfaces
    a customer with one open ticket and buries the escalated one. Sorting a
    sequence of these keys ascending yields the plan's order directly.
    """
    return (
        -_rank(assignment.band),
        -signals.open_sla_breach_high_count,
        -signals.max_tickets_in_14d_window,
        customer_source_id,
    )


def _rank(band: str) -> int:
    """The ordinal position of a band name, refusing one the vocabulary lacks."""
    try:
        return RiskBand(band).rank
    except ValueError as exc:
        raise IntelligenceConfigError(f"{band!r} is not a risk band") from exc


def _band_rule(entry: object, loc: str) -> BandRule:
    if not isinstance(entry, dict):
        raise IntelligenceConfigError(f"{loc}: expected a mapping")
    expected = {"id", "band", "when", "description", "because_documents"}
    optional = {"description", "because_documents"}
    missing = expected - optional - set(entry)
    unknown = set(map(str, entry)) - expected
    if missing or unknown:
        raise IntelligenceConfigError(
            f"{loc}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}"
        )
    rule_id = entry["id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise IntelligenceConfigError(f"{loc}.id: expected a non-empty string")
    band = entry["band"]
    if not isinstance(band, str) or band not in _BAND_NAMES:
        raise IntelligenceConfigError(
            f"{loc}.band: {band!r} is not a risk band; expected one of {sorted(_BAND_NAMES)}"
        )
    return BandRule(
        rule_id=rule_id,
        band=band,
        conditions=_conditions(entry["when"], f"{loc}.when"),
        description=str(entry.get("description", "")).strip(),
        because_documents=_documents(entry.get("because_documents"), f"{loc}.because_documents"),
    )


def _conditions(raw: object, loc: str) -> tuple[Condition, ...]:
    if not isinstance(raw, dict) or not raw:
        raise IntelligenceConfigError(
            f"{loc}: expected at least one condition; a rule with none would band every customer"
        )
    conditions = [_condition(key, value, loc) for key, value in sorted(raw.items())]
    return tuple(conditions)


def _condition(key: object, value: object, loc: str) -> Condition:
    name = str(key)
    where = f"{loc}.{name}"
    if name.endswith(_AT_LEAST) or name.endswith(_AT_MOST):
        at_least = name.endswith(_AT_LEAST)
        signal = name[: -len(_AT_LEAST)] if at_least else name[: -len(_AT_MOST)]
        if signal not in NUMERIC_BAND_INPUTS:
            raise IntelligenceConfigError(
                f"{where}: {signal!r} is not a counted band input. A band may be computed "
                f"only from {sorted(NUMERIC_BAND_INPUTS)}: money, SLA totals and chronic "
                f"backlog are reported beside a band, never inside it"
            )
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise IntelligenceConfigError(f"{where}: expected a threshold of at least 0")
        return Condition(
            signal=signal,
            comparison=Comparison.AT_LEAST if at_least else Comparison.AT_MOST,
            threshold=value,
        )
    if name not in BOOLEAN_BAND_INPUTS:
        raise IntelligenceConfigError(
            f"{where}: {name!r} is not a boolean band input. Expected one of "
            f"{sorted(BOOLEAN_BAND_INPUTS)}, or a counted input with an "
            f"{_AT_LEAST!r} or {_AT_MOST!r} suffix"
        )
    if not isinstance(value, bool):
        raise IntelligenceConfigError(f"{where}: expected true or false")
    return Condition(signal=name, comparison=Comparison.IS, threshold=value)


def _documents(raw: object, loc: str) -> tuple[str, ...]:
    """The documents a rule cites. Structural, never matched against text (plan A13)."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise IntelligenceConfigError(f"{loc}: expected a list of document ids")
    documents = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise IntelligenceConfigError(f"{loc}[{index}]: expected a document id")
        documents.append(value)
    return tuple(documents)


def band_rule_signals(rules: Sequence[BandRule]) -> frozenset[str]:
    """Every signal the table actually names. Used to prove what cannot drive a band."""
    return frozenset(
        condition.signal for rule in rules for condition in rule.conditions
    )


def rules_by_id(rules: Sequence[BandRule]) -> Mapping[str, BandRule]:
    """The table keyed by rule id, so a brief can quote the rule it satisfied."""
    return {rule.rule_id: rule for rule in rules}
