"""
D2 quality gate tests: validate_source_batch (D1 normalization -> D2 validation).

Covers:
A. Valid records pass unchanged
B. Valid/invalid partitioning and ordering
C. Data failures quarantine with full context
D. System failures fail loudly
E. Warnings: duplicates and recommended fields
F. Empty batches, immutability, determinism
G. Cross-source classification on real C2/C3 representations
"""

from __future__ import annotations

import copy
import dataclasses
import json
import sys
from pathlib import Path

import pytest
from d1_support import (
    ABSENT,
    CASE_KEYS,
    ENTITIES,
    INGESTED_AT,
    RUN_ID,
    SOURCES,
    case_id,
    full_case,
    with_value,
)
from d2_support import fingerprint, mixed_customer_batch

import app.normalization.pipeline as d1_pipeline
import app.validation.gate as gate
from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.normalization import (
    ErrorCode,
    NormalizationConfigError,
    NormalizationError,
    UnsupportedEntityError,
    UnsupportedSourceError,
    canonical_id,
    load_config,
    normalize,
)
from app.validation import (
    QualityCode,
    QualityGateSystemError,
    Severity,
    Stage,
    SystemFailureCode,
    ValidationConfigError,
    load_validation_config,
    validate_source_batch,
)

REPO = Path(__file__).resolve().parents[2]


def _gate(source, entity, records, **kwargs):
    return validate_source_batch(source, entity, records, RUN_ID, INGESTED_AT, **kwargs)


def _raising(error):
    def raise_error(*args, **kwargs):
        raise error
    return raise_error


# ---------------------------------------------------------------------------
# A. Valid records
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_valid_record_passes_with_d1_output_unchanged(source, entity):
    record, _ = full_case(source, entity)
    result = _gate(source, entity, [record])
    expected = normalize(source, entity, record, RUN_ID, INGESTED_AT)
    assert result.quarantined == ()
    assert result.warnings == ()
    assert len(result.valid) == 1
    assert result.valid[0].model_dump() == expected.model_dump()
    assert result.valid[0].record_hash == expected.record_hash
    assert result.summary() == {
        "source_system": source, "entity_type": entity, "ingestion_run_id": str(RUN_ID),
        "total_records": 1, "valid": 1, "quarantined": 0, "warnings": 0,
    }


def test_unknown_customer_reference_is_not_quarantined():
    """FK resolution is E1: the source key is preserved and the record stays valid."""
    record, _ = full_case("csv_demo", "deals")
    result = _gate("csv_demo", "deals", [with_value(record, "customer_id", "CUST-999")])
    assert result.quarantined == ()
    assert result.valid[0].customer_source_id == "CUST-999"
    assert result.valid[0].customer_id is None


# ---------------------------------------------------------------------------
# B. Partitioning
# ---------------------------------------------------------------------------


def test_valid_invalid_interleaving_is_partitioned_in_input_order():
    good, _ = full_case("csv_demo", "deals")
    records = [
        good,
        with_value(good, "amount", "abc"),
        with_value(good, "deal_id", "DEAL-002"),
        with_value(good, "stage", "lost"),
        with_value(good, "deal_id", "DEAL-003"),
    ]
    result = _gate("csv_demo", "deals", records)
    assert [record.source_id for record in result.valid] == ["DEAL-001", "DEAL-002", "DEAL-003"]
    assert [record.record_index for record in result.quarantined] == [1, 3]
    assert [record.code for record in result.quarantined] == ["INVALID_DECIMAL", "UNKNOWN_ENUM_VALUE"]
    assert (result.total_records, result.valid_count, result.quarantined_count) == (5, 3, 2)
    assert result.warnings == ()


