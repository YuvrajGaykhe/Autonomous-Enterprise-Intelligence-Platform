"""
D1 normalization configuration tests.

Covers the repository configuration contents, immutability, the loader's
validation of every inconsistency class, and configuration-driven behaviour
(enum aliases, separators, naive-datetime policy, null-token overrides).
"""

from __future__ import annotations

import copy
import dataclasses
from datetime import UTC
from decimal import Decimal

import pytest
import yaml
from d1_support import ENTITIES, INGESTED_AT, RUN_ID, SOURCES, business, full_case, utc, with_value

from app.normalization import NormalizationConfigError, default_config, load_config, normalize
from app.normalization.config import DEFAULT_CONFIG_DIR
from app.normalization.contract import BUSINESS_FIELDS, CANONICAL_SCHEMAS

GLOBAL = "normalization.yaml"
CSV = "csv_demo.yaml"
ODOO = "odoo_mock.yaml"
REST = "rest_mock.yaml"


def _files() -> dict[str, dict]:
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted(DEFAULT_CONFIG_DIR.glob("*.yaml"))}


def _load(tmp_path, mutate=None):
    files = copy.deepcopy(_files())
    if mutate is not None:
        mutate(files)
    for name, data in files.items():
        (tmp_path / name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                                     encoding="utf-8")
    return load_config(tmp_path)


def _set(*path, value):
    def mutate(files):
        target = files
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return mutate


def _delete(*path):
    def mutate(files):
        target = files
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]
    return mutate


# ---------------------------------------------------------------------------
# Repository configuration
# ---------------------------------------------------------------------------


def test_default_config_is_loaded_once():
    assert default_config() is default_config()


def test_source_system_vocabulary():
    assert default_config().source_systems == ("csv_demo", "odoo_mock", "rest_mock")
    assert {path.stem for path in DEFAULT_CONFIG_DIR.glob("*.yaml")} == {"normalization", *SOURCES}


def test_all_21_mappings_cover_every_business_field():
    config = default_config()
    for source in SOURCES:
        profile = config.sources[source]
        assert tuple(profile.entities) == ENTITIES
        for entity, mapping in profile.entities.items():
            assert tuple(mapping.rules) == BUSINESS_FIELDS[entity]
            assert mapping.source_id_field


def test_source_profiles():
    sources = default_config().sources
    assert sources["csv_demo"].identifier_type == "string"
    assert sources["odoo_mock"].identifier_type == "integer"
    assert sources["rest_mock"].identifier_type == "string"
    assert sources["csv_demo"].naive_timezone is UTC
    assert sources["odoo_mock"].naive_timezone is UTC
    assert sources["rest_mock"].naive_timezone is None


def test_source_updated_at_mapped_only_for_documents():
    for source in SOURCES:
        for entity, mapping in default_config().sources[source].entities.items():
            assert (mapping.source_updated_at_field is not None) is (entity == "documents")


def test_spec_null_and_boolean_tokens():
    config = default_config()
    for source in SOURCES:
        assert config.sources[source].null_tokens == {"null", "n/a", "-"}
    assert config.true_tokens == {"true", "yes", "1"}
    assert config.false_tokens == {"false", "no", "0"}


def test_required_flags_follow_canonical_schema():
    for entity, specs in default_config().fields.items():
        schema = CANONICAL_SCHEMAS[entity]
        for name, spec in specs.items():
            assert spec.required is schema.model_fields[name].is_required()
        assert {n for n, s in specs.items() if s.required} <= {"name", "is_active"}


def test_decimal_specs_match_database_columns():
    from app.persistence.models import Deal, Project

    columns = {
        ("deals", "amount"): Deal.__table__.c.amount,
        ("deals", "probability"): Deal.__table__.c.probability,
        ("projects", "budget"): Project.__table__.c.budget,
    }
    fields = default_config().fields
    decimal_fields = {(e, n) for e, specs in fields.items() for n, s in specs.items()
                      if s.kind == "decimal"}
    assert decimal_fields == set(columns)
    for (entity, name), column in columns.items():
        spec = fields[entity][name]
        assert (spec.precision, spec.scale) == (column.type.precision, column.type.scale)
    assert fields["deals"]["probability"].minimum == Decimal(0)
    assert fields["deals"]["probability"].maximum == Decimal(100)


def test_enum_fields_and_vocabulary():
    enums = {(e, n): s.enum_values for e, specs in default_config().fields.items()
             for n, s in specs.items() if s.kind == "enum"}
    assert enums == {
        ("organizations", "status"): {"active", "inactive"},
        ("employees", "status"): {"active", "inactive"},
        ("customers", "status"): {"active", "inactive"},
        ("deals", "stage"): {"qualification", "negotiation", "won"},
        ("projects", "status"): {"planning", "in_progress"},
        ("support_tickets", "priority"): {"medium", "high"},
        ("support_tickets", "status"): {"open", "resolved"},
    }


