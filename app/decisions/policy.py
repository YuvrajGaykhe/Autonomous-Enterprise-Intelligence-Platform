"""
The decision configuration: the action catalogue and the conflict policy (VS-01 M6).

Two files under config/intelligence/, loaded and validated here and nowhere
else, in the convention app/intelligence/config.py set for risk_rules.yaml:
a missing file is named, invalid YAML is reported with its location, every
section is checked for exactly its keys, and the result is a complete frozen
object or an exception. Nothing half-loads (plan §A23): a policy that loaded
three rules of four would resolve plausibly and wrongly.

    action_catalogue.yaml   a DECLARATIVE VOCABULARY (§0.5.2 D-M6-B2): for
                            every ActionId, who may propose it, what kind of
                            object it contests and which way it pulls. It
                            holds no precondition and no threshold. §A16's
                            three numbers stay M5 code, as named constants in
                            app/analysts/base.py; they are neither moved here
                            nor copied here, and M5 remains the only thing
                            that decides whether an action is proposed.
    conflict_policy.yaml    which pairs of actions are incompatible, and for
                            each pair the rule that decides between them
                            (§0.5.12). Validated against the catalogue, which
                            it keeps, so a policy and a catalogue cannot be
                            mismatched at the call site.

**One version, one meaning** (§0.5.6 D-M6-B6). Both files carry a `version`
that is the file format, must be 1, and never leaves this module.
`policy_version` is THE version of the decision configuration -- the policy
and the catalogue it is validated against -- and is what every
Reconciliation carries.

**A repeated YAML key is refused.** yaml.safe_load keeps the last of two
equal keys silently, so a second `resolve_to` would flip a winner unseen --
exactly the lever §A25's policy-liveness test pulls on purpose. The document
is therefore composed first, with the safe loader, and every mapping node is
checked for a repeated key before any value is constructed. This is the one
authored strengthening over load_risk_rules (§0.5.12 row 10); it constructs
nothing, so it widens nothing the G2 deserialisation boundary forbids.

Nothing here reads a database, a clock or a model.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from app.intelligence.contract import ActionId, Function, RiskBand, Stance
from app.intelligence.errors import IntelligenceConfigError

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "intelligence"
DEFAULT_CATALOGUE_PATH = CONFIG_DIR / "action_catalogue.yaml"
DEFAULT_POLICY_PATH = CONFIG_DIR / "conflict_policy.yaml"

#: The file format both files declare. Not a policy version (§0.5.6).
FORMAT_VERSION = 1

#: The entity types an action may contest, as Position.object_ref names them:
#: the three §0.4.1 fixes. A later slice that contests another type widens
#: this set deliberately.
OBJECT_TYPES = frozenset({"customers", "deals", "support_tickets"})

#: The whole `when` vocabulary (§0.5.12 row 6). A rule may name nothing else,
#: and in particular no commercial value.
BAND_AT_LEAST = "support_band_at_least"
BREACHES_AT_LEAST = "open_sla_breach_high_count_at_least"
WHEN_CONDITIONS = frozenset({BAND_AT_LEAST, BREACHES_AT_LEAST})

_CATALOGUE_KEYS = frozenset({"version", "actions"})
_ENTRY_KEYS = frozenset({"id", "function", "object", "stance"})
_POLICY_KEYS = frozenset({"version", "policy_version", "conflicts"})
_RULE_KEYS = frozenset({"id", "between", "resolve_to", "when", "because_documents", "rationale"})

_Member = TypeVar("_Member", bound=StrEnum)


class DecisionConfigError(IntelligenceConfigError):
    """
    The action catalogue or the conflict policy is missing or inconsistent.

    A deployment fault, not a runtime decision failure: like M1's
    IntelligenceConfigError, which it extends, it is deliberately not an
    IntelligenceError, so a caller can tell a broken file from a customer
    whose conflict cannot be resolved.
    """


# ---------------------------------------------------------------------------
# The action catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogueEntry:
    """What one action is: who proposes it, what it contests, which way it pulls."""

    action: ActionId
    function: Function | None
    object_type: str
    stance: Stance

    @property
    def proposable(self) -> bool:
        """Whether any function proposes this action. False for NO_ACTION alone."""
        return self.function is not None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": str(self.action),
            "function": None if self.function is None else str(self.function),
            "object": self.object_type,
            "stance": str(self.stance),
        }


@dataclass(frozen=True)
class ActionCatalogue:
    """Exactly one entry per ActionId, keyed in ActionId declaration order."""

    entries: Mapping[ActionId, CatalogueEntry]

    def entry(self, action: ActionId) -> CatalogueEntry:
        """The entry for an action. Every ActionId has one, or the file did not load."""
        return self.entries[action]


@functools.lru_cache(maxsize=1)
def default_action_catalogue() -> ActionCatalogue:
    """Load (once) the repository action catalogue."""
    return load_action_catalogue(DEFAULT_CATALOGUE_PATH)


def load_action_catalogue(path: str | Path) -> ActionCatalogue:
    """Load and validate an action catalogue, refusing a broken entry by name."""
    path = Path(path)
    where = str(path)
    data = _exact_keys(_read(path, "Action catalogue"), where, _CATALOGUE_KEYS)
    _format_version(data["version"], where)
    raw = data["actions"]
    if not isinstance(raw, list) or not raw:
        raise DecisionConfigError(f"{where}: actions: expected a non-empty list of actions")
    entries: dict[ActionId, CatalogueEntry] = {}
    for index, item in enumerate(raw):
        entry = _catalogue_entry(item, f"{where}: actions[{index}]")
        if entry.action in entries:
            raise DecisionConfigError(
                f"{where}: actions[{index}] ({entry.action}): already declared. Two entries "
                f"for one action would make its function and stance ambiguous"
            )
        entries[entry.action] = entry
    missing = [str(action) for action in ActionId if action not in entries]
    if missing:
        raise DecisionConfigError(
            f"{where}: actions: no entry for {missing}. The catalogue is the whole action "
            f"vocabulary, so every ActionId must be declared exactly once"
        )
    return ActionCatalogue(
        entries=MappingProxyType({action: entries[action] for action in ActionId})
    )


def _catalogue_entry(item: object, loc: str) -> CatalogueEntry:
    if not isinstance(item, dict):
        raise DecisionConfigError(f"{loc}: expected a mapping")
    loc = _named(loc, item.get("id"))
    _exact_keys(item, loc, _ENTRY_KEYS)
    action = _member(ActionId, item["id"], f"{loc}.id")
    object_type = item["object"]
    if not isinstance(object_type, str) or object_type not in OBJECT_TYPES:
        raise DecisionConfigError(
            f"{loc}.object: {object_type!r} is not a contested entity type; expected one of "
            f"{sorted(OBJECT_TYPES)}"
        )
    return CatalogueEntry(
        action=action,
        function=_proposer(item["function"], action, f"{loc}.function"),
        object_type=object_type,
        stance=_member(Stance, item["stance"], f"{loc}.stance"),
    )


def _proposer(value: object, action: ActionId, loc: str) -> Function | None:
    """
    The function that proposes an action: null for NO_ACTION, and only for it.

    §A16 leaves NO_ACTION's *Proposed by* column empty and §0.4.1 has neither
    analyst emit it, so it is the one action no function may propose. Every
    other action has a proposer, or no position could ever carry it.
    """
    if action is ActionId.NO_ACTION:
        if value is not None:
            raise DecisionConfigError(
                f"{loc}: {ActionId.NO_ACTION} is proposed by no function, so its function "
                f"must be null, not {value!r}"
            )
        return None
    if value is None:
        raise DecisionConfigError(
            f"{loc}: only {ActionId.NO_ACTION} may be proposed by no function; {action} needs one"
        )
    return _member(Function, value, loc)


# ---------------------------------------------------------------------------
# The conflict policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionCondition:
    """
    A rule's `when`: every stated condition must hold for the rule to apply.

    A condition left as None is not stated and is not evaluated. A rule with
    no condition at all would resolve every conflict of its pair
    unconditionally, which no rule may do (§0.5.12 row 6), so the empty
    condition cannot be built.
    """

    support_band_at_least: RiskBand | None = None
    open_sla_breach_high_count_at_least: int | None = None

    def __post_init__(self) -> None:
        if self.support_band_at_least is None and self.open_sla_breach_high_count_at_least is None:
            raise DecisionConfigError("a rule's `when` must state at least one condition")

    def failures(self, *, band: RiskBand, open_sla_breach_high_count: int) -> tuple[str, ...]:
        """
        Every stated condition that does not hold, each with the value observed.

        Empty when the rule applies. Reported whole rather than at the first
        failure, so an unresolvable conflict says everything that is wrong.
        """
        failed = []
        required_band = self.support_band_at_least
        if required_band is not None and not band.at_least(required_band):
            failed.append(f"{BAND_AT_LEAST} {required_band} does not hold: the band is {band}")
        required = self.open_sla_breach_high_count_at_least
        if required is not None and open_sla_breach_high_count < required:
            failed.append(
                f"{BREACHES_AT_LEAST} {required} does not hold: S8 is {open_sla_breach_high_count}"
            )
        return tuple(failed)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.support_band_at_least is not None:
            payload[BAND_AT_LEAST] = str(self.support_band_at_least)
        if self.open_sla_breach_high_count_at_least is not None:
            payload[BREACHES_AT_LEAST] = self.open_sla_breach_high_count_at_least
        return payload


@dataclass(frozen=True)
class ConflictRule:
    """One versioned rule: an incompatible pair, and which of the two prevails when."""

    rule_id: str
    between: tuple[ActionId, ActionId]
    resolve_to: ActionId
    when: ResolutionCondition
    because_documents: tuple[str, ...]
    rationale: str

    @property
    def pair(self) -> frozenset[ActionId]:
        """The pair as a set: which action a position proposes first is not an order."""
        return frozenset(self.between)

    @property
    def overruled(self) -> ActionId:
        """The action this rule overrules when it applies."""
        first, second = self.between
        return second if first is self.resolve_to else first

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.rule_id,
            "between": [str(action) for action in self.between],
            "resolve_to": str(self.resolve_to),
            "when": self.when.to_payload(),
            "because_documents": list(self.because_documents),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ConflictPolicy:
    """The complete, validated conflict policy and the catalogue it was validated against."""

    policy_version: int
    rules: tuple[ConflictRule, ...]
    catalogue: ActionCatalogue

    def declares_incompatible(self, first: ActionId, second: ActionId) -> bool:
        """Whether some rule names this pair. Only a declared pair is ever a conflict."""
        pair = frozenset({first, second})
        return any(rule.pair == pair for rule in self.rules)

    def rule_for(self, first: ActionId, second: ActionId) -> ConflictRule:
        """
        The one rule naming this pair.

        At most one exists, because overlapping rules are refused at load.
        Asking for a pair no rule declares is a caller error -- detection
        only ever reports declared pairs -- so it raises rather than
        returning a default.
        """
        pair = frozenset({first, second})
        for rule in self.rules:
            if rule.pair == pair:
                return rule
        raise LookupError(
            f"conflict policy {self.policy_version} declares no rule between {first} and {second}"
        )


@functools.lru_cache(maxsize=1)
def default_conflict_policy() -> ConflictPolicy:
    """Load (once) the repository conflict policy, against the repository catalogue."""
    return load_conflict_policy(DEFAULT_POLICY_PATH, catalogue=default_action_catalogue())


def load_conflict_policy(path: str | Path, *, catalogue: ActionCatalogue) -> ConflictPolicy:
    """
    Load and validate a conflict policy against a catalogue, refusing a broken rule by name.

    Plan §A23: invalid policy configuration is refused at load, naming the
    broken rule, and no partial policy is produced.
    """
    path = Path(path)
    where = str(path)
    data = _exact_keys(_read(path, "Conflict policy"), where, _POLICY_KEYS)
    _format_version(data["version"], where)
    policy_version = _positive_int(data["policy_version"], f"{where}: policy_version")
    raw = data["conflicts"]
    if not isinstance(raw, list) or not raw:
        raise DecisionConfigError(
            f"{where}: conflicts: expected a non-empty list of rules; a policy with none "
            f"would declare no pair incompatible, and no conflict could ever be detected"
        )
    rules: list[ConflictRule] = []
    for index, item in enumerate(raw):
        loc = f"{where}: conflicts[{index}]"
        rule = _rule(item, loc, catalogue)
        for earlier in rules:
            if earlier.rule_id == rule.rule_id:
                raise DecisionConfigError(
                    f"{loc} ({rule.rule_id}): id is already defined. Two rules sharing an id "
                    f"make the policy id a resolution names ambiguous"
                )
            if earlier.pair == rule.pair:
                raise DecisionConfigError(
                    f"{loc} ({rule.rule_id}): overlaps {earlier.rule_id}, which already names "
                    f"{sorted(str(action) for action in rule.pair)}. Two candidate rules for one "
                    f"conflict are ambiguous whatever their `when`"
                )
        rules.append(rule)
    return ConflictPolicy(policy_version=policy_version, rules=tuple(rules), catalogue=catalogue)


def _rule(item: object, loc: str, catalogue: ActionCatalogue) -> ConflictRule:
    if not isinstance(item, dict):
        raise DecisionConfigError(f"{loc}: expected a mapping")
    loc = _named(loc, item.get("id"))
    _exact_keys(item, loc, _RULE_KEYS)
    rule_id = _text(item["id"], f"{loc}.id")
    between = _between(item["between"], f"{loc}.between", catalogue)
    resolve_to = _member(ActionId, item["resolve_to"], f"{loc}.resolve_to")
    if resolve_to not in between:
        raise DecisionConfigError(
            f"{loc}.resolve_to: {resolve_to} is not one of {[str(action) for action in between]}; "
            f"a rule can only decide between the two actions it names"
        )
    return ConflictRule(
        rule_id=rule_id,
        between=between,
        resolve_to=resolve_to,
        when=_when(item["when"], f"{loc}.when"),
        because_documents=_documents(item["because_documents"], f"{loc}.because_documents"),
        rationale=_text(item["rationale"], f"{loc}.rationale").strip(),
    )


def _between(raw: object, loc: str, catalogue: ActionCatalogue) -> tuple[ActionId, ActionId]:
    """
    Two distinct, proposable actions of different functions contesting one object type.

    The catalogue is what makes each clause checkable. Different functions,
    because frozen Conflict admits one position per function; one object type,
    because a conflict is over one object (§0.5.10), which is what makes
    CONF-001 a same-deal rule without a `scope` key.
    """
    if not isinstance(raw, list) or len(raw) != 2:
        raise DecisionConfigError(f"{loc}: expected a list of exactly two actions")
    first = _member(ActionId, raw[0], f"{loc}[0]")
    second = _member(ActionId, raw[1], f"{loc}[1]")
    if first is second:
        raise DecisionConfigError(f"{loc}: names {first} twice; a conflict needs two actions")
    entries = (catalogue.entry(first), catalogue.entry(second))
    for entry in entries:
        if not entry.proposable:
            raise DecisionConfigError(
                f"{loc}: {entry.action} is proposed by no function, so no position can carry "
                f"it and it cannot take part in a conflict"
            )
    if entries[0].function is entries[1].function:
        raise DecisionConfigError(
            f"{loc}: {first} and {second} are both {entries[0].function}'s. A conflict is "
            f"between functions, and one function never states two positions in one"
        )
    if entries[0].object_type != entries[1].object_type:
        raise DecisionConfigError(
            f"{loc}: {first} contests {entries[0].object_type} and {second} contests "
            f"{entries[1].object_type}; a conflict is over one object"
        )
    ordered = sorted((first, second), key=str)
    return ordered[0], ordered[1]


def _when(raw: object, loc: str) -> ResolutionCondition:
    if not isinstance(raw, dict) or not raw:
        raise DecisionConfigError(
            f"{loc}: expected at least one condition; a rule with none would resolve every "
            f"conflict of its pair unconditionally"
        )
    unknown = sorted(set(map(str, raw)) - WHEN_CONDITIONS)
    if unknown:
        raise DecisionConfigError(
            f"{loc}: unknown conditions {unknown}; a rule may name only {sorted(WHEN_CONDITIONS)}"
        )
    return ResolutionCondition(
        support_band_at_least=(
            _member(RiskBand, raw[BAND_AT_LEAST], f"{loc}.{BAND_AT_LEAST}")
            if BAND_AT_LEAST in raw else None
        ),
        open_sla_breach_high_count_at_least=(
            _count(raw[BREACHES_AT_LEAST], f"{loc}.{BREACHES_AT_LEAST}")
            if BREACHES_AT_LEAST in raw else None
        ),
    )


def _documents(raw: object, loc: str) -> tuple[str, ...]:
    """
    The documents a rule is cited from, ascending by id.

    Structural citations, never matched against text (§A13). An id with
    surrounding whitespace would build a citation that resolves to nothing,
    and a repeated one would cite the same ground twice.
    """
    if not isinstance(raw, list) or not raw:
        raise DecisionConfigError(
            f"{loc}: a rule must name the documents it is justified by"
        )
    documents: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise DecisionConfigError(
                f"{loc}[{index}]: expected a document id, got {value!r}"
            )
        if value in documents:
            raise DecisionConfigError(f"{loc}[{index}]: {value} is already cited")
        documents.append(value)
    return tuple(sorted(documents))


# ---------------------------------------------------------------------------
# Shared parsing
# ---------------------------------------------------------------------------


def _read(path: Path, what: str) -> object:
    """A file's YAML, with a repeated mapping key refused before anything is constructed."""
    if not path.is_file():
        raise DecisionConfigError(f"{what} file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        _refuse_repeated_keys(yaml.compose(text, Loader=yaml.SafeLoader), str(path))
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DecisionConfigError(f"{path}: invalid YAML: {exc}") from exc


def _refuse_repeated_keys(node: Node | None, where: str) -> None:
    """Walk a composed document and refuse any mapping that states one key twice."""
    if isinstance(node, MappingNode):
        seen: list[str] = []
        for key, value in node.value:
            if isinstance(key, ScalarNode):
                if key.value in seen:
                    raise DecisionConfigError(
                        f"{where}: line {key.start_mark.line + 1}: {key.value!r} is repeated in "
                        f"one mapping; YAML would silently keep only the last value"
                    )
                seen.append(key.value)
            _refuse_repeated_keys(value, where)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            _refuse_repeated_keys(item, where)


def _exact_keys(data: object, loc: str, expected: frozenset[str]) -> dict[str, object]:
    """A mapping with exactly the expected keys: a missing one and an unknown one are both named."""
    if not isinstance(data, dict):
        raise DecisionConfigError(f"{loc}: expected a mapping")
    missing = sorted(expected - set(map(str, data)))
    unknown = sorted(set(map(str, data)) - expected)
    if missing or unknown:
        raise DecisionConfigError(f"{loc}: missing keys {missing}, unknown keys {unknown}")
    return data


def _named(loc: str, identifier: object) -> str:
    """Name an entry by its id as well as its position, when it has a usable one."""
    if isinstance(identifier, str) and identifier.strip():
        return f"{loc} ({identifier})"
    return loc


def _format_version(value: object, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != FORMAT_VERSION:
        raise DecisionConfigError(f"{where}: unsupported version {value!r}")


def _member(enum: type[_Member], value: object, loc: str) -> _Member:
    """An exact, case-sensitive member of a frozen M1 vocabulary."""
    names = sorted(str(member) for member in enum)
    if not isinstance(value, str) or value not in names:
        raise DecisionConfigError(f"{loc}: {value!r} is not one of {names}")
    return enum(value)


def _text(value: object, loc: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecisionConfigError(f"{loc}: expected a non-empty string")
    return value


def _positive_int(value: object, loc: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DecisionConfigError(f"{loc}: expected an integer of at least 1")
    return value


def _count(value: object, loc: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DecisionConfigError(f"{loc}: expected an integer of at least 0")
    return value
