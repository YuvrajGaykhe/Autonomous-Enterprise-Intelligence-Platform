"""
D1 identity and record_hash tests.

Covers canonical_id determinism and the record_hash contract:
reproducibility, key-order independence, field sensitivity, provenance
independence, Decimal-scale and boolean-representation independence,
timestamp equivalence, and exclusion of E1-resolved FK fields.
"""

from __future__ import annotations

import hashlib
import json
import typing
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from d1_support import (
    CASE_KEYS,
    INGESTED_AT,
    RUN_ID,
    business,
    case_id,
    full_case,
    with_value,
)

from app.normalization import canonical_id, default_config, normalize, record_hash
from app.normalization.contract import (
    BUSINESS_FIELDS,
    CANONICAL_SCHEMAS,
    E1_RESOLVED_FIELDS,
    PROVENANCE_FIELDS,
)
from app.normalization.identifiers import hash_payload


def _normalize(source, entity, record, run_id=RUN_ID, ingested_at=INGESTED_AT):
    return normalize(source, entity, record, run_id, ingested_at)


def _hash_of(source, entity, record):
    return _normalize(source, entity, record).record_hash


# ---------------------------------------------------------------------------
# canonical_id
# ---------------------------------------------------------------------------


def test_canonical_id_golden_value():
    """The namespace and name format are frozen: persisted IDs depend on them."""
    assert canonical_id("csv_demo", "customers", "CUST-001") == uuid.UUID(
        "ebbf3280-9768-5383-9fd2-802d999531de"
    )


def test_canonical_id_is_deterministic_uuid5():
    first = canonical_id("odoo_mock", "deals", "7")
    assert first == canonical_id("odoo_mock", "deals", "7")
    assert first.version == 5


@pytest.mark.parametrize("other", [
    ("odoo_mock", "customers", "CUST-001"),
    ("csv_demo", "employees", "CUST-001"),
    ("csv_demo", "customers", "CUST-002"),
])
def test_canonical_id_depends_on_every_identity_component(other):
    assert canonical_id("csv_demo", "customers", "CUST-001") != canonical_id(*other)


# ---------------------------------------------------------------------------
# Reproducibility and format
# ---------------------------------------------------------------------------


def test_record_hash_golden_value():
    """Changing the hash serialization would mark every stored record as updated."""
    obj = _normalize("csv_demo", "customers",
                     {"customer_id": "CUST-001", "customer_name": "Acme", "status": "active"})
    assert obj.record_hash == "f4a6f8543addf7592627af40a2c82225de3acb4f8f4d1c5a530363802456d69a"


