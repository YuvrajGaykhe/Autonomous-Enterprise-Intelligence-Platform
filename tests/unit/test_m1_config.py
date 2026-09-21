"""
M1 risk-rule configuration: the pinned evaluation date and the fingerprint gate.

The pin is the guard M0 chose. A database prepared the wrong way produces a
different fingerprint and must be refused at the door rather than assessed,
so a broken or absent pin has to be a load-time failure, never a default.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from app.intelligence.config import (
    DEFAULT_CONFIG_PATH,
    RiskRulesConfig,
    default_risk_rules,
    load_risk_rules,
)
from app.intelligence.errors import IntelligenceConfigError

CSV_DEMO_FINGERPRINT = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"

#: A complete file. M3 added lookback_days, the DOC-003 targets and window,
#: and the band table, and M4 added linker_version; the loader refuses
#: unknown *and* missing keys, so a minimal fixture has to carry every
#: section the committed file carries. Each milestone that adds a required
#: key EXTENDS this fixture - the loader's strictness is the thing being
#: tested, so it is never relaxed to let an incomplete fixture through.
VALID = {
    "version": 1,
    "rules_version": 1,
    "linker_version": "1",
    "acceptance_as_of": date(2026, 9, 18),
    "layer1_fingerprints": {"csv_demo": CSV_DEMO_FINGERPRINT},
    "lookback_days": 90,
    "sla_resolution_targets": {"high": 1, "medium": 5},
    "escalation": {
        "window_days": 14,
        "ticket_threshold": 3,
        "because_documents": ["DOC-003"],
    },
    "bands": [
        {"id": "R-CRIT-001", "band": "CRITICAL",
         "when": {"policy_escalation_state": True,
                  "open_sla_breach_high_count_at_least": 2}},
    ],
}


def write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "risk_rules.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def load_with(tmp_path: Path, **overrides) -> RiskRulesConfig:
    data = {**VALID, **overrides}
    return load_risk_rules(write(tmp_path, data))


# ---------------------------------------------------------------------------
# The committed configuration
# ---------------------------------------------------------------------------


def test_the_committed_configuration_pins_the_acceptance_date_and_the_snapshot():
    config = default_risk_rules()

    assert config.rules_version == 1
    assert config.acceptance_as_of == date(2026, 9, 18)
    assert config.pinned_fingerprint("csv_demo") == CSV_DEMO_FINGERPRINT


def test_the_committed_configuration_is_loaded_once_and_lives_where_the_image_copies_it():
    assert default_risk_rules() is default_risk_rules()
    assert DEFAULT_CONFIG_PATH.is_file()
    assert DEFAULT_CONFIG_PATH.parts[-3:] == ("config", "intelligence", "risk_rules.yaml")


def test_the_pinned_date_is_a_date_and_not_a_timestamp():
    """now() is forbidden, and an as_of with a time of day is not an evaluation date."""
    acceptance_as_of = default_risk_rules().acceptance_as_of

    assert type(acceptance_as_of) is date


def test_an_unpinned_source_system_is_refused_rather_than_assessed_unguarded():
    with pytest.raises(IntelligenceConfigError, match="no layer1_fingerprint is pinned"):
        default_risk_rules().pinned_fingerprint("odoo_mock")


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def test_a_missing_file_is_named_rather_than_defaulted(tmp_path):
    with pytest.raises(IntelligenceConfigError, match="not found"):
        load_risk_rules(tmp_path / "absent.yaml")


def test_invalid_yaml_is_reported_with_its_location(tmp_path):
    path = tmp_path / "risk_rules.yaml"
    path.write_text("version: 1\n  rules_version: [\n", encoding="utf-8")

    with pytest.raises(IntelligenceConfigError, match="invalid YAML"):
        load_risk_rules(path)


def test_a_file_that_is_not_a_mapping_is_refused(tmp_path):
    with pytest.raises(IntelligenceConfigError, match="expected a mapping"):
        load_risk_rules(write(tmp_path, ["version", 1]))


def test_an_unsupported_version_is_refused(tmp_path):
    with pytest.raises(IntelligenceConfigError, match="unsupported version 2"):
        load_with(tmp_path, version=2)


def test_a_missing_key_is_named(tmp_path):
    data = dict(VALID)
    del data["rules_version"]

    with pytest.raises(IntelligenceConfigError, match=r"missing keys \['rules_version'\]"):
        load_risk_rules(write(tmp_path, data))


def test_an_unknown_key_is_refused_so_a_new_section_arrives_deliberately(tmp_path):
    """
    `bands` was the unknown key this test named until M3 added it.

    It is a known section now, which is the outcome the guard existed to
    make deliberate, so the guard moves to a key no milestone has claimed:
    a tuned weight, which strategy 4.2 forbids project-wide.
    """
    with pytest.raises(IntelligenceConfigError, match=r"unknown keys \['weights'\]"):
        load_with(tmp_path, weights={})


@pytest.mark.parametrize("rules_version", [0, -1, True, "1", 1.0, None])
def test_the_rules_version_must_be_a_positive_integer(tmp_path, rules_version):
    with pytest.raises(IntelligenceConfigError, match="integer of at least 1"):
        load_with(tmp_path, rules_version=rules_version)


def test_the_linker_version_loads_as_a_non_empty_string(tmp_path):
    """
    Plan §0.3.5. Deliberately a STRING where rules_version is an int:
    DerivedLink validates linker_version with a non-empty-string rule, and
    the frozen contract wins over this file's local integer convention.
    """
    config = load_with(tmp_path, linker_version="7")

    assert config.linker_version == "7"
    assert isinstance(config.rules_version, int)


@pytest.mark.parametrize("linker_version", ["", "   ", 1, 1.0, True, None, ["1"]])
def test_the_linker_version_must_be_a_non_empty_string(tmp_path, linker_version):
    """
    Refused at load naming the broken key (plan A23), rather than surfacing
    later as a ContractViolationError when the first link is constructed.
    """
    with pytest.raises(IntelligenceConfigError, match="expected a non-empty string"):
        load_with(tmp_path, linker_version=linker_version)


@pytest.mark.parametrize("as_of", ["2026-09-18", 20260918, None])
def test_the_acceptance_date_must_be_a_calendar_date(tmp_path, as_of):
    with pytest.raises(IntelligenceConfigError, match="expected a YYYY-MM-DD date"):
        load_with(tmp_path, acceptance_as_of=as_of)


def test_a_timestamp_is_not_an_acceptance_date(tmp_path):
    path = tmp_path / "risk_rules.yaml"
    data = {**VALID, "acceptance_as_of": "PLACEHOLDER"}
    text = yaml.safe_dump(data).replace(
        "acceptance_as_of: PLACEHOLDER", "acceptance_as_of: 2026-09-18 10:30:00"
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(IntelligenceConfigError, match="expected a YYYY-MM-DD date"):
        load_risk_rules(path)


@pytest.mark.parametrize("fingerprints", [{}, [], "csv_demo", None])
def test_at_least_one_snapshot_must_be_pinned(tmp_path, fingerprints):
    with pytest.raises(IntelligenceConfigError, match="expected a non-empty mapping"):
        load_with(tmp_path, layer1_fingerprints=fingerprints)


def test_a_pin_for_an_unknown_source_system_is_refused(tmp_path):
    """The source vocabulary is Layer 1's, and Layer 2 does not widen it."""
    with pytest.raises(IntelligenceConfigError, match="not a configured source system"):
        load_with(tmp_path, layer1_fingerprints={"csv_demo_bad": CSV_DEMO_FINGERPRINT})