def test_canonical_interleaving_is_partitioned_in_input_order():
    from d2_support import canonical, tamper

    from app.validation import validate_canonical_batch

    first = canonical("csv_demo", "deals")
    second = normalize("csv_demo", "deals",
                       with_value(full_case("csv_demo", "deals")[0], "deal_id", "DEAL-002"),
                       RUN_ID, INGESTED_AT)
    third = normalize("csv_demo", "deals",
                      with_value(full_case("csv_demo", "deals")[0], "deal_id", "DEAL-003"),
                      RUN_ID, INGESTED_AT)
    records = [first, tamper(first, stage="lost"), second, tamper(second, currency="usd"), third]
    result = validate_canonical_batch("csv_demo", "deals", records, RUN_ID)
    assert [record.source_id for record in result.valid] == ["DEAL-001", "DEAL-002", "DEAL-003"]
    assert all(a is b for a, b in zip(result.valid, (first, second, third), strict=True))
    assert [(q.record_index, q.stage, q.code) for q in result.quarantined] == [
        (1, Stage.VALIDATION, "UNKNOWN_ENUM_VALUE"), (3, Stage.VALIDATION, "INVALID_CURRENCY")]
    assert (result.total_records, result.valid_count, result.quarantined_count) == (5, 3, 2)


def test_multiple_invalid_records_are_quarantined_independently():
    good, _ = full_case("rest_mock", "projects")
    records = [
        with_value(good, "status", "stalled"),
        with_value(with_value(good, "id", "PROJ-7"), "budget", "lots"),
        with_value(with_value(good, "id", "PROJ-8"), "startDate", "01/04/2026"),
        with_value(good, "id", ""),
        with_value(with_value(good, "id", "PROJ-9"), "customerId", 42),
    ]
    result = _gate("rest_mock", "projects", records)
    assert result.valid == ()
    assert [(q.record_index, q.source_id, q.code, q.field_name, len(q.findings))
            for q in result.quarantined] == [
        (0, "PROJ-002", "UNKNOWN_ENUM_VALUE", "status", 1),
        (1, "PROJ-7", "INVALID_DECIMAL", "budget", 1),
        (2, "PROJ-8", "INVALID_DATE", "start_date", 1),
        (3, None, "SOURCE_ID_MISSING", "source_id", 1),
        (4, "PROJ-9", "RELATIONSHIP_KEY_INVALID", "customer_source_id", 1),
    ]


def test_spec_bad_fixture_issues_are_classified():
    """Spec Section 12 deliberate quality issues map to ERROR or WARNING."""
    customer, _ = full_case("csv_demo", "customers")
    customers = [
        customer,
        with_value(with_value(customer, "customer_id", "CUST-002"), "email_address", ""),
        with_value(with_value(customer, "customer_id", "CUST-003"), "created_date", "31/12/2025"),
        copy.deepcopy(customer),
        with_value(with_value(customer, "customer_id", "CUST-004"), "status", "prospect"),
    ]
    result = _gate("csv_demo", "customers", customers)
    assert [r.source_id for r in result.valid] == ["CUST-001", "CUST-002", "CUST-001"]
    assert [(q.record_index, q.code) for q in result.quarantined] == [
        (2, "INVALID_DATETIME"), (4, "UNKNOWN_ENUM_VALUE")]
    assert [(w.record_index, w.code, w.field_name) for w in result.warnings] == [
        (1, "MISSING_RECOMMENDED_FIELD", "email"), (3, "DUPLICATE_SOURCE_RECORD", "source_id")]

    deal, _ = full_case("csv_demo", "deals")
    deals = _gate("csv_demo", "deals", [with_value(deal, "amount", "12,50"),
                                        with_value(deal, "customer_id", "CUST-999")])
    assert [q.code for q in deals.quarantined] == ["INVALID_DECIMAL"]
    assert deals.valid[0].customer_source_id == "CUST-999"


# ---------------------------------------------------------------------------
# C. Data failures quarantine
# ---------------------------------------------------------------------------