def test_record_hash_is_sha256_of_canonical_json():
    obj = _normalize(*CASE_KEYS[0], full_case(*CASE_KEYS[0])[0])
    payload = json.dumps(hash_payload(obj), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    assert obj.record_hash == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert len(obj.record_hash) == 64
    int(obj.record_hash, 16)


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_record_hash_is_reproducible_from_canonical_object(source, entity):
    record, _ = full_case(source, entity)
    obj = _normalize(source, entity, record)
    schema = CANONICAL_SCHEMAS[entity]
    assert record_hash(obj) == obj.record_hash
    assert record_hash(schema.model_validate(obj.model_dump())) == obj.record_hash
    assert record_hash(schema.model_validate_json(obj.model_dump_json())) == obj.record_hash


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_hash_payload_covers_exactly_business_fields(source, entity):
    record, _ = full_case(source, entity)
    payload = hash_payload(_normalize(source, entity, record))
    assert set(payload) == set(BUSINESS_FIELDS[entity])
    assert not set(payload) & (PROVENANCE_FIELDS | E1_RESOLVED_FIELDS[entity])


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_key_order_independence(source, entity):
    record, _ = full_case(source, entity)
    reordered = dict(reversed(list(record.items())))
    first, second = _normalize(source, entity, record), _normalize(source, entity, reordered)
    assert first.record_hash == second.record_hash
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------


def _alternative(value, kind):
    if kind == "boolean":
        return not value
    if kind == "decimal":
        return value + 1
    if kind == "date":
        return value + timedelta(days=1)
    if kind == "datetime":
        return value + timedelta(seconds=1)
    return value + "-changed"


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_every_business_field_changes_the_hash(source, entity):
    record, _ = full_case(source, entity)
    obj = _normalize(source, entity, record)
    specs = default_config().fields[entity]
    seen = {obj.record_hash}
    for name in BUSINESS_FIELDS[entity]:
        changed = obj.model_copy(update={name: _alternative(getattr(obj, name), specs[name].kind)})
        assert record_hash(changed) != obj.record_hash, name
        seen.add(record_hash(changed))
        if not specs[name].required:
            assert record_hash(obj.model_copy(update={name: None})) != obj.record_hash, name
    assert len(seen) == len(BUSINESS_FIELDS[entity]) + 1


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_changing_source_business_value_changes_hash(source, entity):
    record, expected = full_case(source, entity)
    original = _normalize(source, entity, record)
    different_name_field = next(
        (field for field in ("name", "subject", "title") if field in expected["fields"]), None
    )
    source_field = {
        ("csv_demo", "organizations"): "organization_name", ("csv_demo", "employees"): "employee_name",
        ("csv_demo", "customers"): "customer_name", ("csv_demo", "deals"): "deal_name",
        ("csv_demo", "projects"): "project_name", ("odoo_mock", "support_tickets"): "name",
        ("odoo_mock", "documents"): "name",
    }.get((source, entity), different_name_field)
    changed = _normalize(source, entity, with_value(record, source_field, "Renamed Record"))
    assert changed.record_hash != original.record_hash


# ---------------------------------------------------------------------------
# Independence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_provenance_does_not_affect_hash(source, entity):
    record, _ = full_case(source, entity)
    obj = _normalize(source, entity, record)
    other_run = _normalize(source, entity, record, run_id=uuid.uuid4(),
                           ingested_at=datetime(2030, 5, 5, 5, tzinfo=UTC))
    assert other_run.record_hash == obj.record_hash
    changed = obj.model_copy(update={
        "id": uuid.uuid4(),
        "source_system": "other_source",
        "source_entity": "other_entity",
        "source_id": "OTHER-1",
        "source_updated_at": datetime(2000, 1, 1, tzinfo=UTC),
        "ingested_at": datetime(2001, 1, 1, tzinfo=UTC),
        "ingestion_run_id": uuid.uuid4(),
        "record_hash": "stale",
    })
    assert record_hash(changed) == obj.record_hash


def test_same_content_under_a_different_source_id_has_the_same_hash():
    record, _ = full_case("csv_demo", "customers")
    first = _normalize("csv_demo", "customers", record)
    second = _normalize("csv_demo", "customers", with_value(record, "customer_id", "CUST-999"))
    assert first.id != second.id
    assert first.record_hash == second.record_hash


@pytest.mark.parametrize(("entity", "fk_field"), [
    (entity, fk) for entity, fields in E1_RESOLVED_FIELDS.items() for fk in sorted(fields)
])
def test_e1_resolved_fk_fields_do_not_affect_hash(entity, fk_field):
    for source in ("csv_demo", "odoo_mock", "rest_mock"):
        record, _ = full_case(source, entity)
        obj = _normalize(source, entity, record)
        resolved = obj.model_copy(update={fk_field: uuid.uuid4()})
        assert record_hash(resolved) == obj.record_hash


def test_e1_resolved_fields_are_exactly_the_canonical_uuid_fks():
    """Guard: a new UUID FK in B2 must be classified before it can leak into hashes."""
    for entity, schema in CANONICAL_SCHEMAS.items():
        uuid_fields = {
            name for name, field in schema.model_fields.items()
            if uuid.UUID in (typing.get_args(field.annotation) or (field.annotation,))
        }
        assert uuid_fields - {"id", "ingestion_run_id"} == set(E1_RESOLVED_FIELDS[entity])


@pytest.mark.parametrize(("source", "field", "values"), [
    ("csv_demo", "amount", ["100.5", "100.50", "100.500", "+100.5", " 100.5 "]),
    ("odoo_mock", "expected_revenue", [100.5, 100.50, "100.5", "100.50", 100.5000]),
    ("rest_mock", "amount", [100.5, "100.500"]),
])
def test_decimal_scale_does_not_affect_hash(source, field, values):
    record, _ = full_case(source, "deals")
    hashes = {_hash_of(source, "deals", with_value(record, field, value)) for value in values}
    assert len(hashes) == 1


def test_hash_decimal_serialization_is_scale_independent():
    record, _ = full_case("csv_demo", "deals")
    obj = _normalize("csv_demo", "deals", record)
    for amount in (Decimal("150000.5"), Decimal("150000.5000"), Decimal("1.500005E+5")):
        assert record_hash(obj.model_copy(update={"amount": amount})) == obj.record_hash
    zero = obj.model_copy(update={"amount": Decimal("0.00")})
    assert record_hash(zero) == record_hash(obj.model_copy(update={"amount": Decimal("-0")}))


@pytest.mark.parametrize(("source", "entity", "field", "values"), [
    ("csv_demo", "deals", "is_active", ["true", "TRUE", " Yes ", "1"]),
    ("csv_demo", "employees", "is_active", ["false", "No", "0", " FALSE "]),
    ("odoo_mock", "deals", "active", [True, 1, "true", "YES"]),
    ("odoo_mock", "customers", "active", [False, 0, "false", "no"]),
    ("rest_mock", "projects", "isActive", [True, "true", 1]),
])
def test_boolean_representation_does_not_affect_hash(source, entity, field, values):
    record, _ = full_case(source, entity)
    hashes = {_hash_of(source, entity, with_value(record, field, value)) for value in values}
    assert len(hashes) == 1


def test_equivalent_timestamps_produce_the_same_hash():
    record, _ = full_case("rest_mock", "customers")
    values = ["2026-01-01T12:00:00Z", "2026-01-01T17:30:00+05:30", "2026-01-01T07:00:00-05:00"]
    hashes = {_hash_of("rest_mock", "customers", with_value(record, "createdAt", v)) for v in values}
    assert len(hashes) == 1


def test_lexical_normalization_does_not_affect_hash():
    record, _ = full_case("csv_demo", "projects")
    variants = [
        with_value(with_value(record, "status", "in_progress"), "project_name", "Platform Migration"),
        with_value(with_value(record, "status", " In Progress "), "project_name", "  Platform Migration "),
    ]
    assert len({_hash_of("csv_demo", "projects", variant) for variant in variants}) == 1


def test_unmapped_source_fields_do_not_affect_hash():
    record, _ = full_case("rest_mock", "support_tickets")
    extra = dict(record, name="stray mapper-only field", internalFlag=True)
    assert _hash_of("rest_mock", "support_tickets", record) == _hash_of("rest_mock", "support_tickets", extra)


def test_cross_process_hash_equals_business_payload_hash():
    record, _ = full_case("odoo_mock", "documents")
    obj = _normalize("odoo_mock", "documents", record)
    assert business(obj)["updated_at"] == datetime(2026, 6, 15, 10, 20, 30, tzinfo=UTC)
    assert hash_payload(obj)["updated_at"] == "2026-06-15T10:20:30+00:00"


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


def test_record_hash_rejects_naive_datetimes():
    record, _ = full_case("csv_demo", "customers")
    obj = _normalize("csv_demo", "customers", record)
    with pytest.raises(ValueError, match="Naive datetime"):
        record_hash(obj.model_copy(update={"created_at": datetime(2026, 1, 1)}))


def test_record_hash_rejects_unsupported_value_types():
    record, _ = full_case("csv_demo", "deals")
    obj = _normalize("csv_demo", "deals", record)
    with pytest.raises(TypeError, match="Unsupported value type"):
        record_hash(obj.model_copy(update={"amount": 1.5}))
    with pytest.raises(ValueError, match="Non-finite"):
        record_hash(obj.model_copy(update={"amount": Decimal("NaN")}))


def test_record_hash_rejects_non_canonical_objects():
    with pytest.raises(TypeError, match="Not a canonical entity schema"):
        record_hash({"name": "Acme"})


def test_date_values_hash_as_iso_dates():
    record, _ = full_case("csv_demo", "projects")
    payload = hash_payload(_normalize("csv_demo", "projects", record))
    assert payload["start_date"] == date(2026, 1, 1).isoformat()
    assert payload["budget"] == "500000"
