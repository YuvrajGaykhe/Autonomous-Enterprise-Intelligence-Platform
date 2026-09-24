"""
The decision configuration: the action catalogue and the conflict policy.

Both files are refused at load, naming what is broken, and nothing half-loads
(§A23, §0.5.2, §0.5.12). Every refusal the specification lists has a test
here, and each asserts the message names the entry -- by index and, when it
has one, by id -- because an error that says "invalid policy" without saying
which rule is how a broken rule survives a review.

The committed files are asserted **as content**, not merely as loadable: the
catalogue must be §0.4.1's table exactly, and the policy must be CONF-001
exactly. `version` is the file format and goes nowhere; `policy_version` is
the one version the decision layer carries (§0.5.6).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.decisions.policy import (
    BAND_AT_LEAST,
    BREACHES_AT_LEAST,
    DEFAULT_CATALOGUE_PATH,
    DEFAULT_POLICY_PATH,
    WHEN_CONDITIONS,
    ActionCatalogue,
    ConflictPolicy,
    DecisionConfigError,
    ResolutionCondition,
    default_action_catalogue,
    default_conflict_policy,
    load_action_catalogue,
    load_conflict_policy,
)
from app.intelligence.contract import ActionId, Function, RiskBand, Stance
from app.intelligence.errors import IntelligenceConfigError, IntelligenceError
from tests.unit.m6_support import (
    catalogue_data,
    flipped_policy,
    load_catalogue,
    load_policy,
    policy_data,
)

pytestmark = pytest.mark.unit

PAUSE = ActionId.PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED
ACCELERATE = ActionId.ACCELERATE_DEAL_CLOSE

#: §0.5.2 D-M6-B2's committed table: (function, object, stance) per action.
CATALOGUE = {
    ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA: (Function.SUPPORT, "customers", Stance.NEUTRAL),
    ActionId.SCHEDULE_EXECUTIVE_SPONSOR_CALL: (Function.SUPPORT, "customers", Stance.NEUTRAL),
    ActionId.ASSIGN_DEDICATED_SUPPORT_OWNER: (Function.SUPPORT, "customers", Stance.NEUTRAL),
    PAUSE: (Function.SUPPORT, "deals", Stance.RESTRAIN),
    ActionId.REVIEW_INVOICE_DISPUTE: (Function.SUPPORT, "support_tickets", Stance.NEUTRAL),
    ACCELERATE: (Function.SALES, "deals", Stance.ADVANCE),
    ActionId.NO_ACTION: (None, "customers", Stance.NEUTRAL),
}


def refused(match: str):
    return pytest.raises(DecisionConfigError, match=match)


def catalogue_with(index: int, **changes) -> dict:
    data = catalogue_data()
    data["actions"][index].update(changes)
    return data


def rule_with(**changes) -> dict:
    data = policy_data()
    data["conflicts"][0].update(changes)
    return data


# ---------------------------------------------------------------------------
# The committed catalogue
# ---------------------------------------------------------------------------


def test_the_committed_catalogue_is_the_specified_vocabulary_exactly():
    """§0.5.2's table, row for row: a drifted stance or function fails here."""
    catalogue = default_action_catalogue()

    assert {
        action: (entry.function, entry.object_type, entry.stance)
        for action, entry in catalogue.entries.items()
    } == CATALOGUE


def test_the_catalogue_declares_every_action_once_in_declaration_order():
    assert tuple(default_action_catalogue().entries) == tuple(ActionId)


def test_no_action_alone_is_proposed_by_no_function():
    catalogue = default_action_catalogue()

    assert [entry.action for entry in catalogue.entries.values() if not entry.proposable] == [
        ActionId.NO_ACTION
    ]


def test_the_catalogue_declares_no_precondition_and_no_threshold():
    """
    §0.5.2: the vocabulary only. §A16's three numbers stay M5 constants, so a
    catalogue entry that grew a threshold key would be refused at load.
    """
    for entry in catalogue_data()["actions"]:
        assert set(entry) == {"id", "function", "object", "stance"}


def test_the_committed_files_live_where_the_image_copies_them():
    assert DEFAULT_CATALOGUE_PATH.parts[-3:] == ("config", "intelligence",
                                                 "action_catalogue.yaml")
    assert DEFAULT_POLICY_PATH.parts[-3:] == ("config", "intelligence", "conflict_policy.yaml")