@pytest.mark.parametrize("digest", [
    "", "not-a-digest", CSV_DEMO_FINGERPRINT[:-1], CSV_DEMO_FINGERPRINT.upper(), 12345, None,
])
def test_a_pin_must_be_a_sha_256_digest(tmp_path, digest):
    with pytest.raises(IntelligenceConfigError, match="64-character hex SHA-256"):
        load_with(tmp_path, layer1_fingerprints={"csv_demo": digest})


def test_every_configured_source_system_may_carry_its_own_pin(tmp_path):
    other = "0" * 64
    config = load_with(tmp_path, layer1_fingerprints={
        "csv_demo": CSV_DEMO_FINGERPRINT, "odoo_mock": other})

    assert config.pinned_fingerprint("odoo_mock") == other


# ---------------------------------------------------------------------------
# What M3 measures with: the lookback, DOC-003's targets, and its window
# ---------------------------------------------------------------------------


def test_the_committed_configuration_carries_what_m3_measures_with():
    config = default_risk_rules()

    assert config.lookback_days == 90
    assert dict(config.sla_resolution_targets) == {"high": 1, "medium": 5}
    assert config.escalation.window_days == 14
    assert config.escalation.ticket_threshold == 3
    assert config.escalation.because_documents == ("DOC-003",)


