"""
D2 canonical rule tests: validate_canonical_batch on real D1 output.

Covers:
A. Valid D1 records pass as the same, unmodified objects
B. Data-contract violations quarantine with semantic codes, per field kind
C. Coverage across all seven canonical entities
D. System invariants raise instead of quarantining
E. Ordering, duplicates, immutability, cross-source classification
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from d1_support import CASE_KEYS, RUN_ID, SOURCES, case_id, full_case, with_value
from d2_support import canonical, tamper

from app.normalization import default_config, normalize
from app.normalization.contract import (
    BUSINESS_FIELDS,
    CANONICAL_SCHEMAS,
    E1_RESOLVED_FIELDS,
    is_required,
)
from app.validation import (
    CanonicalInvariantError,
    QualityGateSystemError,
    Severity,
    Stage,
    SystemFailureCode,
    default_validation_config,
    validate_canonical_batch,
)
from app.validation.quarantine import safe_payload
from app.validation.rules import canonical_values


def _validate(records, source="csv_demo", entity="deals", **kwargs):
    return validate_canonical_batch(source, entity, records, RUN_ID, **kwargs)


def _only_quarantine(record, source="csv_demo", entity="deals"):
    result = _validate([record], source, entity)
    assert result.valid == ()
    assert len(result.quarantined) == 1
    return result.quarantined[0]


def _findings(quarantined):
    return [(finding.field_name, finding.code) for finding in quarantined.findings]


# ---------------------------------------------------------------------------
# A. Valid records
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_d1_output_is_valid_and_returned_unmodified(source, entity):
    record = canonical(source, entity)
    before = dict(vars(record))
    result = _validate([record], source, entity)
    assert result.quarantined == () and result.warnings == ()
    assert result.valid[0] is record
    assert dict(vars(record)) == before


# ---------------------------------------------------------------------------
# B. Data-contract violations
# ---------------------------------------------------------------------------

DATA_VIOLATIONS = [
    ("required-none", "csv_demo", "customers", {"name": None},
     [("name", "REQUIRED_FIELD_MISSING")]),
    ("required-blank", "rest_mock", "deals", {"name": "   "},
     [("name", "REQUIRED_FIELD_MISSING")]),
    ("required-boolean-none", "odoo_mock", "projects", {"is_active": None},
     [("is_active", "REQUIRED_FIELD_MISSING")]),
    ("enum-unknown", "csv_demo", "deals", {"stage": "lost"},
     [("stage", "UNKNOWN_ENUM_VALUE")]),
    ("enum-not-normalized", "rest_mock", "projects", {"status": "In Progress"},
     [("status", "UNKNOWN_ENUM_VALUE")]),
    ("enum-priority", "odoo_mock", "support_tickets", {"priority": "low"},
     [("priority", "UNKNOWN_ENUM_VALUE")]),
    ("source-id-blank", "csv_demo", "customers", {"source_id": ""},
     [("source_id", "SOURCE_ID_MISSING")]),
    ("source-id-none", "rest_mock", "customers", {"source_id": None},
     [("source_id", "SOURCE_ID_MISSING")]),
    ("source-id-whitespace", "rest_mock", "deals", {"source_id": " DEAL-003"},
     [("source_id", "SOURCE_ID_INVALID")]),
    ("odoo-source-id-text", "odoo_mock", "deals", {"source_id": "abc"},
     [("source_id", "SOURCE_ID_INVALID")]),
    ("odoo-source-id-leading-zero", "odoo_mock", "deals", {"source_id": "01"},
     [("source_id", "SOURCE_ID_INVALID")]),
    ("source-id-integer", "csv_demo", "deals", {"source_id": 5},
     [("source_id", "SOURCE_ID_INVALID")]),
    ("naive-datetime", "csv_demo", "customers", {"created_at": datetime(2025, 1, 15, 9, 45)},
     [("created_at", "NAIVE_DATETIME_REJECTED")]),
    ("non-utc-datetime", "rest_mock", "support_tickets",
     {"resolved_at": datetime(2026, 9, 1, 21, 30, tzinfo=timezone(timedelta(hours=-4)))},
     [("resolved_at", "NON_CANONICAL_VALUE")]),
    ("datetime-as-string", "odoo_mock", "documents", {"created_at": "2026-01-01T00:00:00Z"},
     [("created_at", "INVALID_TYPE")]),
    ("naive-source-updated-at", "rest_mock", "documents",
     {"source_updated_at": datetime(2026, 6, 15)},
     [("source_updated_at", "NAIVE_DATETIME_REJECTED")]),
    ("decimal-scale", "csv_demo", "deals", {"amount": Decimal("150000.505")},
     [("amount", "DECIMAL_SCALE_EXCEEDED")]),
    ("decimal-precision", "odoo_mock", "projects", {"budget": Decimal("10000000000000.00")},
     [("budget", "DECIMAL_PRECISION_EXCEEDED")]),
    ("decimal-range", "rest_mock", "deals", {"probability": Decimal("100.01")},
     [("probability", "DECIMAL_OUT_OF_RANGE")]),
    ("decimal-not-quantized", "csv_demo", "deals", {"amount": Decimal("150000.5")},
     [("amount", "NON_CANONICAL_VALUE")]),
    ("decimal-negative-zero", "csv_demo", "projects", {"budget": Decimal("-0.00")},
     [("budget", "NON_CANONICAL_VALUE")]),
    ("decimal-nan", "csv_demo", "deals", {"amount": Decimal("NaN")},
     [("amount", "INVALID_DECIMAL")]),
    ("decimal-as-float", "odoo_mock", "deals", {"amount": 150000.5},
     [("amount", "INVALID_TYPE")]),
    ("relationship-key-blank", "csv_demo", "deals", {"customer_source_id": ""},
     [("customer_source_id", "RELATIONSHIP_KEY_INVALID")]),
    ("relationship-key-whitespace", "rest_mock", "support_tickets",
     {"assignee_source_id": " EMP-001 "}, [("assignee_source_id", "RELATIONSHIP_KEY_INVALID")]),
    ("odoo-relationship-key-text", "odoo_mock", "deals", {"owner_source_id": "EMP-002"},
     [("owner_source_id", "RELATIONSHIP_KEY_INVALID")]),
    ("relationship-key-integer", "rest_mock", "projects", {"customer_source_id": 12},
     [("customer_source_id", "RELATIONSHIP_KEY_INVALID")]),
    ("boolean-as-string", "rest_mock", "employees", {"is_active": "true"},
     [("is_active", "INVALID_TYPE")]),
    ("date-as-datetime", "csv_demo", "employees",
     {"hire_date": datetime(2025, 1, 10, tzinfo=UTC)}, [("hire_date", "INVALID_TYPE")]),
    ("name-as-integer", "odoo_mock", "organizations", {"name": 123},
     [("name", "INVALID_TYPE")]),
    ("currency-lowercase", "csv_demo", "deals", {"currency": "inr"},
     [("currency", "INVALID_CURRENCY")]),
    ("currency-unknown", "rest_mock", "deals", {"currency": "XYZ"},
     [("currency", "INVALID_CURRENCY")]),
    ("string-whitespace", "rest_mock", "organizations", {"country": " Germany"},
     [("country", "NON_CANONICAL_VALUE")]),
    ("optional-blank-string", "odoo_mock", "customers", {"segment": ""},
     [("segment", "NON_CANONICAL_VALUE")]),
    ("email-not-lowercase", "csv_demo", "employees", {"email": "Carol@GlobalTech.example"},
     [("email", "NON_CANONICAL_VALUE")]),
    ("blank-text", "csv_demo", "documents", {"body_text": "  \n"},
     [("body_text", "NON_CANONICAL_VALUE")]),
]


@pytest.mark.parametrize(("source", "entity", "updates", "expected"),
                         [case[1:] for case in DATA_VIOLATIONS],
                         ids=[case[0] for case in DATA_VIOLATIONS])
def test_data_violations_are_quarantined(source, entity, updates, expected):
    record = tamper(canonical(source, entity), **updates)
    quarantined = _only_quarantine(record, source, entity)
    assert quarantined.stage is Stage.VALIDATION
    assert _findings(quarantined) == expected
    assert all(finding.severity is Severity.ERROR for finding in quarantined.findings)
    source_id = record.source_id if isinstance(record.source_id, str) and record.source_id.strip() else None
    assert quarantined.source_id == source_id
    assert quarantined.canonical_id == record.id
    assert (quarantined.source_system, quarantined.entity_type, quarantined.ingestion_run_id) == (
        source, entity, RUN_ID)
    expected_payload = safe_payload(canonical_values(record), default_validation_config().quarantine)
    assert quarantined.raw_record == expected_payload
    assert set(quarantined.raw_record) == set(CANONICAL_SCHEMAS[entity].model_fields)


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_missing_required_attributes_are_quarantined(source, entity):
    record = canonical(source, entity)
    schema = CANONICAL_SCHEMAS[entity]
    required = [name for name in BUSINESS_FIELDS[entity] if is_required(entity, name)]
    without_source_id = schema.model_construct(
        **{k: v for k, v in vars(record).items() if k != "source_id"})
    assert _findings(_only_quarantine(without_source_id, source, entity)) == [
        ("source_id", "SOURCE_ID_MISSING")]
    if required:
        without_required = schema.model_construct(
            **{k: v for k, v in vars(record).items() if k not in required})
        assert _findings(_only_quarantine(without_required, source, entity)) == [
            (name, "REQUIRED_FIELD_MISSING") for name in required]


def test_multiple_violations_are_reported_in_canonical_field_order():
    record = tamper(canonical("csv_demo", "deals"), customer_source_id="", is_active="yes",
                    amount=Decimal("1.001"), stage="lost", source_id="")
    assert _findings(_only_quarantine(record)) == [
        ("source_id", "SOURCE_ID_MISSING"),
        ("stage", "UNKNOWN_ENUM_VALUE"),
        ("amount", "DECIMAL_SCALE_EXCEEDED"),
        ("is_active", "INVALID_TYPE"),
        ("customer_source_id", "RELATIONSHIP_KEY_INVALID"),
    ]


def test_finding_raw_values_are_safe_representations():
    record = tamper(canonical("csv_demo", "deals"), stage="lost", amount=Decimal("1.001"))
    assert [(f.field_name, f.raw_value) for f in _only_quarantine(record).findings] == [
        ("stage", "'lost'"), ("amount", "'1.001'")]


# ---------------------------------------------------------------------------
# C. All seven entities
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_every_field_rejects_the_wrong_python_type(source, entity):
    record = canonical(source, entity)
    specs = default_config().fields[entity]
    for name in BUSINESS_FIELDS[entity]:
        expected = "RELATIONSHIP_KEY_INVALID" if specs[name].kind == "source_key" else "INVALID_TYPE"
        quarantined = _only_quarantine(tamper(record, **{name: object()}), source, entity)
        assert _findings(quarantined) == [(name, expected)], name
        assert quarantined.findings[0].raw_value == "'<object>'"


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_every_string_field_rejects_surrounding_whitespace(source, entity):
    record = canonical(source, entity)
    for name, spec in default_config().fields[entity].items():
        if spec.kind not in ("string", "email", "source_key", "enum", "currency"):
            continue
        padded = tamper(record, **{name: f" {getattr(record, name)} "})
        expected = {
            "source_key": "RELATIONSHIP_KEY_INVALID",
            "enum": "UNKNOWN_ENUM_VALUE",
            "currency": "INVALID_CURRENCY",
        }.get(spec.kind, "NON_CANONICAL_VALUE")
        assert _findings(_only_quarantine(padded, source, entity)) == [(name, expected)], name


DATETIME_CASES = [key for key in CASE_KEYS if any(
    spec.kind == "datetime" for spec in default_config().fields[key[1]].values())]


@pytest.mark.parametrize(("source", "entity"), DATETIME_CASES, ids=case_id)
def test_every_datetime_field_rejects_naive_and_non_utc_values(source, entity):
    record = canonical(source, entity)
    ist = timezone(timedelta(hours=5, minutes=30))
    for name, spec in default_config().fields[entity].items():
        if spec.kind != "datetime":
            continue
        value = getattr(record, name)
        naive = tamper(record, **{name: value.replace(tzinfo=None)})
        shifted = tamper(record, **{name: value.astimezone(ist)})
        assert _findings(_only_quarantine(naive, source, entity)) == [
            (name, "NAIVE_DATETIME_REJECTED")]
        assert _findings(_only_quarantine(shifted, source, entity)) == [
            (name, "NON_CANONICAL_VALUE")]


# ---------------------------------------------------------------------------
# D. System invariants
# ---------------------------------------------------------------------------

_DEAL_HASH = canonical().record_hash

INVARIANT_VIOLATIONS = [
    ("wrong-schema", lambda: canonical("csv_demo", "customers"),
     SystemFailureCode.WRONG_ENTITY_SCHEMA, None),
    ("plain-dict", lambda: canonical().model_dump(), SystemFailureCode.WRONG_ENTITY_SCHEMA, None),
    ("none", lambda: None, SystemFailureCode.WRONG_ENTITY_SCHEMA, None),
    ("source-system", lambda: tamper(canonical(), source_system="rest_mock"),
     SystemFailureCode.PROVENANCE_MISMATCH, "source_system"),
    ("source-entity", lambda: tamper(canonical(), source_entity="customers"),
     SystemFailureCode.PROVENANCE_MISMATCH, "source_entity"),
    ("run-id", lambda: tamper(canonical(), ingestion_run_id=uuid.UUID(int=2)),
     SystemFailureCode.PROVENANCE_MISMATCH, "ingestion_run_id"),
    ("naive-ingested-at", lambda: tamper(canonical(), ingested_at=datetime(2026, 9, 14, 12)),
     SystemFailureCode.INVALID_PROVENANCE, "ingested_at"),
    ("non-utc-ingested-at",
     lambda: tamper(canonical(), ingested_at=datetime(2026, 9, 14, 17, 30,
                                                      tzinfo=timezone(timedelta(hours=5, minutes=30)))),
     SystemFailureCode.INVALID_PROVENANCE, "ingested_at"),
    ("id-not-uuid", lambda: tamper(canonical(), id=str(canonical().id)),
     SystemFailureCode.INVALID_PROVENANCE, "id"),
    ("hash-malformed", lambda: tamper(canonical(), record_hash="stale"),
     SystemFailureCode.INVALID_PROVENANCE, "record_hash"),
    ("hash-uppercase", lambda: tamper(canonical(), record_hash=_DEAL_HASH.upper()),
     SystemFailureCode.INVALID_PROVENANCE, "record_hash"),
    ("e1-fk", lambda: tamper(canonical(), customer_id=uuid.uuid4()),
     SystemFailureCode.E1_FIELD_POPULATED, "customer_id"),
    ("canonical-id", lambda: tamper(canonical(), id=uuid.UUID(int=7)),
     SystemFailureCode.CANONICAL_ID_MISMATCH, "id"),
    ("business-change-with-stale-hash", lambda: tamper(canonical(), name="Renamed Deal"),
     SystemFailureCode.RECORD_HASH_MISMATCH, "record_hash"),
    ("well-formed-wrong-hash", lambda: tamper(canonical(), record_hash="0" * 64),
     SystemFailureCode.RECORD_HASH_MISMATCH, "record_hash"),
]


@pytest.mark.parametrize(("build", "code", "field"), [case[1:] for case in INVARIANT_VIOLATIONS],
                         ids=[case[0] for case in INVARIANT_VIOLATIONS])
def test_invariant_violations_raise_instead_of_quarantining(build, code, field):
    good = canonical()
    with pytest.raises(QualityGateSystemError) as excinfo:
        _validate([good, build()])
    error = excinfo.value
    assert type(error) is CanonicalInvariantError
    assert error.code is code
    assert error.field_name == field
    assert (error.source_system, error.entity_type, error.record_index) == ("csv_demo", "deals", 1)
    assert str(error).startswith(f"[{code}] csv_demo/deals")


@pytest.mark.parametrize(("entity", "fk_field"), [
    (entity, fk) for entity, fields in E1_RESOLVED_FIELDS.items() for fk in sorted(fields)])
def test_populated_e1_fields_raise_for_every_entity(entity, fk_field):
    record = tamper(canonical("rest_mock", entity), **{fk_field: uuid.uuid4()})
    with pytest.raises(CanonicalInvariantError) as excinfo:
        _validate([record], "rest_mock", entity)
    assert (excinfo.value.code, excinfo.value.field_name) == (
        SystemFailureCode.E1_FIELD_POPULATED, fk_field)


def test_invariant_violations_take_precedence_over_data_violations():
    record = tamper(canonical(), source_system="odoo_mock", stage="lost")
    with pytest.raises(CanonicalInvariantError) as excinfo:
        _validate([record])
    assert excinfo.value.code is SystemFailureCode.PROVENANCE_MISMATCH


def test_invariant_error_messages_do_not_echo_values():
    record = tamper(canonical(), source_system="Bearer TEST_CREDENTIAL_VALUE_FOR_REDACTION")
    with pytest.raises(CanonicalInvariantError) as excinfo:
        _validate([record])
    assert "TEST_CREDENTIAL" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# E. Ordering, duplicates, immutability, cross-source
# ---------------------------------------------------------------------------


def test_batch_ordering_is_deterministic():
    good = canonical()
    second = normalize("csv_demo", "deals", with_value(full_case("csv_demo", "deals")[0],
                                                        "deal_id", "DEAL-002"), RUN_ID,
                       canonical().ingested_at)
    records = [tamper(good, stage="lost"), good, tamper(second, currency="usd"), second]
    first_run = _validate(records)
    assert [r.source_id for r in first_run.valid] == ["DEAL-001", "DEAL-002"]
    assert [(q.record_index, q.code) for q in first_run.quarantined] == [
        (0, "UNKNOWN_ENUM_VALUE"), (2, "INVALID_CURRENCY")]
    again = _validate(records)
    assert [q.to_dict() for q in again.quarantined] == [q.to_dict() for q in first_run.quarantined]
    assert all(a is b for a, b in zip(again.valid, first_run.valid, strict=True))


def test_canonical_duplicates_are_warnings():
    good = canonical()
    renamed = normalize("csv_demo", "deals",
                        with_value(full_case("csv_demo", "deals")[0], "deal_name", "Renamed"),
                        RUN_ID, good.ingested_at)
    result = _validate([good, good, renamed])
    assert result.valid_count == 3 and result.quarantined == ()
    assert [(w.record_index, w.code) for w in result.warnings] == [
        (1, "DUPLICATE_SOURCE_RECORD"), (2, "DUPLICATE_SOURCE_IDENTITY_CONFLICT")]


def test_validation_does_not_mutate_valid_or_invalid_records():
    good = canonical()
    bad = tamper(canonical(), stage="lost", amount=Decimal("1.5"))
    snapshots = [dict(vars(good)), dict(vars(bad))]
    _validate([good, bad, good])
    assert [dict(vars(good)), dict(vars(bad))] == snapshots


@pytest.mark.parametrize("updates", [
    {"stage": "lost"}, {"amount": Decimal("1.005")}, {"is_active": None}, {"currency": "usd"},
    {"expected_close_date": "2026-12-31"},
])
def test_invalid_canonical_values_classify_identically_across_sources(updates):
    outcomes = set()
    for source in SOURCES:
        quarantined = _only_quarantine(tamper(canonical(source, "deals"), **updates), source)
        outcomes.add(tuple((f.field_name, f.code, f.raw_value) for f in quarantined.findings))
    assert len(outcomes) == 1


def test_batch_with_system_failure_returns_no_partial_result():
    good = canonical()
    records = [good, tamper(good, stage="lost"), tamper(good, customer_id=uuid.uuid4())]
    with pytest.raises(CanonicalInvariantError):
        _validate(records)