def test_the_committed_files_are_loaded_once():
    assert default_action_catalogue() is default_action_catalogue()
    assert default_conflict_policy() is default_conflict_policy()


def test_a_catalogue_entry_projects_to_plain_data():
    catalogue = default_action_catalogue()

    assert catalogue.entry(PAUSE).to_payload() == {
        "id": "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "function": "SUPPORT",
        "object": "deals", "stance": "RESTRAIN",
    }
    assert catalogue.entry(ActionId.NO_ACTION).to_payload()["function"] is None


def test_catalogue_types_are_immutable():
    entry = default_action_catalogue().entry(PAUSE)

    with pytest.raises(FrozenInstanceError):
        entry.stance = Stance.NEUTRAL  # type: ignore[misc]
    with pytest.raises(TypeError):
        default_action_catalogue().entries[PAUSE] = entry  # type: ignore[index]


# ---------------------------------------------------------------------------
# Catalogue refusals
# ---------------------------------------------------------------------------


def test_a_missing_catalogue_is_named(tmp_path):
    with refused("Action catalogue file not found"):
        load_action_catalogue(tmp_path / "absent.yaml")


def test_invalid_catalogue_yaml_is_reported_with_its_location(tmp_path):
    path = tmp_path / "action_catalogue.yaml"
    path.write_text("version: [1\n", encoding="utf-8")

    with refused("invalid YAML"):
        load_action_catalogue(path)


def test_a_catalogue_that_is_not_a_mapping_is_refused(tmp_path):
    with refused("expected a mapping"):
        load_catalogue(tmp_path, ["version", 1])


@pytest.mark.parametrize("key, match", [
    ("actions", r"missing keys \['actions'\]"),
    ("version", r"missing keys \['version'\]"),
])
def test_a_missing_catalogue_section_is_named(tmp_path, key, match):
    data = catalogue_data()
    del data[key]

    with refused(match):
        load_catalogue(tmp_path, data)


def test_an_unknown_catalogue_section_is_refused(tmp_path):
    with refused(r"unknown keys \['preconditions'\]"):
        load_catalogue(tmp_path, {**catalogue_data(), "preconditions": {}})


@pytest.mark.parametrize("version", [2, 0, True, "1", 1.0, None])
def test_an_unsupported_catalogue_format_is_refused(tmp_path, version):
    with refused("unsupported version"):
        load_catalogue(tmp_path, {**catalogue_data(), "version": version})


@pytest.mark.parametrize("actions", [[], {}, "ACCELERATE_DEAL_CLOSE", None])
def test_the_actions_must_be_a_non_empty_list(tmp_path, actions):
    with refused("actions: expected a non-empty list"):
        load_catalogue(tmp_path, {**catalogue_data(), "actions": actions})


def test_an_entry_that_is_not_a_mapping_is_named_by_index(tmp_path):
    data = catalogue_data()
    data["actions"][2] = "ASSIGN_DEDICATED_SUPPORT_OWNER"

    with refused(r"actions\[2\]: expected a mapping"):
        load_catalogue(tmp_path, data)


def test_an_entry_with_an_unknown_key_is_named_by_index_and_id(tmp_path):
    with refused(r"actions\[5\] \(ACCELERATE_DEAL_CLOSE\): .*unknown keys \['threshold'\]"):
        load_catalogue(tmp_path, catalogue_with(5, threshold=80))


def test_an_entry_missing_a_key_is_named(tmp_path):
    data = catalogue_data()
    del data["actions"][3]["stance"]

    with refused(r"actions\[3\] \(PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED\): "
                 r"missing keys \['stance'\]"):
        load_catalogue(tmp_path, data)


@pytest.mark.parametrize("action_id", [
    "accelerate_deal_close", "Accelerate_Deal_Close", "SELL_MORE", 7, None,
])
def test_an_id_outside_the_frozen_vocabulary_is_refused(tmp_path, action_id):
    """Exact and case-sensitive: the catalogue cannot widen M1's ActionId."""
    with refused(r"actions\[5\].*\.id: .* is not one of"):
        load_catalogue(tmp_path, catalogue_with(5, id=action_id))


