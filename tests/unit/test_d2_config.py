"""D2 quality gate configuration tests."""

from __future__ import annotations

import copy
import dataclasses

import pytest
import yaml
from d1_support import ABSENT, INGESTED_AT, RUN_ID, full_case, with_value

from app.validation import (
    ValidationConfigError,
    default_validation_config,
    load_validation_config,
    validate_source_batch,
)
from app.validation.config import DEFAULT_CONFIG_PATH


def _data() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def _load(tmp_path, mutate=None):
    data = copy.deepcopy(_data())
    if mutate is not None:
        mutate(data)
    path = tmp_path / "quality_gate.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_validation_config(path)


def _set(*path, value):
    def mutate(data):
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return mutate


def test_default_config_is_loaded_once():
    assert default_validation_config() is default_validation_config()


def test_default_policy_values():
    config = default_validation_config()
    assert config.quarantine.redaction == "[REDACTED]"
    assert {"password", "token", "apikey", "authorization", "secret"} <= config.quarantine.sensitive_keys
    assert config.quarantine.max_string_length == 2000
    assert config.warnings.duplicate_source_identity is True
    assert dict(config.warnings.recommended_fields) == {"customers": ("email",),
                                                        "employees": ("email",)}


def test_configuration_is_immutable():
    config = default_validation_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.warnings = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.quarantine.redaction = "x"
    with pytest.raises(TypeError):
        config.warnings.recommended_fields["deals"] = ("stage",)


def test_unmodified_copy_loads(tmp_path):
    assert _load(tmp_path) == default_validation_config()


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ValidationConfigError, match="not found"):
        load_validation_config(tmp_path / "missing.yaml")


def test_invalid_yaml_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(ValidationConfigError, match="invalid YAML"):
        load_validation_config(path)


CONFIG_ERRORS = [
    ("top-level-list", lambda data: data.clear() or data.update({"x": 1}), "unknown keys"),
    ("unknown-key", _set("extra", value=True), "unknown keys"),
    ("version", _set("version", value=2), "unsupported version"),
    ("short-max-length", _set("quarantine", "max_string_length", value=5), "max_string_length"),
    ("zero-depth", _set("quarantine", "max_depth", value=0), "max_depth"),
    ("string-depth", _set("quarantine", "max_depth", value="8"), "max_depth"),
    ("bool-length", _set("quarantine", "max_string_length", value=True), "max_string_length"),
    ("empty-redaction", _set("quarantine", "redaction", value=" "), "redaction"),
    ("no-sensitive-keys", _set("quarantine", "sensitive_keys", value=[]), "sensitive_keys"),
    ("punctuation-key", _set("quarantine", "sensitive_keys", value=["--"]), "letters or digits"),
    ("bad-pattern", _set("quarantine", "sensitive_value_patterns", value=["("]), "invalid pattern"),
    ("duplicate-flag", _set("warnings", "duplicate_source_identity", value="yes"),
     "duplicate_source_identity"),
    ("unknown-entity", _set("warnings", "recommended_fields", value={"invoices": ["total"]}),
     "unknown entities"),
    ("unknown-field", _set("warnings", "recommended_fields", value={"customers": ["phone"]}),
     "not a business field"),
    ("required-field", _set("warnings", "recommended_fields", value={"customers": ["name"]}),
     "already required"),
    ("duplicate-fields", _set("warnings", "recommended_fields",
                              value={"customers": ["email", "email"]}), "unique strings"),
    ("fields-not-mapping", _set("warnings", "recommended_fields", value=["email"]), "mapping"),
]


@pytest.mark.parametrize(("mutate", "match"), [case[1:] for case in CONFIG_ERRORS],
                         ids=[case[0] for case in CONFIG_ERRORS])
def test_invalid_configuration_is_rejected(tmp_path, mutate, match):
    with pytest.raises(ValidationConfigError, match=match):
        _load(tmp_path, mutate)


def test_explicit_configuration_drives_the_gate(tmp_path):
    def mutate(data):
        data["warnings"]["duplicate_source_identity"] = False
        data["warnings"]["recommended_fields"] = {}
        data["quarantine"]["redaction"] = "***"

    config = _load(tmp_path, mutate)
    customer, _ = full_case("csv_demo", "customers")
    records = [with_value(customer, "email_address", ABSENT), customer,
               dict(with_value(customer, "status", "churned"), password="x")]
    result = validate_source_batch("csv_demo", "customers", records, RUN_ID, INGESTED_AT,
                                   validation_config=config)
    assert result.warnings == ()
    assert result.quarantined[0].raw_record["password"] == "***"
