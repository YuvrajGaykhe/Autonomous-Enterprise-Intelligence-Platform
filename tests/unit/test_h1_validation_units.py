"""
H1 unit tests — validation rule surfaces the D2 suites leave unexercised.

Spec Section 15 requires unit coverage of the validation rules. The D2
suites drive the gate through its public entry point, which reaches every
path the committed configuration and schemas can produce. This module covers
the remainder:

1. The provenance escape hatch in check_canonical_record: a pipeline-generated
   field that strict schema validation rejects is a SYSTEM failure, never a
   quarantined data violation.
2. The source_updated_at contract check, which the D2 fixtures never reach
   with a schema-valid but non-canonical value.
3. The fail-loud guards behind the data-contract classifier, which exist
   because the classifier may only see values strict validation accepted.
4. The quality-gate partition invariant and the configuration section guard.

These guards protect invariants the rest of the pipeline relies on, so each
one is asserted on the exact exception type and message.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import yaml
from d1_support import INGESTED_AT, RUN_ID
from d2_support import canonical, tamper

from app.normalization import default_config
from app.normalization.config import FieldSpec
from app.validation import (
    QualityGateResult,
    ValidationConfigError,
    load_validation_config,
)
from app.validation.errors import (
    CanonicalInvariantError,
    QualityCode,
    Severity,
    Stage,
    SystemFailureCode,
)
from app.validation.quarantine import QualityFinding, QuarantineRecord
from app.validation.rules import (
    ErrorCode,
    _decimal_violation,
    _schema_violation,
    _significant_fractional_digits,
    _validated,
    check_canonical_record,
)

CONFIG = default_config()


def _violations(record, entity_type="customers", source="csv_demo"):
    return check_canonical_record(record, entity_type=entity_type,
                                  profile=CONFIG.sources[source], config=CONFIG,
                                  record_index=0)


# ---------------------------------------------------------------------------
# Provenance fields are never quarantined as data
# ---------------------------------------------------------------------------


def test_a_schema_invalid_provenance_field_is_a_system_failure():
    """check_invariants runs first; if it ever misses one, this fails loudly."""
    record = tamper(canonical("csv_demo", "customers"), source_entity=17)
    with pytest.raises(CanonicalInvariantError) as exc:
        _violations(record)
    assert exc.value.code == SystemFailureCode.INVALID_PROVENANCE
    assert "source_entity" in str(exc.value)


def test_the_system_failure_names_every_offending_field():
    """More than one broken provenance field is reported together, sorted."""
    record = tamper(canonical("csv_demo", "customers"), source_entity=17, ingested_at="today")
    with pytest.raises(CanonicalInvariantError) as exc:
        _violations(record)
    assert "['ingested_at', 'source_entity']" in str(exc.value)


def test_a_valid_record_has_no_violations():
    """The baseline the tamper cases are measured against."""
    assert _violations(canonical("csv_demo", "customers")) == []


# ---------------------------------------------------------------------------
# source_updated_at is checked against the canonical datetime contract
# ---------------------------------------------------------------------------


def test_a_utc_source_updated_at_is_canonical():
    record = tamper(canonical("csv_demo", "customers"),
                    source_updated_at=datetime(2026, 6, 1, tzinfo=UTC))
    assert _violations(record) == []


def test_a_non_utc_source_updated_at_is_a_violation():
    """The provenance timestamp obeys the same UTC rule as business datetimes."""
    record = tamper(canonical("csv_demo", "customers"),
                    source_updated_at=datetime(2026, 6, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))))
    violations = _violations(record)
    assert [v.field_name for v in violations] == ["source_updated_at"]
    assert violations[0].code == str(QualityCode.NON_CANONICAL_VALUE)


def test_a_naive_source_updated_at_is_rejected_by_the_strict_schema():
    """A naive datetime fails the schema before the contract check sees it."""
    record = tamper(canonical("csv_demo", "customers"),
                    source_updated_at=datetime(2026, 6, 1))
    violations = _violations(record)
    assert [v.field_name for v in violations] == ["source_updated_at"]


def test_a_source_updated_at_of_the_wrong_type_is_classified_as_a_type_error():
    """A schema error on the provenance timestamp still resolves its kind."""
    record = tamper(canonical("csv_demo", "customers"), source_updated_at="2026-06-01")
    violations = _violations(record)
    assert [(v.field_name, v.code) for v in violations] == [
        ("source_updated_at", str(ErrorCode.INVALID_TYPE))
    ]
    assert "2026-06-01" not in violations[0].reason


def test_a_null_source_updated_at_is_not_a_violation():
    record = tamper(canonical("csv_demo", "customers"), source_updated_at=None)
    assert _violations(record) == []


# ---------------------------------------------------------------------------
# Fail-loud guards behind the classifier
# ---------------------------------------------------------------------------


def test_an_unclassified_schema_error_keeps_a_stable_code_and_hides_the_value():
    """Any future pydantic error type still yields a safe, stable finding."""
    code, reason = _schema_violation("customers", "name", "s3cr3t-value",
                                     "string_too_long", CONFIG)
    assert code == ErrorCode.SCHEMA_VALIDATION_FAILED
    assert "string_too_long" in reason
    assert "s3cr3t-value" not in reason


@pytest.mark.parametrize(
    ("field", "value", "error_type", "expected"),
    [
        ("name", None, "missing", ErrorCode.REQUIRED_FIELD_MISSING),
        ("source_id", None, "missing", ErrorCode.SOURCE_ID_MISSING),
        ("name", "v", "string_type", ErrorCode.INVALID_TYPE),
        ("name", "v", "is_instance_of", ErrorCode.INVALID_TYPE),
        ("source_id", 1, "string_type", ErrorCode.SOURCE_ID_INVALID),
        ("owner_source_id", 1, "string_type", ErrorCode.RELATIONSHIP_KEY_INVALID),
        ("created_at", Decimal("nan"), "finite_number", ErrorCode.INVALID_DECIMAL),
        ("name", "v", "string_too_long", ErrorCode.SCHEMA_VALIDATION_FAILED),
    ],
)
def test_schema_error_types_map_to_stable_codes(field, value, error_type, expected):
    """Each classifier branch keeps its published code."""
    code, reason = _schema_violation("customers", field, value, error_type, CONFIG)
    assert code == expected
    assert reason


def test_the_classifier_refuses_a_value_strict_validation_could_not_have_accepted():
    """_validated is a programming-fault guard, not a data check."""
    with pytest.raises(TypeError, match="strict schema accepted str; expected int"):
        _validated("12", int)


def test_the_classifier_accepts_the_declared_type_unchanged():
    value = Decimal("1.00")
    assert _validated(value, Decimal) is value


def test_a_decimal_field_without_limits_fails_loudly():
    """D1 configuration guarantees precision and scale; a gap is a fault."""
    spec = FieldSpec(name="amount", kind="decimal", required=False)
    with pytest.raises(TypeError, match="decimal field 'amount' has no configured"):
        _decimal_violation(Decimal("1.00"), spec)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_fractional_digits_of_a_non_finite_decimal_fail_loudly(value):
    """Non-finite decimals are rejected earlier; reaching here is a fault."""
    with pytest.raises(TypeError, match="non-finite decimal has no fractional digits"):
        _significant_fractional_digits(Decimal(value))


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", 0), ("0.00", 0), ("1.00", 0), ("1.5", 1), ("1.050", 2), ("-2.125", 3), ("1E+2", 0)],
)
def test_significant_fractional_digits_ignores_trailing_zeros(value, expected):
    """The scale check counts significant digits, not stored exponent."""
    assert _significant_fractional_digits(Decimal(value)) == expected


# ---------------------------------------------------------------------------
# Quality gate partition invariant
# ---------------------------------------------------------------------------


def _finding(index: int) -> QualityFinding:
    return QualityFinding(severity=Severity.ERROR, code="X", message="m", record_index=index)


def _quarantined(index: int) -> QuarantineRecord:
    return QuarantineRecord(
        ingestion_run_id=RUN_ID, source_system="csv_demo", entity_type="customers",
        record_index=index, stage=Stage.VALIDATION, source_id=None, canonical_id=None,
        findings=(_finding(index),), raw_record={},
    )


def test_a_result_must_account_for_every_input_record():
    """Valid plus quarantined must equal the batch size."""
    with pytest.raises(ValueError, match="account for every input record"):
        QualityGateResult(source_system="csv_demo", entity_type="customers",
                          ingestion_run_id=RUN_ID, total_records=3,
                          valid=(canonical(),), quarantined=(), warnings=())


def test_downstream_index_recovery_rejects_a_result_that_does_not_partition():
    """Two quarantine rows for one index would silently mis-align raw payloads."""
    from app.ingestion.batch import valid_record_indices

    result = QualityGateResult(
        source_system="csv_demo", entity_type="customers", ingestion_run_id=RUN_ID,
        total_records=3, valid=(canonical(),),
        quarantined=(_quarantined(0), _quarantined(0)), warnings=(),
    )
    with pytest.raises(ValueError, match="does not partition its input records"):
        valid_record_indices(result)


def test_index_recovery_returns_the_surviving_input_positions():
    """The happy path the guard protects: indices line up with raw records."""
    from app.ingestion.batch import valid_record_indices

    result = QualityGateResult(
        source_system="csv_demo", entity_type="customers", ingestion_run_id=RUN_ID,
        total_records=3, valid=(canonical(), canonical()),
        quarantined=(_quarantined(1),), warnings=(),
    )
    assert valid_record_indices(result) == (0, 2)


# ---------------------------------------------------------------------------
# Validation configuration sections
# ---------------------------------------------------------------------------


def _write(tmp_path, data) -> object:
    path = tmp_path / "quality_gate.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_a_configuration_file_must_hold_a_mapping(tmp_path):
    with pytest.raises(ValidationConfigError, match="expected a mapping"):
        load_validation_config(_write(tmp_path, ["version", 1]))


def test_a_configuration_section_must_hold_a_mapping(tmp_path):
    data = {"version": 1, "quarantine": "not a mapping", "warnings": {}}
    with pytest.raises(ValidationConfigError, match="quarantine: expected a mapping"):
        load_validation_config(_write(tmp_path, data))


def test_a_missing_configuration_file_is_reported(tmp_path):
    with pytest.raises(ValidationConfigError, match="not found"):
        load_validation_config(tmp_path / "absent.yaml")


def test_the_gate_result_summary_counts_match_its_contents():
    """summary() is what E1 and the API report; it must not drift."""
    result = QualityGateResult(
        source_system="csv_demo", entity_type="customers", ingestion_run_id=RUN_ID,
        total_records=2, valid=(canonical(),), quarantined=(_quarantined(1),),
        warnings=(QualityFinding(severity=Severity.WARNING, code="W", message="m",
                                 record_index=0),),
    )
    assert result.summary() == {
        "source_system": "csv_demo", "entity_type": "customers",
        "ingestion_run_id": str(RUN_ID), "total_records": 2,
        "valid": 1, "quarantined": 1, "warnings": 1,
    }
    assert (result.valid_count, result.quarantined_count, result.warning_count) == (1, 1, 1)


def test_ingested_at_is_unchanged_by_these_helpers():
    """Guard against a fixture drift that would weaken the tamper cases."""
    assert canonical().ingested_at == INGESTED_AT
    assert canonical().ingestion_run_id == RUN_ID
    assert isinstance(canonical().id, uuid.UUID)
