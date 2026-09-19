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

VALID = {
    "version": 1,
    "rules_version": 1,
    "acceptance_as_of": date(2026, 9, 18),
    "layer1_fingerprints": {"csv_demo": CSV_DEMO_FINGERPRINT},
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


def test_an_unknown_key_is_refused_so_m3s_band_table_arrives_deliberately(tmp_path):
    with pytest.raises(IntelligenceConfigError, match=r"unknown keys \['bands'\]"):
        load_with(tmp_path, bands={})


@pytest.mark.parametrize("rules_version", [0, -1, True, "1", 1.0, None])
def test_the_rules_version_must_be_a_positive_integer(tmp_path, rules_version):
    with pytest.raises(IntelligenceConfigError, match="integer of at least 1"):
        load_with(tmp_path, rules_version=rules_version)


@pytest.mark.parametrize("as_of", ["2026-09-18", 20260918, None])
def test_the_acceptance_date_must_be_a_calendar_date(tmp_path, as_of):
    with pytest.raises(IntelligenceConfigError, match="expected a YYYY-MM-DD date"):
        load_with(tmp_path, acceptance_as_of=as_of)


def test_a_timestamp_is_not_an_acceptance_date(tmp_path):
    path = tmp_path / "risk_rules.yaml"
    path.write_text(
        "version: 1\nrules_version: 1\nacceptance_as_of: 2026-09-18 10:30:00\n"
        f"layer1_fingerprints:\n  csv_demo: \"{CSV_DEMO_FINGERPRINT}\"\n",
        encoding="utf-8",
    )

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