@pytest.mark.parametrize("lookback_days", [0, -1, True, "90", 90.0, None])
def test_the_lookback_must_be_a_positive_integer(tmp_path, lookback_days):
    with pytest.raises(IntelligenceConfigError, match="integer of at least 1"):
        load_with(tmp_path, lookback_days=lookback_days)


@pytest.mark.parametrize("targets", [{}, [], "high", None, 1])
def test_the_sla_targets_must_be_a_non_empty_mapping(tmp_path, targets):
    with pytest.raises(IntelligenceConfigError, match="expected a non-empty mapping"):
        load_with(tmp_path, sla_resolution_targets=targets)


@pytest.mark.parametrize("priority", ["urgent", "HIGH", "low"])
def test_a_target_for_a_priority_layer_1_does_not_have_is_refused(tmp_path, priority):
    """The D1 enum is the vocabulary. Layer 2 may not widen it to suit a rule."""
    with pytest.raises(IntelligenceConfigError, match="is not a Layer 1 priority value"):
        load_with(tmp_path, sla_resolution_targets={priority: 1})


@pytest.mark.parametrize("days", [0, -1, True, "1", None])
def test_a_resolution_target_must_be_a_positive_number_of_business_days(tmp_path, days):
    with pytest.raises(IntelligenceConfigError, match="integer of at least 1"):
        load_with(tmp_path, sla_resolution_targets={"high": days})


@pytest.mark.parametrize("escalation", ["DOC-003", [], None, 3])
def test_the_escalation_policy_must_be_a_mapping(tmp_path, escalation):
    with pytest.raises(IntelligenceConfigError, match="expected a mapping"):
        load_with(tmp_path, escalation=escalation)


def test_an_escalation_policy_missing_a_key_is_refused_by_name(tmp_path):
    with pytest.raises(IntelligenceConfigError, match=r"missing keys \['window_days'\]"):
        load_with(tmp_path, escalation={"ticket_threshold": 3,
                                        "because_documents": ["DOC-003"]})


def test_an_escalation_policy_carrying_an_unknown_key_is_refused(tmp_path):
    with pytest.raises(IntelligenceConfigError, match=r"unknown keys \['weight'\]"):
        load_with(tmp_path, escalation={"window_days": 14, "ticket_threshold": 3,
                                        "because_documents": ["DOC-003"], "weight": 1})


@pytest.mark.parametrize("documents", [[], "DOC-003", None, {}])
def test_an_escalation_policy_must_name_the_document_it_came_from(tmp_path, documents):
    """Plan A13: a policy citation is structural, so the rule names its source."""
    with pytest.raises(IntelligenceConfigError, match="must name the document it came from"):
        load_with(tmp_path, escalation={"window_days": 14, "ticket_threshold": 3,
                                        "because_documents": documents})


@pytest.mark.parametrize("document", ["", "   ", 3, None])
def test_an_escalation_citation_that_is_not_a_document_id_is_refused(tmp_path, document):
    with pytest.raises(IntelligenceConfigError,
                       match=r"because_documents\[0\]: expected a document id"):
        load_with(tmp_path, escalation={"window_days": 14, "ticket_threshold": 3,
                                        "because_documents": [document]})


@pytest.mark.parametrize("field", ["window_days", "ticket_threshold"])
@pytest.mark.parametrize("value", [0, -1, True, "3", None])
def test_the_escalation_window_and_threshold_must_be_positive_integers(tmp_path, field, value):
    policy = {"window_days": 14, "ticket_threshold": 3, "because_documents": ["DOC-003"]}

    with pytest.raises(IntelligenceConfigError, match="integer of at least 1"):
        load_with(tmp_path, escalation={**policy, field: value})


def test_a_broken_band_table_is_refused_at_load_rather_than_at_evaluation(tmp_path):
    """Plan A23: refuse naming the broken rule; never a partial assessment."""
    with pytest.raises(IntelligenceConfigError, match=r"bands\[0\]"):
        load_with(tmp_path, bands=[{"id": "R-X", "band": "SEVERE", "when": {}}])