DATA_FAILURES = [
    ("missing-required-field", "csv_demo", "customers", "customer_name", ABSENT,
     "REQUIRED_FIELD_MISSING", "name", "CUST-001"),
    ("invalid-enum", "rest_mock", "projects", "status", "stalled",
     "UNKNOWN_ENUM_VALUE", "status", "PROJ-002"),
    ("invalid-identifier", "odoo_mock", "customers", "id", "abc",
     "SOURCE_ID_INVALID", "source_id", None),
    ("missing-identifier", "csv_demo", "deals", "deal_id", "",
     "SOURCE_ID_MISSING", "source_id", None),
    ("invalid-datetime", "odoo_mock", "support_tickets", "create_date", "2026-09-01T08:00:00Z",
     "INVALID_DATETIME", "created_at", "1"),
    ("naive-datetime", "rest_mock", "customers", "createdAt", "2025-06-10T18:30:00",
     "NAIVE_DATETIME_REJECTED", "created_at", "CUST-003"),
    ("invalid-decimal", "csv_demo", "deals", "amount", "12,50",
     "INVALID_DECIMAL", "amount", "DEAL-001"),
    ("decimal-scale", "rest_mock", "projects", "budget", 120000.001,
     "DECIMAL_SCALE_EXCEEDED", "budget", "PROJ-002"),
    ("invalid-relationship-key", "odoo_mock", "deals", "partner_id", "1",
     "RELATIONSHIP_KEY_INVALID", "customer_source_id", "1"),
    ("wrong-canonical-type", "rest_mock", "customers", "name", 123,
     "INVALID_TYPE", "name", "CUST-003"),
    ("invalid-boolean", "csv_demo", "employees", "is_active", "maybe",
     "INVALID_BOOLEAN", "is_active", "EMP-003"),
    ("invalid-currency", "odoo_mock", "deals", "company_currency", "US$",
     "INVALID_CURRENCY", "currency", "1"),
    ("invalid-date", "odoo_mock", "projects", "date", "31/10/2026",
     "INVALID_DATE", "end_date", "2"),
]


@pytest.mark.parametrize(
    ("source", "entity", "field", "value", "code", "canonical_field", "source_id"),
    [case[1:] for case in DATA_FAILURES], ids=[case[0] for case in DATA_FAILURES],
)
def test_data_failures_are_quarantined_with_full_context(source, entity, field, value, code,
                                                         canonical_field, source_id):
    record, _ = full_case(source, entity)
    bad = with_value(record, field, value)
    result = _gate(source, entity, [bad])
    assert result.valid == ()
    assert len(result.quarantined) == 1
    quarantined = result.quarantined[0]
    assert quarantined.ingestion_run_id == RUN_ID
    assert (quarantined.source_system, quarantined.entity_type) == (source, entity)
    assert quarantined.record_index == 0
    assert quarantined.stage is Stage.NORMALIZATION
    assert quarantined.source_id == source_id
    assert quarantined.canonical_id == (None if source_id is None
                                        else canonical_id(source, entity, source_id))
    assert (quarantined.code, quarantined.field_name) == (code, canonical_field)
    assert len(quarantined.findings) == 1
    finding = quarantined.findings[0]
    assert finding.severity is Severity.ERROR
    assert (finding.record_index, finding.source_id) == (0, source_id)
    assert finding.message and not finding.message.startswith("[")
    assert quarantined.raw_record == bad
    json.dumps(quarantined.to_dict())


@pytest.mark.parametrize("record", [None, ["DEAL-1"], "DEAL-1", 42])
def test_non_mapping_records_are_quarantined(record):
    result = _gate("csv_demo", "deals", [record])
    quarantined = result.quarantined[0]
    assert (quarantined.code, quarantined.source_id, quarantined.canonical_id) == (
        "INVALID_RECORD", None, None)
    assert quarantined.raw_record == (list(record) if isinstance(record, list) else record)


def test_quarantine_codes_are_stable_known_values():
    result = _gate("csv_demo", "customers", mixed_customer_batch())
    known = {code.value for code in ErrorCode} | {code.value for code in QualityCode}
    assert {finding.code for q in result.quarantined for finding in q.findings} <= known
    assert all(isinstance(q.code, str) and q.code == q.code.upper() for q in result.quarantined)


# ---------------------------------------------------------------------------
# D. System failures
# ---------------------------------------------------------------------------


