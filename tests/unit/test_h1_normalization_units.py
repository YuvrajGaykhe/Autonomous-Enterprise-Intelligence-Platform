"""
H1 unit tests — normalization surfaces the D1 suites leave unexercised.

Spec Section 15 requires unit coverage of mapping, type coercion, identifier
generation and hashing. The D1 modules cover the paths the committed
configuration can reach; this module covers the rest:

1. Loader rejections that the committed YAML shape never triggers
   (malformed column keys, underivable targets, malformed derivations, and
   the scalar/list/mapping helpers used throughout the parser).
2. The source_updated_at mapping error path, which the committed mappings
   cannot reach because every source maps that field from a column that also
   feeds a canonical datetime business field.
3. The fail-loud guards in the coercion dispatcher and the hash serializer.

Every rejection is asserted on its message, so a guard that stops firing or
starts reporting a different rule fails here.
"""

from __future__ import annotations

import copy
import dataclasses
import uuid
from datetime import UTC, datetime

import pytest
import yaml
from d1_support import INGESTED_AT, RUN_ID, full_case, with_value

from app.normalization import NormalizationConfigError, default_config, load_config, normalize
from app.normalization.config import DEFAULT_CONFIG_DIR, FieldSpec
from app.normalization.errors import CoercionError, ErrorCode, NormalizationError
from app.normalization.identifiers import _canonical_value
from app.normalization.mappings import _coerce

CSV = "csv_demo.yaml"
GLOBAL = "normalization.yaml"


def _files() -> dict[str, dict]:
    return {path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in sorted(DEFAULT_CONFIG_DIR.glob("*.yaml"))}


def _load(tmp_path, mutate):
    """Load a copy of the committed configuration after applying one mutation."""
    files = copy.deepcopy(_files())
    mutate(files)
    for name, data in files.items():
        (tmp_path / name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                                     encoding="utf-8")
    return load_config(tmp_path)


def _rejects(tmp_path, mutate, message: str) -> None:
    with pytest.raises(NormalizationConfigError) as exc:
        _load(tmp_path, mutate)
    assert message in str(exc.value)


def _set(*path, value):
    def mutate(files):
        target = files
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return mutate


# ---------------------------------------------------------------------------
# Column and derivation rejections
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source_field", ["", 17, None])
def test_column_keys_must_be_non_empty_strings(tmp_path, source_field):
    """A column key that is not a usable source field name is rejected by name."""
    def mutate(files):
        columns = files[CSV]["entities"]["customers"]["columns"]
        target = columns.pop("customer_name")
        columns[source_field] = target

    _rejects(tmp_path, mutate,
             f"entities.customers.columns: invalid source field {source_field!r}")


def test_only_business_fields_can_be_derived(tmp_path):
    """source_updated_at passes the target checks but has no derivation rule."""
    def mutate(files):
        files[CSV]["entities"]["customers"]["derived"]["source_updated_at"] = {
            "rule": "enum_membership", "from": "status", "enum_of": "status",
            "true_values": ["active"], "false_values": ["inactive"],
        }

    _rejects(tmp_path, mutate,
             "entities.customers.derived.source_updated_at: only business fields can be derived")


def test_a_derivation_must_name_its_source_field(tmp_path):
    """'from' is required and must be a non-empty string."""
    def mutate(files):
        del files[CSV]["entities"]["customers"]["derived"]["is_active"]["from"]

    _rejects(tmp_path, mutate,
             "entities.customers.derived.is_active: 'from' must name a source field")


def test_enum_membership_must_read_a_canonical_enum_field(tmp_path):
    """enum_of naming a non-enum field cannot derive a boolean."""
    _rejects(
        tmp_path,
        _set(CSV, "entities", "customers", "derived", "is_active", "enum_of", value="name"),
        "enum_membership derives a boolean from a canonical enum field",
    )


def test_an_entity_mapping_must_be_a_mapping(tmp_path):
    """The parser refuses a scalar where a mapping is required."""
    _rejects(tmp_path, _set(CSV, "entities", "customers", value="not a mapping"),
             "entities.customers: expected a mapping")


def test_a_canonical_field_group_must_be_a_mapping(tmp_path):
    """The same guard protects the global canonical_fields sections."""
    _rejects(tmp_path, _set(GLOBAL, "canonical_fields", "customers", value=["name"]),
             "canonical_fields.customers: expected a mapping")


# ---------------------------------------------------------------------------
# Scalar, list and token helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["csv_demo", [], ["csv_demo", "csv_demo"], ["csv_demo", ""]])
def test_string_lists_must_be_non_empty_and_unique(tmp_path, value):
    """source_systems must be a non-empty list of unique, non-empty strings."""
    _rejects(tmp_path, _set(GLOBAL, "source_systems", value=value),
             "source_systems: expected a non-empty list of unique strings")


def test_token_lists_must_be_lists(tmp_path):
    _rejects(tmp_path, _set(GLOBAL, "null_tokens", value="null"),
             "null_tokens: expected a list of tokens")