def test_an_action_declared_twice_is_refused_by_name(tmp_path):
    data = catalogue_data()
    data["actions"].append(dict(data["actions"][5]))

    with refused(r"actions\[7\] \(ACCELERATE_DEAL_CLOSE\): already declared"):
        load_catalogue(tmp_path, data)


def test_an_action_left_out_is_named(tmp_path):
    data = catalogue_data()
    del data["actions"][4]

    with refused(r"no entry for \['REVIEW_INVOICE_DISPUTE'\]"):
        load_catalogue(tmp_path, data)


def test_no_action_must_be_proposed_by_no_function(tmp_path):
    with refused(r"actions\[6\] \(NO_ACTION\)\.function: .* must be null"):
        load_catalogue(tmp_path, catalogue_with(6, function="SUPPORT"))


def test_only_no_action_may_be_proposed_by_no_function(tmp_path):
    with refused(r"actions\[5\] \(ACCELERATE_DEAL_CLOSE\)\.function: only NO_ACTION"):
        load_catalogue(tmp_path, catalogue_with(5, function=None))


@pytest.mark.parametrize("function", ["MARKETING", "sales", "Sales", 1])
def test_a_function_outside_the_frozen_vocabulary_is_refused(tmp_path, function):
    with refused(r"\.function: .* is not one of \['SALES', 'SUPPORT'\]"):
        load_catalogue(tmp_path, catalogue_with(5, function=function))


@pytest.mark.parametrize("object_type", ["projects", "Deals", "deal", "", None, 3])
def test_an_object_outside_the_contested_entity_types_is_refused(tmp_path, object_type):
    with refused(r"actions\[3\] \(PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED\)\.object: "
                 r".* is not a contested entity type"):
        load_catalogue(tmp_path, catalogue_with(3, object=object_type))


@pytest.mark.parametrize("stance", ["advance", "FORWARD", None])
def test_a_stance_outside_the_frozen_vocabulary_is_refused(tmp_path, stance):
    with refused(r"\.stance: .* is not one of \['ADVANCE', 'NEUTRAL', 'RESTRAIN'\]"):
        load_catalogue(tmp_path, catalogue_with(5, stance=stance))


def test_a_catalogue_key_repeated_in_one_mapping_is_refused(tmp_path):
    """
    §0.5.12 row 10, applied to the catalogue: safe_load would keep the second
    stance silently, and a flipped stance is a flipped reading of the brief.
    """
    path = tmp_path / "action_catalogue.yaml"
    text = DEFAULT_CATALOGUE_PATH.read_text(encoding="utf-8").replace(
        "    stance: ADVANCE\n", "    stance: ADVANCE\n    stance: NEUTRAL\n")
    path.write_text(text, encoding="utf-8")

    with refused(r"line \d+: 'stance' is repeated in one mapping"):
        load_action_catalogue(path)


def test_the_error_is_a_configuration_fault_not_a_runtime_one():
    assert issubclass(DecisionConfigError, IntelligenceConfigError)
    assert not issubclass(DecisionConfigError, IntelligenceError)


# ---------------------------------------------------------------------------
# The committed policy
# ---------------------------------------------------------------------------


def test_the_committed_policy_is_conf_001_exactly():
    policy = default_conflict_policy()
    (rule,) = policy.rules

    assert policy.policy_version == 1
    assert rule.rule_id == "CONF-001"
    assert rule.between == (ACCELERATE, PAUSE)
    assert rule.resolve_to is PAUSE
    assert rule.overruled is ACCELERATE
    assert rule.when == ResolutionCondition(
        support_band_at_least=RiskBand.ELEVATED, open_sla_breach_high_count_at_least=1)
    assert rule.because_documents == ("DOC-003", "DOC-009")
    assert rule.rationale == (
        "An active support-policy escalation outranks deal acceleration on the same "
        "account, and the customer has explicitly linked the deal decision to "
        "resolution of the open tickets."
    )


def test_the_policy_keeps_the_catalogue_it_was_validated_against():
    assert default_conflict_policy().catalogue is default_action_catalogue()


def test_policy_version_is_the_only_version_the_policy_carries():
    """§0.5.6: `version` is the file format, read by the loader and nowhere else."""
    policy = default_conflict_policy()

    assert not hasattr(policy, "version")
    assert not hasattr(default_action_catalogue(), "version")
    assert policy_data()["version"] == 1