def test_unexpected_d1_error_fails_loudly_instead_of_quarantining(monkeypatch):
    real_map_record = d1_pipeline.map_record

    def explode_for_one(config, profile, mapping, record):
        if record.get("deal_id") == "DEAL-002":
            raise RuntimeError("programming bug")
        return real_map_record(config, profile, mapping, record)

    monkeypatch.setattr(d1_pipeline, "map_record", explode_for_one)
    good, _ = full_case("csv_demo", "deals")
    records = [good, with_value(good, "deal_id", "DEAL-002"), with_value(good, "amount", "abc")]
    with pytest.raises(QualityGateSystemError) as excinfo:
        _gate("csv_demo", "deals", records)
    error = excinfo.value
    assert type(error) is QualityGateSystemError
    assert error.code is SystemFailureCode.NORMALIZATION_SYSTEM_FAILURE
    assert (error.source_system, error.entity_type, error.source_id, error.record_index) == (
        "csv_demo", "deals", "DEAL-002", 1)
    assert isinstance(error.__cause__, NormalizationError)
    assert error.__cause__.code is ErrorCode.UNEXPECTED_ERROR
    assert isinstance(error.__cause__.__cause__, RuntimeError)
    assert str(error).startswith("[NORMALIZATION_SYSTEM_FAILURE] csv_demo/deals/DEAL-002 record #1")


@pytest.mark.parametrize("error", [
    UnsupportedSourceError("source missing from configuration"),
    UnsupportedEntityError("entity missing from configuration"),
    NormalizationError("unexpected", code=ErrorCode.UNEXPECTED_ERROR),
], ids=["unsupported-source", "unsupported-entity", "unexpected"])
def test_non_data_normalization_errors_fail_loudly(monkeypatch, error):
    monkeypatch.setattr(gate, "normalize", _raising(error))
    with pytest.raises(QualityGateSystemError) as excinfo:
        _gate("csv_demo", "deals", [full_case("csv_demo", "deals")[0]])
    assert excinfo.value.code is SystemFailureCode.NORMALIZATION_SYSTEM_FAILURE
    assert excinfo.value.__cause__ is error


def test_unclassified_normalization_error_code_fails_closed(monkeypatch):
    error = NormalizationError("future code", code=ErrorCode.INVALID_TYPE)
    error.code = "SOME_FUTURE_CODE"
    monkeypatch.setattr(gate, "normalize", _raising(error))
    with pytest.raises(QualityGateSystemError) as excinfo:
        _gate("csv_demo", "deals", [{}])
    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize("error", [
    NormalizationConfigError("broken mapping configuration"),
    KeyError("programming bug"),
    OSError("filesystem failure"),
    AssertionError("impossible state"),
    TypeError("programmer error"),
], ids=["config", "key-error", "os-error", "assertion", "type-error"])
def test_other_exceptions_propagate_unchanged(monkeypatch, error):
    monkeypatch.setattr(gate, "normalize", _raising(error))
    with pytest.raises(type(error)) as excinfo:
        _gate("csv_demo", "deals", [full_case("csv_demo", "deals")[0]])
    assert excinfo.value is error


def test_bug_in_d2_rules_propagates(monkeypatch):
    monkeypatch.setattr(gate, "check_canonical_record", _raising(ZeroDivisionError("bug")))
    with pytest.raises(ZeroDivisionError):
        _gate("csv_demo", "deals", [full_case("csv_demo", "deals")[0]])


def test_bug_in_quarantine_construction_propagates(monkeypatch):
    monkeypatch.setattr(gate, "quarantine_from_normalization_error", _raising(ValueError("bug")))
    record = with_value(full_case("csv_demo", "deals")[0], "amount", "abc")
    with pytest.raises(ValueError, match="bug"):
        _gate("csv_demo", "deals", [record])


def test_validation_configuration_failure_propagates(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "default_validation_config",
                        lambda: load_validation_config(tmp_path / "missing.yaml"))
    with pytest.raises(ValidationConfigError):
        _gate("csv_demo", "deals", [full_case("csv_demo", "deals")[0]])


def test_normalization_configuration_failure_propagates(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "default_config", lambda: load_config(tmp_path))
    with pytest.raises(NormalizationConfigError):
        _gate("csv_demo", "deals", [full_case("csv_demo", "deals")[0]])