def test_token_list_entries_must_be_strings(tmp_path):
    _rejects(tmp_path, _set(GLOBAL, "null_tokens", value=["null", 7]),
             "null_tokens: tokens must be strings")


@pytest.mark.parametrize("value", [[0], {"min": 0}, True])
def test_decimal_bounds_must_be_numbers(tmp_path, value):
    """A bound that is not a number-like scalar is rejected (booleans included)."""
    _rejects(tmp_path,
             _set(GLOBAL, "canonical_fields", "deals", "probability", "min", value=value),
             "probability.min: expected a number")


def test_decimal_bounds_must_be_parseable(tmp_path):
    """A string that Decimal cannot parse is reported as the same rule."""
    _rejects(tmp_path,
             _set(GLOBAL, "canonical_fields", "deals", "probability", "min", value="abc"),
             "probability.min: expected a number")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_decimal_bounds_must_be_finite(tmp_path, value):
    """NaN and the infinities parse as Decimal but cannot bound a range."""
    _rejects(tmp_path,
             _set(GLOBAL, "canonical_fields", "deals", "probability", "max", value=value),
             "probability.max: expected a finite number")


# ---------------------------------------------------------------------------
# source_updated_at mapping errors
# ---------------------------------------------------------------------------


def _independent_source_updated_at(files: dict) -> None:
    """Map documents.source_updated_at from a column no business field uses."""
    columns = files[CSV]["entities"]["documents"]["columns"]
    columns["updated_date"] = "updated_at"
    columns["audit_stamp"] = "source_updated_at"


def test_source_updated_at_can_be_mapped_from_its_own_column(tmp_path):
    """The independent mapping is valid and is what the failure test exercises."""
    config = _load(tmp_path, _independent_source_updated_at)
    record, _ = full_case("csv_demo", "documents")
    canonical = normalize("csv_demo", "documents",
                          {**record, "audit_stamp": "2026-06-15 10:30:00"},
                          RUN_ID, INGESTED_AT, config=config)
    assert canonical.source_updated_at == datetime(2026, 6, 15, 10, 30, tzinfo=UTC)


def test_an_unparseable_source_updated_at_is_reported_against_that_field(tmp_path):
    """The error names source_updated_at, not the business field beside it."""
    config = _load(tmp_path, _independent_source_updated_at)
    record, _ = full_case("csv_demo", "documents")
    with pytest.raises(CoercionError) as exc:
        normalize("csv_demo", "documents", {**record, "audit_stamp": "not-a-timestamp"},
                  RUN_ID, INGESTED_AT, config=config)
    assert exc.value.field_name == "source_updated_at"
    assert exc.value.code == ErrorCode.INVALID_DATETIME
    assert exc.value.entity_type == "documents"


def test_a_null_token_source_updated_at_normalizes_to_none(tmp_path):
    """Null tokens clear the provenance timestamp instead of failing."""
    config = _load(tmp_path, _independent_source_updated_at)
    record, _ = full_case("csv_demo", "documents")
    canonical = normalize("csv_demo", "documents", {**record, "audit_stamp": "N/A"},
                          RUN_ID, INGESTED_AT, config=config)
    assert canonical.source_updated_at is None


# ---------------------------------------------------------------------------
# Fail-loud guards
# ---------------------------------------------------------------------------


def test_an_unknown_field_kind_fails_loudly():
    """A FieldSpec kind the dispatcher does not handle is a programming fault."""
    config = default_config()
    spec = dataclasses.replace(config.fields["customers"]["name"], kind="telepathy")
    with pytest.raises(AssertionError, match="unhandled field kind 'telepathy'"):
        _coerce(config, config.sources["csv_demo"], "customers", spec, "Acme")


def test_every_configured_field_kind_is_handled():
    """The dispatcher has a branch for every kind the loader can produce."""
    config = default_config()
    kinds = {spec.kind for fields in config.fields.values() for spec in fields.values()}
    profile = config.sources["csv_demo"]
    for kind in sorted(kinds):
        spec = FieldSpec(name="probe", kind=kind, required=False,
                         enum_values=frozenset({"active"}), precision=15, scale=2)
        assert _coerce(config, profile, "customers", spec, None) is None


def test_uuid_values_hash_as_their_canonical_string():
    """The hash serializer renders UUIDs as strings, never as objects."""
    value = uuid.UUID("11111111-2222-3333-4444-555555555555")
    assert _canonical_value("probe", value) == str(value)


def test_the_hash_serializer_rejects_values_it_cannot_render():
    """An unsupported type fails loudly rather than hashing its repr."""
    with pytest.raises(TypeError, match="Unsupported value type set in field 'probe'"):
        _canonical_value("probe", {"a", "b"})


def test_mapping_errors_keep_the_business_field_name(tmp_path):
    """The business-field context path stays distinct from the provenance one."""
    record, _ = full_case("csv_demo", "documents")
    with pytest.raises(NormalizationError) as exc:
        normalize("csv_demo", "documents", with_value(record, "created_date", "not-a-timestamp"),
                  RUN_ID, INGESTED_AT)
    assert exc.value.field_name == "created_at"