def test_a_policy_version_bump_is_carried(tmp_path):
    assert load_policy(tmp_path, {**policy_data(), "policy_version": 7}).policy_version == 7


def test_there_is_no_scope_key_and_one_is_refused(tmp_path):
    """§0.5.12: scope is structural. §A15's `scope: same_deal` no longer loads."""
    assert "scope" not in policy_data()["conflicts"][0]

    with refused(r"conflicts\[0\] \(CONF-001\): .*unknown keys \['scope'\]"):
        load_policy(tmp_path, rule_with(scope="same_deal"))


def test_the_rule_is_found_for_either_order_of_the_pair():
    policy = default_conflict_policy()

    assert policy.rule_for(PAUSE, ACCELERATE) is policy.rule_for(ACCELERATE, PAUSE)
    assert policy.declares_incompatible(PAUSE, ACCELERATE)
    assert policy.declares_incompatible(ACCELERATE, PAUSE)


def test_an_undeclared_pair_is_not_incompatible_and_has_no_rule():
    policy = default_conflict_policy()

    assert not policy.declares_incompatible(PAUSE, ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA)
    with pytest.raises(LookupError, match="declares no rule between"):
        policy.rule_for(PAUSE, ActionId.ESCALATE_TO_ACCOUNT_OWNER_PER_SLA)


def test_flipping_resolve_to_changes_the_winner_and_nothing_else(tmp_path):
    """§A25 test 3's lever, loaded: only resolve_to and what it derives differ."""
    committed, flipped = default_conflict_policy().rules[0], flipped_policy(tmp_path).rules[0]

    assert flipped.resolve_to is ACCELERATE
    assert flipped.overruled is PAUSE
    assert (flipped.rule_id, flipped.between, flipped.when, flipped.because_documents,
            flipped.rationale) == (committed.rule_id, committed.between, committed.when,
                                   committed.because_documents, committed.rationale)