def test_configuration_is_immutable():
    config = default_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.source_systems = ()
    with pytest.raises(TypeError):
        config.sources["sap_mock"] = None
    with pytest.raises(TypeError):
        config.fields["deals"]["amount"] = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.fields["deals"]["amount"].scale = 5
    with pytest.raises(TypeError):
        config.sources["csv_demo"].entities["customers"].rules["name"] = None
    with pytest.raises(TypeError):
        config.currency_aliases["$"] = "USD"


def test_loading_is_independent_of_working_directory_and_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CSV_DATA_DIR", "/nonexistent")
    config = load_config(DEFAULT_CONFIG_DIR)
    record, _ = full_case("odoo_mock", "deals")
    explicit = normalize("odoo_mock", "deals", record, RUN_ID, INGESTED_AT, config=config)
    assert explicit.model_dump() == normalize("odoo_mock", "deals", record, RUN_ID,
                                              INGESTED_AT).model_dump()


def test_unmodified_copy_loads(tmp_path):
    assert _load(tmp_path).source_systems == default_config().source_systems


# ---------------------------------------------------------------------------
# Loader validation
# ---------------------------------------------------------------------------


def test_missing_global_file_is_rejected(tmp_path):
    with pytest.raises(NormalizationConfigError, match="not found"):
        load_config(tmp_path)


def test_invalid_yaml_is_rejected(tmp_path):
    (tmp_path / GLOBAL).write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(NormalizationConfigError, match="invalid YAML"):
        load_config(tmp_path)


def test_non_mapping_top_level_is_rejected(tmp_path):
    (tmp_path / GLOBAL).write_text("- 1\n", encoding="utf-8")
    with pytest.raises(NormalizationConfigError, match="must be a mapping"):
        load_config(tmp_path)


CONFIG_ERRORS = [
    ("unknown-top-level-key", _set(GLOBAL, "colums", value={}), "unknown keys"),
    ("unsupported-version", _set(GLOBAL, "version", value=2), "unsupported version"),
    ("source-file-missing",
     _set(GLOBAL, "source_systems", value=["csv_demo", "odoo_mock", "rest_mock", "sap_mock"]),
     "not found"),
    ("invalid-source-name", _set(GLOBAL, "source_systems", value=["csv_demo", "Odoo-Mock"]),
     "invalid source system name"),
    ("source-name-mismatch", _set(REST, "source", value="rest_demo"), "'source' must be"),
    ("unknown-identifier-type", _set(ODOO, "identifier_type", value="uuid"), "identifier_type"),
    ("named-timezone", _set(CSV, "naive_datetime_timezone", value="Asia/Kolkata"),
     "naive_datetime_timezone"),
    ("unsupported-directive", _set(REST, "datetime_formats", value=["%Y-%m-%d %I:%M %p"]),
     "unsupported directives"),
    ("time-in-date-format", _set(CSV, "date_formats", value=["%Y-%m-%d %H"]),
     "unsupported directives"),
    ("unmapped-business-field", _delete(CSV, "entities", "customers", "columns", "created_date"),
     "not mapped"),
    ("duplicate-target",
     _set(CSV, "entities", "customers", "columns", "industry_name", value=["industry", "segment"]),
     "mapped twice"),
    ("unknown-target", _set(CSV, "entities", "customers", "columns", "tier", value="loyalty_tier"),
     "unknown canonical field"),
    ("e1-fk-mapped",
     _set(CSV, "entities", "deals", "columns", "customer_id",
          value=["customer_source_id", "customer_id"]),
     "resolved by E1"),
    ("provenance-mapped",
     _set(CSV, "entities", "customers", "columns", "created_date",
          value=["created_at", "ingested_at"]),
     "provenance field"),
    ("no-source-id", _delete(CSV, "entities", "customers", "columns", "customer_id"), "source_id"),
    ("derived-duplicate-of-column",
     _set(REST, "entities", "customers", "derived",
          value={"status": {"rule": "boolean_to_enum", "from": "isActive",
                            "true_value": "active", "false_value": "inactive"}}),
     "mapped twice"),
    ("non-canonical-enum-value",
     _set(GLOBAL, "canonical_fields", "projects", "status", "values",
          value=["planning", "In Progress"]),
     "canonical form"),
    ("kind-mismatch", _set(GLOBAL, "canonical_fields", "deals", "amount", value={"kind": "string"}),
     "does not match canonical annotation"),
    ("unknown-kind", _set(GLOBAL, "canonical_fields", "deals", "currency", value={"kind": "money"}),
     "unknown kind"),
    ("missing-canonical-field", _delete(GLOBAL, "canonical_fields", "deals", "currency"),
     "currency"),
    ("invalid-precision", _set(GLOBAL, "canonical_fields", "deals", "probability", "scale", value=5),
     "precision"),
    ("min-greater-than-max",
     _set(GLOBAL, "canonical_fields", "deals", "probability", "min", value=101), "min is greater"),
    ("membership-overlap",
     _set(CSV, "entities", "customers", "derived", "is_active", "false_values",
          value=["active", "inactive"]),
     "partition"),
    ("boolean-to-enum-unknown-value",
     _set(ODOO, "entities", "organizations", "derived", "status", "true_value", value="enabled"),
     "boolean_to_enum"),
    ("unknown-derivation",
     _set(ODOO, "entities", "customers", "derived", "status", "rule", value="lookup"),
     "unknown derivation rule"),
    ("null-token-overlaps-boolean", _set(GLOBAL, "null_tokens", value=["null", "no"]),
     "boolean tokens"),
    ("boolean-token-conflict", _set(GLOBAL, "boolean_tokens", "false_values", value=["false", "yes"]),
     "both true and false"),
    ("currency-alias-unknown-code", _set(GLOBAL, "currency", "aliases", value={"$": "USDX"}),
     "currency alias"),
    ("invalid-currency-code", _set(GLOBAL, "currency", "codes", value=["USD", "usd"]), "ISO 4217"),
    ("enum-alias-unknown-value",
     _set(CSV, "enum_aliases", value={"deals.stage": {"closed_won": "lost"}}), "alias"),
    ("enum-alias-shadows-canonical-value",
     _set(CSV, "enum_aliases", value={"deals.stage": {"won": "negotiation"}}), "alias"),
    ("enum-alias-on-non-enum-field",
     _set(CSV, "enum_aliases", value={"deals.currency": {"rs": "INR"}}),
     "not a canonical enum field"),
    ("same-separators", _set(CSV, "decimal", "thousands_separator", value="."), "separators"),
    ("unknown-entity",
     _set(REST, "entities", "invoices", value={"columns": {"id": "source_id"}}), "invoices"),
    ("source-null-token-overlaps-boolean", _set(REST, "null_tokens", value=["yes"]),
     "boolean tokens"),
]