@pytest.mark.parametrize(("source", "entity", "code"), [
    ("odoo", "deals", SystemFailureCode.UNSUPPORTED_SOURCE),
    ("rest_demo", "deals", SystemFailureCode.UNSUPPORTED_SOURCE),
    (None, "deals", SystemFailureCode.UNSUPPORTED_SOURCE),
    ("csv_demo", "invoices", SystemFailureCode.UNSUPPORTED_ENTITY),
])
def test_unsupported_batch_context_fails_before_processing(source, entity, code):
    consumed = []

    def records():
        consumed.append(True)
        yield {}

    with pytest.raises(QualityGateSystemError) as excinfo:
        validate_source_batch(source, entity, records(), RUN_ID, INGESTED_AT)
    assert excinfo.value.code is code
    assert consumed == []
    with pytest.raises(QualityGateSystemError):
        validate_source_batch(source, entity, [], RUN_ID, INGESTED_AT)


@pytest.mark.parametrize(("run_id", "ingested_at", "error"), [
    (str(RUN_ID), INGESTED_AT, TypeError),
    (RUN_ID, "2026-09-14T12:00:00Z", TypeError),
    (RUN_ID, INGESTED_AT.replace(tzinfo=None), ValueError),
])
def test_invalid_invocation_fails_even_for_empty_batches(run_id, ingested_at, error):
    with pytest.raises(error):
        validate_source_batch("csv_demo", "deals", [], run_id, ingested_at)


# ---------------------------------------------------------------------------
# E. Warnings
# ---------------------------------------------------------------------------


def test_identical_duplicates_stay_valid_with_a_warning():
    good, _ = full_case("rest_mock", "deals")
    result = _gate("rest_mock", "deals", [good, copy.deepcopy(good)])
    assert result.valid_count == 2 and result.quarantined == ()
    assert [(w.severity, w.code, w.record_index, w.source_id, w.field_name)
            for w in result.warnings] == [
        (Severity.WARNING, "DUPLICATE_SOURCE_RECORD", 1, "DEAL-003", "source_id")]
    assert "#0" in result.warnings[0].message


def test_conflicting_duplicates_stay_valid_with_a_conflict_warning():
    good, _ = full_case("csv_demo", "projects")
    changed = with_value(good, "project_name", "Platform Migration Phase 2")
    result = _gate("csv_demo", "projects", [good, changed])
    assert result.valid_count == 2 and result.quarantined == ()
    assert [w.code for w in result.warnings] == ["DUPLICATE_SOURCE_IDENTITY_CONFLICT"]


def test_equivalent_representations_are_identical_duplicates():
    good, _ = full_case("odoo_mock", "deals")
    result = _gate("odoo_mock", "deals", [good, with_value(good, "active", 1)])
    assert [w.code for w in result.warnings] == ["DUPLICATE_SOURCE_RECORD"]


def test_every_later_duplicate_references_the_first_occurrence():
    good, _ = full_case("csv_demo", "organizations")
    result = _gate("csv_demo", "organizations", [good, good, good])
    assert [(w.record_index, w.code) for w in result.warnings] == [
        (1, "DUPLICATE_SOURCE_RECORD"), (2, "DUPLICATE_SOURCE_RECORD")]
    assert all("#0" in w.message for w in result.warnings)


def test_quarantined_records_do_not_count_as_duplicates():
    good, _ = full_case("csv_demo", "deals")
    result = _gate("csv_demo", "deals", [good, with_value(good, "stage", "lost")])
    assert result.warnings == ()


@pytest.mark.parametrize(("source", "entity", "field"), [
    ("csv_demo", "customers", "email_address"), ("odoo_mock", "customers", "email"),
    ("rest_mock", "customers", "email"), ("csv_demo", "employees", "email_address"),
    ("odoo_mock", "employees", "work_email"), ("rest_mock", "employees", "email"),
])
def test_missing_email_is_a_warning_not_a_quarantine(source, entity, field):
    record, expected = full_case(source, entity)
    result = _gate(source, entity, [with_value(record, field, ABSENT)])
    assert result.valid_count == 1 and result.quarantined == ()
    assert [(w.severity, w.code, w.field_name, w.record_index, w.source_id)
            for w in result.warnings] == [
        (Severity.WARNING, "MISSING_RECOMMENDED_FIELD", "email", 0, expected["source_id"])]