def test_a_rule_projects_to_plain_data():
    assert default_conflict_policy().rules[0].to_payload() == {
        "id": "CONF-001",
        "between": ["ACCELERATE_DEAL_CLOSE", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"],
        "resolve_to": "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
        "when": {BAND_AT_LEAST: "ELEVATED", BREACHES_AT_LEAST: 1},
        "because_documents": ["DOC-003", "DOC-009"],
        "rationale": default_conflict_policy().rules[0].rationale,
    }


def test_policy_types_are_immutable():
    policy = default_conflict_policy()

    with pytest.raises(FrozenInstanceError):
        policy.policy_version = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.rules[0].resolve_to = ACCELERATE  # type: ignore[misc]
    assert isinstance(policy.rules, tuple)


# ---------------------------------------------------------------------------
# `when`: the whitelist and its evaluation
# ---------------------------------------------------------------------------


def test_the_when_vocabulary_is_exactly_the_two_section_a15_names():
    assert WHEN_CONDITIONS == {"support_band_at_least", "open_sla_breach_high_count_at_least"}


def test_a_condition_with_nothing_stated_cannot_be_built():
    with refused("must state at least one condition"):
        ResolutionCondition()


@pytest.mark.parametrize("band, s8, failing", [
    (RiskBand.CRITICAL, 3, ()),
    (RiskBand.ELEVATED, 1, ()),
    (RiskBand.WATCH, 1, (BAND_AT_LEAST,)),
    (RiskBand.ELEVATED, 0, (BREACHES_AT_LEAST,)),
    (RiskBand.NONE, 0, (BAND_AT_LEAST, BREACHES_AT_LEAST)),
])
def test_every_failing_condition_is_reported_with_the_value_observed(band, s8, failing):
    condition = default_conflict_policy().rules[0].when

    failures = condition.failures(band=band, open_sla_breach_high_count=s8)

    assert tuple(message.split()[0] for message in failures) == failing
    for message in failures:
        assert str(band) in message or f"S8 is {s8}" in message


def test_a_single_stated_condition_is_the_only_one_evaluated():
    band_only = ResolutionCondition(support_band_at_least=RiskBand.WATCH)
    breaches_only = ResolutionCondition(open_sla_breach_high_count_at_least=2)

    assert band_only.failures(band=RiskBand.WATCH, open_sla_breach_high_count=0) == ()
    assert breaches_only.failures(band=RiskBand.NONE, open_sla_breach_high_count=2) == ()
    assert band_only.to_payload() == {BAND_AT_LEAST: "WATCH"}
    assert breaches_only.to_payload() == {BREACHES_AT_LEAST: 2}


def test_bands_compare_by_rank_and_not_alphabetically():
    """"CRITICAL" < "ELEVATED" as strings; as bands it is the other way round."""
    condition = ResolutionCondition(support_band_at_least=RiskBand.ELEVATED)

    assert condition.failures(band=RiskBand.CRITICAL, open_sla_breach_high_count=0) == ()


# ---------------------------------------------------------------------------
# Policy refusals, each naming the broken rule
# ---------------------------------------------------------------------------


def test_a_missing_policy_is_named(tmp_path):
    with refused("Conflict policy file not found"):
        load_conflict_policy(tmp_path / "absent.yaml", catalogue=default_action_catalogue())


def test_invalid_policy_yaml_is_reported_with_its_location(tmp_path):
    path = tmp_path / "conflict_policy.yaml"
    path.write_text("conflicts: [\n", encoding="utf-8")

    with refused("invalid YAML"):
        load_conflict_policy(path, catalogue=default_action_catalogue())


def test_a_policy_that_is_not_a_mapping_is_refused(tmp_path):
    with refused("expected a mapping"):
        load_policy(tmp_path, "CONF-001")


def test_a_missing_policy_section_is_named(tmp_path):
    data = policy_data()
    del data["policy_version"]

    with refused(r"missing keys \['policy_version'\]"):
        load_policy(tmp_path, data)


def test_an_unknown_policy_section_is_refused(tmp_path):
    with refused(r"unknown keys \['default_winner'\]"):
        load_policy(tmp_path, {**policy_data(), "default_winner": "PAUSE"})


@pytest.mark.parametrize("version", [2, True, "1", 1.0])
def test_an_unsupported_policy_format_is_refused(tmp_path, version):
    with refused("unsupported version"):
        load_policy(tmp_path, {**policy_data(), "version": version})


@pytest.mark.parametrize("policy_version", [0, -1, True, "1", 1.5, None])
def test_policy_version_must_be_a_positive_integer(tmp_path, policy_version):
    with refused("policy_version: expected an integer of at least 1"):
        load_policy(tmp_path, {**policy_data(), "policy_version": policy_version})


@pytest.mark.parametrize("conflicts", [[], {}, None, "CONF-001"])
def test_a_policy_must_declare_at_least_one_rule(tmp_path, conflicts):
    with refused("conflicts: expected a non-empty list of rules"):
        load_policy(tmp_path, {**policy_data(), "conflicts": conflicts})


def test_a_rule_that_is_not_a_mapping_is_named_by_index(tmp_path):
    with refused(r"conflicts\[0\]: expected a mapping"):
        load_policy(tmp_path, {**policy_data(), "conflicts": ["CONF-001"]})


def test_a_rule_missing_a_key_is_named(tmp_path):
    data = policy_data()
    del data["conflicts"][0]["rationale"]

    with refused(r"conflicts\[0\] \(CONF-001\): missing keys \['rationale'\]"):
        load_policy(tmp_path, data)


@pytest.mark.parametrize("rule_id", ["", "   ", 1, None])
def test_a_rule_id_must_be_non_empty_text(tmp_path, rule_id):
    with refused(r"conflicts\[0\]\.id: expected a non-empty string"):
        load_policy(tmp_path, rule_with(id=rule_id))


@pytest.mark.parametrize("between", [
    ["PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"],
    ["PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "ACCELERATE_DEAL_CLOSE", "NO_ACTION"],
    "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED",
    None,
])
def test_between_names_exactly_two_actions(tmp_path, between):
    with refused(r"conflicts\[0\] \(CONF-001\)\.between: expected a list of exactly two"):
        load_policy(tmp_path, rule_with(between=between))


def test_between_names_only_catalogue_actions(tmp_path):
    with refused(r"CONF-001\)\.between\[1\]: 'PAUSE_DEAL' is not one of"):
        load_policy(tmp_path, rule_with(between=["ACCELERATE_DEAL_CLOSE", "PAUSE_DEAL"],
                                        resolve_to="ACCELERATE_DEAL_CLOSE"))


def test_between_names_two_distinct_actions(tmp_path):
    with refused(r"CONF-001\)\.between: names ACCELERATE_DEAL_CLOSE twice"):
        load_policy(tmp_path, rule_with(between=["ACCELERATE_DEAL_CLOSE"] * 2,
                                        resolve_to="ACCELERATE_DEAL_CLOSE"))


def test_no_action_cannot_take_part_in_a_conflict(tmp_path):
    with refused(r"CONF-001\)\.between: NO_ACTION is proposed by no function"):
        load_policy(tmp_path, rule_with(between=["ACCELERATE_DEAL_CLOSE", "NO_ACTION"],
                                        resolve_to="ACCELERATE_DEAL_CLOSE"))


def test_a_conflict_is_between_functions(tmp_path):
    with refused(r"CONF-001\)\.between: .* are both SUPPORT's"):
        load_policy(tmp_path, rule_with(
            between=["PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "ASSIGN_DEDICATED_SUPPORT_OWNER"],
            resolve_to="PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED"))


def test_a_conflict_is_over_one_object_type(tmp_path):
    """What makes CONF-001 a same-deal rule without a `scope` key."""
    with refused(r"ESCALATE_TO_ACCOUNT_OWNER_PER_SLA contests customers and "
                 r"ACCELERATE_DEAL_CLOSE contests deals"):
        load_policy(tmp_path, rule_with(
            between=["ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "ACCELERATE_DEAL_CLOSE"],
            resolve_to="ACCELERATE_DEAL_CLOSE"))


@pytest.mark.parametrize("resolve_to", [
    "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "NO_ACTION",
])
def test_resolve_to_must_be_one_of_the_pair(tmp_path, resolve_to):
    with refused(r"CONF-001\)\.resolve_to: .* is not one of"):
        load_policy(tmp_path, rule_with(resolve_to=resolve_to))


@pytest.mark.parametrize("resolve_to", ["pause", None, 1])
def test_resolve_to_must_be_an_action(tmp_path, resolve_to):
    with refused(r"CONF-001\)\.resolve_to: .* is not one of \["):
        load_policy(tmp_path, rule_with(resolve_to=resolve_to))


@pytest.mark.parametrize("when", [{}, None, [], "ELEVATED"])
def test_a_rule_states_at_least_one_condition(tmp_path, when):
    with refused(r"CONF-001\)\.when: expected at least one condition"):
        load_policy(tmp_path, rule_with(when=when))


@pytest.mark.parametrize("key", [
    "exposure_at_least", "band_at_least", "deal_amount_at_least", "probability_at_least",
])
def test_a_condition_outside_the_whitelist_is_refused(tmp_path, key):
    """In particular, no commercial value can decide a conflict."""
    with refused(rf"CONF-001\)\.when: unknown conditions \['{key}'\]"):
        load_policy(tmp_path, rule_with(when={BAND_AT_LEAST: "ELEVATED", key: 1}))


@pytest.mark.parametrize("band", ["elevated", "HIGH", "Elevated", None, 3])
def test_the_band_condition_is_an_exact_risk_band(tmp_path, band):
    with refused(rf"CONF-001\)\.when\.{BAND_AT_LEAST}: .* is not one of"):
        load_policy(tmp_path, rule_with(when={BAND_AT_LEAST: band}))


@pytest.mark.parametrize("count", [-1, True, "1", 1.5, None])
def test_the_breach_condition_is_a_count(tmp_path, count):
    with refused(rf"CONF-001\)\.when\.{BREACHES_AT_LEAST}: expected an integer of at least 0"):
        load_policy(tmp_path, rule_with(when={BREACHES_AT_LEAST: count}))


def test_either_condition_may_stand_alone(tmp_path):
    band_only = load_policy(tmp_path, rule_with(when={BAND_AT_LEAST: "WATCH"}))

    assert band_only.rules[0].when == ResolutionCondition(support_band_at_least=RiskBand.WATCH)


@pytest.mark.parametrize("documents, match", [
    ([], "must name the documents"),
    (None, "must name the documents"),
    ("DOC-003", "must name the documents"),
    (["DOC-003", ""], r"because_documents\[1\]: expected a document id"),
    (["DOC-003", " DOC-009"], r"because_documents\[1\]: expected a document id"),
    ([3], r"because_documents\[0\]: expected a document id"),
    (["DOC-003", "DOC-003"], r"because_documents\[1\]: DOC-003 is already cited"),
])
def test_a_rule_names_the_documents_it_is_justified_by(tmp_path, documents, match):
    with refused(rf"CONF-001\)\.{match}" if match.startswith("because") else match):
        load_policy(tmp_path, rule_with(because_documents=documents))


def test_cited_documents_are_held_in_id_order(tmp_path):
    policy = load_policy(tmp_path, rule_with(because_documents=["DOC-009", "DOC-003"]))

    assert policy.rules[0].because_documents == ("DOC-003", "DOC-009")


@pytest.mark.parametrize("rationale", ["", "  \n", None, 3])
def test_a_rule_states_its_rationale(tmp_path, rationale):
    with refused(r"CONF-001\)\.rationale: expected a non-empty string"):
        load_policy(tmp_path, rule_with(rationale=rationale))


def test_two_rules_may_not_share_an_id(tmp_path):
    data = policy_data()
    second = dict(data["conflicts"][0])
    data["conflicts"].append(second)

    with refused(r"conflicts\[1\] \(CONF-001\): id is already defined"):
        load_policy(tmp_path, data)


def test_two_rules_may_not_name_one_pair_whatever_their_when(tmp_path):
    """§0.5.12 row 9: disjoint `when`s do not make two candidate rules unambiguous."""
    data = policy_data()
    second = dict(data["conflicts"][0], id="CONF-002",
                  between=list(reversed(data["conflicts"][0]["between"])),
                  when={BAND_AT_LEAST: "NONE"})
    data["conflicts"].append(second)

    with refused(r"conflicts\[1\] \(CONF-002\): overlaps CONF-001"):
        load_policy(tmp_path, data)


def test_a_policy_key_repeated_in_one_mapping_is_refused(tmp_path):
    """§0.5.12 row 10: the second resolve_to would otherwise win silently."""
    path = tmp_path / "conflict_policy.yaml"
    text = DEFAULT_POLICY_PATH.read_text(encoding="utf-8").replace(
        "    resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED\n",
        "    resolve_to: PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED\n"
        "    resolve_to: ACCELERATE_DEAL_CLOSE\n")
    path.write_text(text, encoding="utf-8")

    with refused(r"line \d+: 'resolve_to' is repeated in one mapping"):
        load_conflict_policy(path, catalogue=default_action_catalogue())


def test_a_repeated_key_inside_a_list_item_is_found(tmp_path):
    path = tmp_path / "conflict_policy.yaml"
    text = DEFAULT_POLICY_PATH.read_text(encoding="utf-8").replace(
        "      open_sla_breach_high_count_at_least: 1\n",
        "      open_sla_breach_high_count_at_least: 1\n"
        "      open_sla_breach_high_count_at_least: 0\n")
    path.write_text(text, encoding="utf-8")

    with refused("'open_sla_breach_high_count_at_least' is repeated"):
        load_conflict_policy(path, catalogue=default_action_catalogue())


def test_a_broken_later_rule_loads_nothing(tmp_path):
    """No partial policy: a valid first rule does not survive a broken second one."""
    data = policy_data()
    data["conflicts"].append({"id": "CONF-002"})

    with refused(r"conflicts\[1\] \(CONF-002\): missing keys"):
        load_policy(tmp_path, data)


def test_the_policy_is_validated_against_the_catalogue_it_is_given(tmp_path):
    """A catalogue that moves PAUSE onto customers makes CONF-001 span two object types."""
    data = catalogue_data()
    data["actions"][3]["object"] = "customers"
    catalogue = load_catalogue(tmp_path, data)

    with refused("contests customers"):
        load_policy(tmp_path, policy_data(), catalogue=catalogue)


def test_loaded_objects_are_the_declared_types(tmp_path):
    assert isinstance(load_catalogue(tmp_path, catalogue_data()), ActionCatalogue)
    assert isinstance(load_policy(tmp_path, policy_data()), ConflictPolicy)