@pytest.mark.parametrize(("mutate", "match"), [case[1:] for case in CONFIG_ERRORS],
                         ids=[case[0] for case in CONFIG_ERRORS])
def test_invalid_configuration_is_rejected(tmp_path, mutate, match):
    with pytest.raises(NormalizationConfigError, match=match):
        _load(tmp_path, mutate)


def test_config_error_is_not_a_record_error():
    from app.normalization import NormalizationError

    assert not issubclass(NormalizationConfigError, NormalizationError)


# ---------------------------------------------------------------------------
# Configuration-driven behaviour
# ---------------------------------------------------------------------------


def test_enum_aliases_are_applied(tmp_path):
    config = _load(tmp_path, _set(REST, "enum_aliases", value={"deals.stage": {"Closed Won": "won"}}))
    record, _ = full_case("rest_mock", "deals")
    obj = normalize("rest_mock", "deals", with_value(record, "stage", "closed-won"), RUN_ID,
                    INGESTED_AT, config=config)
    assert obj.stage == "won"


def test_configured_thousands_separator(tmp_path):
    config = _load(tmp_path, _set(CSV, "decimal", "thousands_separator", value=","))
    record, _ = full_case("csv_demo", "deals")
    obj = normalize("csv_demo", "deals", with_value(record, "amount", "1,500.25"), RUN_ID,
                    INGESTED_AT, config=config)
    assert str(obj.amount) == "1500.25"


def test_configured_naive_timezone_offset(tmp_path):
    config = _load(tmp_path, _set(CSV, "naive_datetime_timezone", value="+05:30"))
    record, _ = full_case("csv_demo", "customers")
    obj = normalize("csv_demo", "customers", with_value(record, "created_date", "2026-01-01 17:30:00"),
                    RUN_ID, INGESTED_AT, config=config)
    assert obj.created_at == utc(2026, 1, 1, 12)


def test_source_null_token_override(tmp_path):
    config = _load(tmp_path, _set(REST, "null_tokens", value=["unknown"]))
    record, _ = full_case("rest_mock", "organizations")
    unknown = normalize("rest_mock", "organizations", with_value(record, "country", "Unknown"),
                        RUN_ID, INGESTED_AT, config=config)
    not_applicable = normalize("rest_mock", "organizations", with_value(record, "country", "N/A"),
                               RUN_ID, INGESTED_AT, config=config)
    assert unknown.country is None
    assert not_applicable.country == "N/A"


def test_configured_mapping_rewiring_changes_output(tmp_path):
    """Mapping lives in configuration: rewiring YAML (not code) changes canonical output."""
    config = _load(tmp_path, _set(REST, "entities", "organizations", "columns",
                                  value={"id": "source_id", "name": "name", "industry": "country",
                                         "country": "industry", "status": "status"}))
    record, expected = full_case("rest_mock", "organizations")
    obj = normalize("rest_mock", "organizations", record, RUN_ID, INGESTED_AT, config=config)
    assert business(obj) == {**expected["fields"], "industry": "Germany", "country": "Manufacturing"}