def test_entities_without_recommended_fields_emit_no_completeness_warnings():
    result = _gate("csv_demo", "deals", [{"deal_id": "D1", "deal_name": "Minimal",
                                          "is_active": "true"}])
    assert result.valid_count == 1 and result.warnings == ()


# ---------------------------------------------------------------------------
# F. Empty batches, immutability, determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("records", [[], (), iter([])], ids=["list", "tuple", "iterator"])
def test_empty_batch_returns_an_explicit_empty_result(records):
    result = _gate("csv_demo", "customers", records)
    assert (result.total_records, result.valid, result.quarantined, result.warnings) == (
        0, (), (), ())
    assert result.summary()["total_records"] == 0


def test_generator_input_is_supported():
    good, _ = full_case("csv_demo", "customers")
    result = _gate("csv_demo", "customers", (record for record in [good, None]))
    assert (result.valid_count, result.quarantined_count) == (1, 1)


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_source_records_are_not_mutated(source, entity):
    record, _ = full_case(source, entity)
    first_field = next(iter(record))
    records = [record, with_value(record, first_field, ABSENT), None, copy.deepcopy(record)]
    snapshot = copy.deepcopy(records)
    identities = [id(item) for item in records]
    _gate(source, entity, records)
    assert records == snapshot
    assert [id(item) for item in records] == identities


def test_result_and_quarantine_records_are_immutable():
    result = _gate("csv_demo", "customers", mixed_customer_batch())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.valid = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.quarantined[0].code_override = "X"
    assert isinstance(result.valid, tuple) and isinstance(result.quarantined, tuple)


def test_repeated_calls_are_identical():
    fingerprints = {fingerprint(_gate("csv_demo", "customers", mixed_customer_batch()))
                    for _ in range(3)}
    assert len(fingerprints) == 1


def test_mixed_batch_expected_partition():
    result = _gate("csv_demo", "customers", mixed_customer_batch())
    assert [r.source_id for r in result.valid] == ["CUST-001", "CUST-002", "CUST-001"]
    assert [(q.record_index, q.code) for q in result.quarantined] == [
        (1, "REQUIRED_FIELD_MISSING"), (2, "INVALID_RECORD"), (5, "UNKNOWN_ENUM_VALUE")]
    assert [(w.record_index, w.code) for w in result.warnings] == [
        (3, "MISSING_RECOMMENDED_FIELD"), (4, "DUPLICATE_SOURCE_RECORD")]
    assert result.quarantined[2].raw_record["tags"] == ["apac", "renewal", "vip"]
    assert result.quarantined[2].raw_record["api_key"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# G. Cross-source classification
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_payloads():
    sys.path.insert(0, str(REPO / "docker"))
    import mock_source

    connector = CsvConnector(
        CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml"),
        base_path=REPO,
    )
    odoo, rest = mock_source.load_source_data(REPO / "data" / "demo")
    csv_rows = {entity: connector.fetch_entities(entity, page_size=10_000).items
                for entity in ENTITIES}
    return {"csv_demo": csv_rows, "odoo_mock": odoo, "rest_mock": rest}


@pytest.mark.parametrize("entity", ENTITIES)
def test_demo_dataset_validates_identically_across_sources(demo_payloads, entity):
    shapes = set()
    for source in SOURCES:
        records = demo_payloads[source][entity]
        result = _gate(source, entity, records)
        assert result.quarantined == ()
        assert result.valid_count == len(records) > 0
        shapes.add(tuple((w.record_index, w.code, w.field_name) for w in result.warnings))
    assert len(shapes) == 1


@pytest.mark.parametrize(("value", "code"), [
    ("stalled", "UNKNOWN_ENUM_VALUE"), ("", None),
])
def test_same_invalid_business_value_classifies_identically_across_sources(value, code):
    fields = {"csv_demo": "status", "odoo_mock": "stage_id", "rest_mock": "status"}
    outcomes = set()
    for source in SOURCES:
        record, _ = full_case(source, "projects")
        result = _gate(source, "projects", [with_value(record, fields[source], value)])
        outcomes.add(tuple((q.stage, q.code, q.field_name) for q in result.quarantined))
    assert len(outcomes) == 1
    expected = () if code is None else ((Stage.NORMALIZATION, code, "status"),)
    assert outcomes == {expected}
