"""
D1 mapping tests: field-level wiring for all 21 source x entity combinations.

Covers:
A. Every business field of every combination (exact canonical values)
B. is_active True/False per source, status derivations
C. Required fields (name, is_active) reject missing / null-token values
D. Source identifiers and relationship keys
E. Enum, currency, decimal, date/datetime, text, and null-token handling
   through the configured mappings
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest
from d1_support import (
    ABSENT,
    CASE_KEYS,
    ENTITIES,
    FULL_CASES,
    INGESTED_AT,
    RUN_ID,
    SOURCES,
    assert_error,
    business,
    case_id,
    full_case,
    utc,
    with_value,
)

from app.normalization import (
    CoercionError,
    ErrorCode,
    FieldMappingError,
    IdentifierError,
    canonical_id,
    normalize,
)
from app.normalization.contract import BUSINESS_FIELDS, CANONICAL_SCHEMAS, E1_RESOLVED_FIELDS
from app.schemas.source import (
    CsvCustomerSource,
    CsvDealSource,
    CsvDocumentSource,
    CsvEmployeeSource,
    CsvOrganizationSource,
    CsvProjectSource,
    CsvSupportTicketSource,
    OdooCustomerSource,
    OdooDealSource,
    OdooDocumentSource,
    OdooEmployeeSource,
    OdooOrganizationSource,
    OdooProjectSource,
    OdooSupportTicketSource,
    RestCustomerSource,
    RestDealSource,
    RestDocumentSource,
    RestEmployeeSource,
    RestOrganizationSource,
    RestProjectSource,
    RestSupportTicketSource,
)

SOURCE_SCHEMAS = {
    ("csv_demo", "organizations"): CsvOrganizationSource,
    ("csv_demo", "employees"): CsvEmployeeSource,
    ("csv_demo", "customers"): CsvCustomerSource,
    ("csv_demo", "deals"): CsvDealSource,
    ("csv_demo", "projects"): CsvProjectSource,
    ("csv_demo", "support_tickets"): CsvSupportTicketSource,
    ("csv_demo", "documents"): CsvDocumentSource,
    ("odoo_mock", "organizations"): OdooOrganizationSource,
    ("odoo_mock", "employees"): OdooEmployeeSource,
    ("odoo_mock", "customers"): OdooCustomerSource,
    ("odoo_mock", "deals"): OdooDealSource,
    ("odoo_mock", "projects"): OdooProjectSource,
    ("odoo_mock", "support_tickets"): OdooSupportTicketSource,
    ("odoo_mock", "documents"): OdooDocumentSource,
    ("rest_mock", "organizations"): RestOrganizationSource,
    ("rest_mock", "employees"): RestEmployeeSource,
    ("rest_mock", "customers"): RestCustomerSource,
    ("rest_mock", "deals"): RestDealSource,
    ("rest_mock", "projects"): RestProjectSource,
    ("rest_mock", "support_tickets"): RestSupportTicketSource,
    ("rest_mock", "documents"): RestDocumentSource,
}

SOURCE_ID_FIELD = {
    ("csv_demo", "organizations"): "organization_id",
    ("csv_demo", "employees"): "employee_id",
    ("csv_demo", "customers"): "customer_id",
    ("csv_demo", "deals"): "deal_id",
    ("csv_demo", "projects"): "project_id",
    ("csv_demo", "support_tickets"): "ticket_id",
    ("csv_demo", "documents"): "document_id",
    **{("odoo_mock", entity): "id" for entity in ENTITIES},
    **{("rest_mock", entity): "id" for entity in ENTITIES},
}


def _normalize(source: str, entity: str, record: object):
    return normalize(source, entity, record, RUN_ID, INGESTED_AT)


def _error(source: str, entity: str, record: object):
    with pytest.raises(Exception) as excinfo:
        _normalize(source, entity, record)
    return excinfo.value


# ---------------------------------------------------------------------------
# A. Field-level mapping for all 21 combinations
# ---------------------------------------------------------------------------


def test_cases_cover_all_21_combinations():
    assert set(FULL_CASES) == {(s, e) for s in SOURCES for e in ENTITIES}
    assert len(FULL_CASES) == 21


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_full_record_maps_every_business_field(source, entity):
    record, expected = full_case(source, entity)
    obj = _normalize(source, entity, record)

    assert type(obj) is CANONICAL_SCHEMAS[entity]
    assert obj.source_system == source
    assert obj.source_entity == entity
    assert obj.source_id == expected["source_id"]
    assert obj.id == canonical_id(source, entity, expected["source_id"])
    assert obj.source_updated_at == expected["source_updated_at"]
    assert business(obj) == expected["fields"]
    for fk_field in E1_RESOLVED_FIELDS[entity]:
        assert getattr(obj, fk_field) is None


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_fixture_is_discriminating(source, entity):
    """Every field is populated and same-typed values differ, so wiring errors surface."""
    _, expected = full_case(source, entity)
    fields = expected["fields"]
    assert set(fields) == set(BUSINESS_FIELDS[entity])
    assert all(value is not None for value in fields.values())
    by_type: dict[type, list] = defaultdict(list)
    for value in fields.values():
        by_type[type(value)].append(value)
    for value_type, values in by_type.items():
        if value_type is not bool:
            assert len(values) == len(set(values)), (value_type, values)


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_fixture_is_a_valid_b3_source_payload(source, entity):
    record, _ = full_case(source, entity)
    SOURCE_SCHEMAS[(source, entity)].model_validate(record)


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_decimal_fields_use_canonical_scale(source, entity):
    record, _ = full_case(source, entity)
    obj = _normalize(source, entity, record)
    for name in BUSINESS_FIELDS[entity]:
        value = getattr(obj, name)
        if isinstance(value, Decimal):
            assert value.as_tuple().exponent == -2, (name, value)


def test_unmapped_source_fields_are_ignored():
    record, expected = full_case("rest_mock", "support_tickets")
    record["name"] = "stray"
    record["unexpected"] = {"nested": True}
    assert business(_normalize("rest_mock", "support_tickets", record)) == expected["fields"]


def test_missing_optional_fields_become_none():
    obj = _normalize("csv_demo", "customers",
                     {"customer_id": "C1", "customer_name": "Minimal", "status": "active"})
    assert business(obj) == {
        "name": "Minimal", "email": None, "segment": None, "industry": None,
        "status": "active", "owner_source_id": None, "created_at": None, "is_active": True,
    }


# ---------------------------------------------------------------------------
# B. is_active and status derivation
# ---------------------------------------------------------------------------

IS_ACTIVE_SOURCE = {
    ("csv_demo", "employees"): ("is_active", "false", "true"),
    ("csv_demo", "customers"): ("status", "inactive", "active"),
    ("csv_demo", "deals"): ("is_active", "false", "true"),
    ("csv_demo", "projects"): ("is_active", "false", "true"),
    ("odoo_mock", "employees"): ("active", False, True),
    ("odoo_mock", "customers"): ("active", False, True),
    ("odoo_mock", "deals"): ("active", False, True),
    ("odoo_mock", "projects"): ("active", False, True),
    ("rest_mock", "employees"): ("isActive", False, True),
    ("rest_mock", "customers"): ("isActive", False, True),
    ("rest_mock", "deals"): ("isActive", False, True),
    ("rest_mock", "projects"): ("isActive", False, True),
}


@pytest.mark.parametrize("expected", [False, True])
@pytest.mark.parametrize(("source", "entity"), sorted(IS_ACTIVE_SOURCE), ids=case_id)
def test_is_active_follows_source_value(source, entity, expected):
    field, false_value, true_value = IS_ACTIVE_SOURCE[(source, entity)]
    record, _ = full_case(source, entity)
    record[field] = true_value if expected else false_value
    assert _normalize(source, entity, record).is_active is expected


@pytest.mark.parametrize(("status", "expected"), [
    ("active", True), ("inactive", False), (" Inactive ", False), ("ACTIVE", True),
])
def test_csv_customer_is_active_derives_from_status(status, expected):
    record, _ = full_case("csv_demo", "customers")
    obj = _normalize("csv_demo", "customers", with_value(record, "status", status))
    assert obj.is_active is expected
    assert obj.status == ("active" if expected else "inactive")


@pytest.mark.parametrize("value", ["true", "TRUE", " Yes ", "1"])
def test_csv_boolean_true_representations(value):
    record, _ = full_case("csv_demo", "deals")
    assert _normalize("csv_demo", "deals", with_value(record, "is_active", value)).is_active is True


@pytest.mark.parametrize("value", ["false", "FALSE", " no ", "0"])
def test_csv_boolean_false_representations(value):
    record, _ = full_case("csv_demo", "projects")
    obj = _normalize("csv_demo", "projects", with_value(record, "is_active", value))
    assert obj.is_active is False


@pytest.mark.parametrize("entity", ["organizations", "employees", "customers"])
@pytest.mark.parametrize(("active", "status"), [
    (True, "active"), (False, "inactive"), (1, "active"), (0, "inactive"), ("false", "inactive"),
])
def test_odoo_status_derives_from_active_flag(entity, active, status):
    record, _ = full_case("odoo_mock", entity)
    assert _normalize("odoo_mock", entity, with_value(record, "active", active)).status == status


def test_odoo_organization_status_is_none_without_active_flag():
    record, _ = full_case("odoo_mock", "organizations")
    assert _normalize("odoo_mock", "organizations", with_value(record, "active", None)).status is None


MISSING_IS_ACTIVE = [
    ("csv_demo", "employees", "is_active", ABSENT),
    ("csv_demo", "employees", "is_active", ""),
    ("csv_demo", "deals", "is_active", "  "),
    ("csv_demo", "projects", "is_active", "N/A"),
    ("csv_demo", "customers", "status", ""),
    ("csv_demo", "customers", "status", ABSENT),
    ("odoo_mock", "employees", "active", None),
    ("odoo_mock", "customers", "active", ABSENT),
    ("odoo_mock", "deals", "active", None),
    ("odoo_mock", "projects", "active", ABSENT),
    ("rest_mock", "employees", "isActive", ""),
    ("rest_mock", "customers", "isActive", None),
    ("rest_mock", "deals", "isActive", ABSENT),
    ("rest_mock", "projects", "isActive", None),
]


@pytest.mark.parametrize(("source", "entity", "field", "value"), MISSING_IS_ACTIVE)
def test_missing_is_active_is_rejected_deterministically(source, entity, field, value):
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, field, value))
    assert_error(exc, FieldMappingError, ErrorCode.REQUIRED_FIELD_MISSING,
                 source_system=source, entity_type=entity,
                 source_id=expected["source_id"], field_name="is_active")


@pytest.mark.parametrize(("source", "entity", "field", "value"), [
    ("csv_demo", "deals", "is_active", "maybe"),
    ("csv_demo", "employees", "is_active", "active"),
    ("odoo_mock", "deals", "active", 2),
    ("odoo_mock", "projects", "active", 1.0),
    ("rest_mock", "projects", "isActive", "enabled"),
    ("rest_mock", "customers", "isActive", [True]),
])
def test_invalid_boolean_is_rejected(source, entity, field, value):
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, field, value))
    assert_error(exc, CoercionError, ErrorCode.INVALID_BOOLEAN, source_system=source,
                 entity_type=entity, source_id=expected["source_id"], field_name="is_active")
    assert exc.raw_value == value


# ---------------------------------------------------------------------------
# C. Required names
# ---------------------------------------------------------------------------

NAME_FIELD = {
    ("csv_demo", "organizations"): "organization_name",
    ("csv_demo", "employees"): "employee_name",
    ("csv_demo", "customers"): "customer_name",
    ("csv_demo", "deals"): "deal_name",
    ("csv_demo", "projects"): "project_name",
    **{(source, entity): "name" for source in ("odoo_mock", "rest_mock")
       for entity in ("organizations", "employees", "customers", "deals", "projects")},
}


def test_name_is_required_exactly_for_named_entities():
    named = {entity for (_, entity) in NAME_FIELD}
    for entity, schema in CANONICAL_SCHEMAS.items():
        has_required_name = "name" in schema.model_fields and schema.model_fields["name"].is_required()
        assert has_required_name is (entity in named)


@pytest.mark.parametrize("value", [ABSENT, None, "", "   ", "N/A", "null", " - "])
@pytest.mark.parametrize(("source", "entity"), sorted(NAME_FIELD), ids=case_id)
def test_missing_required_name_is_rejected(source, entity, value):
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, NAME_FIELD[(source, entity)], value))
    assert_error(exc, FieldMappingError, ErrorCode.REQUIRED_FIELD_MISSING, source_system=source,
                 entity_type=entity, source_id=expected["source_id"], field_name="name")
    assert NAME_FIELD[(source, entity)] in exc.reason


# ---------------------------------------------------------------------------
# D. Source identifiers and relationship keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "1", "42", 1.0, True, False, 0, -7, "abc", [1]])
@pytest.mark.parametrize("entity", ENTITIES)
def test_odoo_rejects_invalid_source_ids(entity, value):
    record, _ = full_case("odoo_mock", entity)
    exc = _error("odoo_mock", entity, with_value(record, "id", value))
    assert_error(exc, IdentifierError, ErrorCode.SOURCE_ID_INVALID, source_system="odoo_mock",
                 entity_type=entity, source_id=None, field_name="source_id")
    assert exc.raw_value == value


@pytest.mark.parametrize("value", [ABSENT, None])
@pytest.mark.parametrize("entity", ENTITIES)
def test_odoo_missing_source_id(entity, value):
    record, _ = full_case("odoo_mock", entity)
    exc = _error("odoo_mock", entity, with_value(record, "id", value))
    assert_error(exc, IdentifierError, ErrorCode.SOURCE_ID_MISSING, source_system="odoo_mock",
                 entity_type=entity, source_id=None, field_name="source_id")


@pytest.mark.parametrize("entity", ENTITIES)
def test_odoo_integer_source_id_becomes_canonical_string(entity):
    record, _ = full_case("odoo_mock", entity)
    obj = _normalize("odoo_mock", entity, with_value(record, "id", 907))
    assert obj.source_id == "907"
    assert obj.id == canonical_id("odoo_mock", entity, "907")


@pytest.mark.parametrize("value", [ABSENT, None, "", "   "])
@pytest.mark.parametrize(("source", "entity"),
                         [k for k in CASE_KEYS if k[0] != "odoo_mock"], ids=case_id)
def test_string_sources_reject_missing_source_ids(source, entity, value):
    record, _ = full_case(source, entity)
    exc = _error(source, entity, with_value(record, SOURCE_ID_FIELD[(source, entity)], value))
    assert_error(exc, IdentifierError, ErrorCode.SOURCE_ID_MISSING, source_system=source,
                 entity_type=entity, source_id=None, field_name="source_id")


@pytest.mark.parametrize("value", [5, 5.0, True])
@pytest.mark.parametrize(("source", "entity"),
                         [k for k in CASE_KEYS if k[0] != "odoo_mock"], ids=case_id)
def test_string_sources_reject_non_string_source_ids(source, entity, value):
    record, _ = full_case(source, entity)
    exc = _error(source, entity, with_value(record, SOURCE_ID_FIELD[(source, entity)], value))
    assert_error(exc, IdentifierError, ErrorCode.SOURCE_ID_INVALID, source_system=source,
                 entity_type=entity, source_id=None, field_name="source_id")


def test_string_source_id_is_trimmed():
    record, _ = full_case("rest_mock", "customers")
    obj = _normalize("rest_mock", "customers", with_value(record, "id", "  CUST-9 "))
    assert obj.source_id == "CUST-9"
    assert obj.id == canonical_id("rest_mock", "customers", "CUST-9")


RELATIONSHIP_KEYS = [
    ("csv_demo", "employees", "manager_id", "manager_source_id"),
    ("csv_demo", "customers", "account_owner_id", "owner_source_id"),
    ("csv_demo", "deals", "customer_id", "customer_source_id"),
    ("csv_demo", "deals", "owner_id", "owner_source_id"),
    ("csv_demo", "projects", "customer_id", "customer_source_id"),
    ("csv_demo", "projects", "owner_id", "owner_source_id"),
    ("csv_demo", "support_tickets", "customer_id", "customer_source_id"),
    ("csv_demo", "support_tickets", "assignee_id", "assignee_source_id"),
    ("csv_demo", "documents", "owner_id", "owner_source_id"),
    ("odoo_mock", "employees", "parent_id", "manager_source_id"),
    ("odoo_mock", "customers", "user_id", "owner_source_id"),
    ("odoo_mock", "deals", "partner_id", "customer_source_id"),
    ("odoo_mock", "deals", "user_id", "owner_source_id"),
    ("odoo_mock", "projects", "partner_id", "customer_source_id"),
    ("odoo_mock", "projects", "user_id", "owner_source_id"),
    ("odoo_mock", "support_tickets", "partner_id", "customer_source_id"),
    ("odoo_mock", "support_tickets", "user_id", "assignee_source_id"),
    ("odoo_mock", "documents", "owner_id", "owner_source_id"),
    ("rest_mock", "employees", "managerId", "manager_source_id"),
    ("rest_mock", "customers", "ownerId", "owner_source_id"),
    ("rest_mock", "deals", "customerId", "customer_source_id"),
    ("rest_mock", "deals", "ownerId", "owner_source_id"),
    ("rest_mock", "projects", "customerId", "customer_source_id"),
    ("rest_mock", "projects", "ownerId", "owner_source_id"),
    ("rest_mock", "support_tickets", "customerId", "customer_source_id"),
    ("rest_mock", "support_tickets", "assigneeId", "assignee_source_id"),
    ("rest_mock", "documents", "ownerId", "owner_source_id"),
]


def _key_id(param):
    return f"{param[0]}-{param[1]}-{param[3]}"


def test_relationship_key_table_covers_every_source_key_field():
    from app.normalization import default_config

    config = default_config()
    expected = {
        (source, entity, name)
        for source in SOURCES for entity in ENTITIES
        for name, spec in config.fields[entity].items() if spec.kind == "source_key"
    }
    assert {(s, e, c) for s, e, _, c in RELATIONSHIP_KEYS} == expected


@pytest.mark.parametrize("key", RELATIONSHIP_KEYS, ids=_key_id)
def test_relationship_key_is_preserved(key):
    source, entity, source_field, canonical_field = key
    record, _ = full_case(source, entity)
    value = 8421 if source == "odoo_mock" else "  REF-8421 "
    obj = _normalize(source, entity, with_value(record, source_field, value))
    assert getattr(obj, canonical_field) == ("8421" if source == "odoo_mock" else "REF-8421")


@pytest.mark.parametrize("key", RELATIONSHIP_KEYS, ids=_key_id)
def test_missing_relationship_key_becomes_none(key):
    source, entity, source_field, canonical_field = key
    record, _ = full_case(source, entity)
    for value in ([None, ABSENT] if source == "odoo_mock" else [None, ABSENT, "", "   "]):
        obj = _normalize(source, entity, with_value(record, source_field, value))
        assert getattr(obj, canonical_field) is None


@pytest.mark.parametrize("key", RELATIONSHIP_KEYS, ids=_key_id)
def test_invalid_relationship_key_is_rejected(key):
    source, entity, source_field, canonical_field = key
    record, expected = full_case(source, entity)
    invalid = ["", "12", 1.5, True, 0, -3] if source == "odoo_mock" else [12, 1.5, True]
    for value in invalid:
        exc = _error(source, entity, with_value(record, source_field, value))
        assert_error(exc, IdentifierError, ErrorCode.RELATIONSHIP_KEY_INVALID,
                     source_system=source, entity_type=entity,
                     source_id=expected["source_id"], field_name=canonical_field)


# ---------------------------------------------------------------------------
# E. Enum, currency, decimal, date/time, text, and null tokens via mappings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "field"), [
    ("csv_demo", "status"), ("odoo_mock", "stage_id"), ("rest_mock", "status"),
])
@pytest.mark.parametrize("label", ["In Progress", "in-progress", " IN_PROGRESS ", "in   progress"])
def test_project_status_labels_normalize(source, field, label):
    record, _ = full_case(source, "projects")
    assert _normalize(source, "projects", with_value(record, field, label)).status == "in_progress"


@pytest.mark.parametrize(("source", "entity", "field", "canonical", "value"), [
    ("csv_demo", "projects", "status", "status", "stalled"),
    ("rest_mock", "projects", "status", "status", "active"),
    ("csv_demo", "deals", "stage", "stage", "closed_won"),
    ("odoo_mock", "deals", "stage_id", "stage", "Proposition"),
    ("rest_mock", "support_tickets", "priority", "priority", "p1"),
    ("odoo_mock", "support_tickets", "stage_id", "status", "archived"),
    ("csv_demo", "customers", "status", "status", "churned"),
    ("rest_mock", "organizations", "status", "status", "dormant"),
    ("csv_demo", "employees", "status", "status", "on leave"),
])
def test_unknown_enum_values_are_rejected(source, entity, field, canonical, value):
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, field, value))
    assert_error(exc, CoercionError, ErrorCode.UNKNOWN_ENUM_VALUE, source_system=source,
                 entity_type=entity, source_id=expected["source_id"], field_name=canonical)


def test_optional_enum_null_token_becomes_none():
    record, _ = full_case("rest_mock", "support_tickets")
    assert _normalize("rest_mock", "support_tickets", with_value(record, "priority", "N/A")).priority is None


@pytest.mark.parametrize(("source", "field", "value", "expected"), [
    ("csv_demo", "currency", " usd ", "USD"),
    ("csv_demo", "currency", "Usd", "USD"),
    ("csv_demo", "currency", "₹", "INR"),
    ("odoo_mock", "company_currency", "€", "EUR"),
    ("rest_mock", "currency", "£", "GBP"),
    ("rest_mock", "currency", "N/A", None),
])
def test_currency_normalization(source, field, value, expected):
    record, _ = full_case(source, "deals")
    assert _normalize(source, "deals", with_value(record, field, value)).currency == expected


@pytest.mark.parametrize(("value", "code"), [
    ("US$", ErrorCode.INVALID_CURRENCY), ("$", ErrorCode.INVALID_CURRENCY),
    ("XYZ", ErrorCode.INVALID_CURRENCY), ("IN", ErrorCode.INVALID_CURRENCY),
    ("rupees", ErrorCode.INVALID_CURRENCY), (840, ErrorCode.INVALID_TYPE),
])
def test_invalid_currency_is_rejected(value, code):
    record, expected = full_case("odoo_mock", "deals")
    exc = _error("odoo_mock", "deals", with_value(record, "company_currency", value))
    assert_error(exc, CoercionError, code, source_system="odoo_mock", entity_type="deals",
                 source_id=expected["source_id"], field_name="currency")


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("amount", "150000.50", "150000.50"),
    ("amount", "150000.500", "150000.50"),
    ("amount", "9999999999999.99", "9999999999999.99"),
    ("amount", "-9999999999999.99", "-9999999999999.99"),
    ("amount", "-0.00", "0.00"),
    ("amount", "0", "0.00"),
    ("probability", "0", "0.00"),
    ("probability", "100", "100.00"),
    ("probability", "99.99", "99.99"),
])
def test_decimal_boundaries_accepted(field, value, expected):
    record, _ = full_case("csv_demo", "deals")
    obj = _normalize("csv_demo", "deals", with_value(record, field, value))
    assert str(getattr(obj, field)) == expected


@pytest.mark.parametrize(("source", "field", "canonical", "value", "code"), [
    ("csv_demo", "amount", "amount", "150000.505", ErrorCode.DECIMAL_SCALE_EXCEEDED),
    ("csv_demo", "amount", "amount", "10000000000000.00", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("csv_demo", "amount", "amount", "-10000000000000", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("csv_demo", "probability", "probability", "100.01", ErrorCode.DECIMAL_OUT_OF_RANGE),
    ("csv_demo", "probability", "probability", "-0.01", ErrorCode.DECIMAL_OUT_OF_RANGE),
    ("csv_demo", "probability", "probability", "999.99", ErrorCode.DECIMAL_OUT_OF_RANGE),
    ("csv_demo", "probability", "probability", "1000", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("csv_demo", "probability", "probability", "75.005", ErrorCode.DECIMAL_SCALE_EXCEEDED),
    ("csv_demo", "amount", "amount", "1,000.00", ErrorCode.INVALID_DECIMAL),
    ("csv_demo", "amount", "amount", "1e3", ErrorCode.INVALID_DECIMAL),
    ("csv_demo", "amount", "amount", "NaN", ErrorCode.INVALID_DECIMAL),
    ("csv_demo", "amount", "amount", "₹50000", ErrorCode.INVALID_DECIMAL),
    ("odoo_mock", "expected_revenue", "amount", 0.1 + 0.2, ErrorCode.DECIMAL_SCALE_EXCEEDED),
    ("odoo_mock", "expected_revenue", "amount", 1e20, ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("odoo_mock", "expected_revenue", "amount", float("inf"), ErrorCode.INVALID_DECIMAL),
    ("odoo_mock", "expected_revenue", "amount", True, ErrorCode.INVALID_TYPE),
    ("rest_mock", "budget", "budget", 120000.001, ErrorCode.DECIMAL_SCALE_EXCEEDED),
])
def test_decimal_violations_are_rejected_not_rounded(source, field, canonical, value, code):
    entity = "projects" if canonical == "budget" else "deals"
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, field, value))
    assert_error(exc, CoercionError, code, source_system=source, entity_type=entity,
                 source_id=expected["source_id"], field_name=canonical)


@pytest.mark.parametrize("value", [
    "15/01/2026", "2026-13-01", "2026-02-30", "20260115", "2026-W03-1", "2026-01-15T10:00:00",
])
def test_invalid_dates_are_rejected(value):
    record, expected = full_case("csv_demo", "employees")
    exc = _error("csv_demo", "employees", with_value(record, "hire_date", value))
    assert_error(exc, CoercionError, ErrorCode.INVALID_DATE, source_system="csv_demo",
                 entity_type="employees", source_id=expected["source_id"], field_name="hire_date")


@pytest.mark.parametrize(("source", "field", "canonical", "value", "code"), [
    ("rest_mock", "createdAt", "created_at", "2026-01-01T12:00:00", ErrorCode.NAIVE_DATETIME_REJECTED),
    ("rest_mock", "createdAt", "created_at", "2026-01-01", ErrorCode.NAIVE_DATETIME_REJECTED),
    ("rest_mock", "createdAt", "created_at", "01/01/2026 12:00", ErrorCode.INVALID_DATETIME),
    ("odoo_mock", "create_date", "created_at", "2026-01-01T12:00:00Z", ErrorCode.INVALID_DATETIME),
    ("csv_demo", "created_date", "created_at", "2026-02-30", ErrorCode.INVALID_DATETIME),
])
def test_invalid_datetimes_are_rejected(source, field, canonical, value, code):
    record, expected = full_case(source, "customers")
    exc = _error(source, "customers", with_value(record, field, value))
    assert_error(exc, CoercionError, code, source_system=source, entity_type="customers",
                 source_id=expected["source_id"], field_name=canonical)


@pytest.mark.parametrize(("source", "field", "value"), [
    ("csv_demo", "created_date", "2026-01-01 12:00:00"),
    ("odoo_mock", "create_date", "2026-01-01 12:00:00"),
    ("rest_mock", "createdAt", "2026-01-01T12:00:00Z"),
    ("rest_mock", "createdAt", "2026-01-01T17:30:00+05:30"),
    ("rest_mock", "createdAt", "2026-01-01T07:00:00-05:00"),
    ("csv_demo", "created_date", "2026-01-01T13:00:00+01:00"),
])
def test_equivalent_timestamps_converge_across_sources(source, field, value):
    record, _ = full_case(source, "customers")
    created_at = _normalize(source, "customers", with_value(record, field, value)).created_at
    assert created_at == utc(2026, 1, 1, 12)
    assert created_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(("source", "field"), [
    ("csv_demo", "description"), ("odoo_mock", "description"), ("rest_mock", "description"),
])
def test_free_text_is_preserved_consistently(source, field):
    record, _ = full_case(source, "support_tickets")
    for value, expected in [("N/A", "N/A"), ("  indented\n", "  indented\n"),
                            ("", None), ("  \n\t", None), (None, None)]:
        obj = _normalize(source, "support_tickets", with_value(record, field, value))
        assert obj.description == expected


@pytest.mark.parametrize(("source", "field"), [
    ("csv_demo", "body_text"), ("odoo_mock", "datas"), ("rest_mock", "bodyText"),
])
def test_empty_document_body_becomes_none_for_every_source(source, field):
    record, _ = full_case(source, "documents")
    assert _normalize(source, "documents", with_value(record, field, "")).body_text is None


@pytest.mark.parametrize(("value", "expected"), [
    ("NA", "NA"), ("None", "None"), ("nil", "nil"), ("N/A", None), ("null", None),
    (" - ", None), ("  Namibia ", "Namibia"),
])
def test_string_null_tokens_follow_configuration(value, expected):
    record, _ = full_case("rest_mock", "organizations")
    assert _normalize("rest_mock", "organizations", with_value(record, "country", value)).country == expected


@pytest.mark.parametrize(("source", "entity", "field", "canonical", "value"), [
    ("rest_mock", "customers", "name", "name", 123),
    ("odoo_mock", "organizations", "industry_id", "industry", [7, "Technology"]),
    ("csv_demo", "support_tickets", "description", "description", 42),
    ("rest_mock", "employees", "email", "email", ["bob@acme.example"]),
])
def test_non_string_values_in_text_fields_are_rejected(source, entity, field, canonical, value):
    record, expected = full_case(source, entity)
    exc = _error(source, entity, with_value(record, field, value))
    assert_error(exc, CoercionError, ErrorCode.INVALID_TYPE, source_system=source,
                 entity_type=entity, source_id=expected["source_id"], field_name=canonical)


@pytest.mark.parametrize(("source", "entity", "field"), [
    ("csv_demo", "customers", "updated_date"),
    ("odoo_mock", "deals", "write_date"),
    ("rest_mock", "projects", "updatedAt"),
])
def test_source_updated_at_only_extracted_where_mapped(source, entity, field):
    record, _ = full_case(source, entity)
    record[field] = "2026-01-01T00:00:00Z"
    assert _normalize(source, entity, record).source_updated_at is None


@pytest.mark.parametrize(("source", "field"), [
    ("csv_demo", "updated_date"), ("odoo_mock", "write_date"), ("rest_mock", "updatedAt"),
])
def test_document_source_updated_at_absent_becomes_none(source, field):
    record, _ = full_case(source, "documents")
    obj = _normalize(source, "documents", with_value(record, field, ABSENT))
    assert obj.source_updated_at is None
    assert obj.updated_at is None
