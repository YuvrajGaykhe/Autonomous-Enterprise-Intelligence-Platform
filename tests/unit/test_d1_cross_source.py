"""
D1 cross-source convergence tests.

The same logical business record is represented three ways:
    C2 CsvConnector  -> CSV row (all strings, snake_case)
    C3 /odoo/...     -> Odoo payload (int IDs, Odoo field names, naive UTC)
    C3 /rest/...     -> REST payload (str IDs, camelCase, ISO 8601 with Z)

These tests prove that D1 maps every representation to the same canonical
business content, while never merging source identities. Fixtures are
verified to be exactly what C3's transformers produce, and the full demo
dataset is swept through C2 + C3 representations.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from d1_support import ENTITIES, INGESTED_AT, RUN_ID, SOURCES, business, utc

from app.connectors.csv import CsvConnector, CsvConnectorConfig
from app.normalization import default_config, normalize, normalize_batch
from app.normalization.contract import BUSINESS_FIELDS
from app.schemas.source import CsvCustomerSource

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "docker"))
import mock_source  # noqa: E402

HANDBOOK_URI = "https://internal.acme.example/docs/handbook.pdf"

# One logical record per entity, as a C2 CSV row.
CSV_ROWS = {
    "organizations": {"organization_id": "ORG-002", "organization_name": "GlobalTech Solutions",
                      "industry": "Technology", "country": "United States", "status": "active"},
    "employees": {"employee_id": "EMP-003", "employee_name": "Carol Analyst",
                  "email_address": "carol@globaltech.example", "department": "Analytics",
                  "title": "Data Analyst", "manager_id": "EMP-002", "status": "active",
                  "hire_date": "2025-01-10", "is_active": "true", "organization_id": "ORG-002"},
    "customers": {"customer_id": "CUST-001", "customer_name": "Acme Industries",
                  "email_address": "contact@acme-ind.example", "customer_segment": "Enterprise",
                  "industry_name": "Manufacturing", "account_owner_id": "EMP-002",
                  "status": "active", "created_date": "2025-01-15"},
    "deals": {"deal_id": "DEAL-001", "deal_name": "Acme Platform Deal", "customer_id": "CUST-001",
              "owner_id": "EMP-002", "stage": "negotiation", "amount": "150000.50",
              "currency": "INR", "probability": "75.0", "expected_close_date": "2026-12-31",
              "is_active": "true"},
    "projects": {"project_id": "PROJ-001", "project_name": "Platform Migration",
                 "customer_id": "CUST-001", "owner_id": "EMP-001", "status": "in_progress",
                 "start_date": "2026-01-01", "end_date": "2026-12-31", "budget": "500000.00",
                 "is_active": "true"},
    "support_tickets": {"ticket_id": "TKT-002", "customer_id": "CUST-002",
                        "assignee_id": "EMP-003", "priority": "medium", "status": "resolved",
                        "category": "billing", "subject": "Invoice discrepancy Q3",
                        "description": "Invoice totals do not match the agreed contract.",
                        "created_date": "2026-08-15", "resolved_date": "2026-08-20"},
    "documents": {"document_id": "DOC-001", "title": "Employee Handbook 2026",
                  "document_type": "policy", "body_text": "Section 1: Code of conduct.",
                  "source_uri": HANDBOOK_URI, "owner_id": "EMP-001",
                  "created_date": "2026-01-01", "updated_date": "2026-06-15"},
}

# The same records as C3 serves them.
ODOO_PAYLOADS = {
    "organizations": {"id": 2, "name": "GlobalTech Solutions", "industry_id": "Technology",
                      "country_id": "United States", "active": True},
    "employees": {"id": 3, "name": "Carol Analyst", "work_email": "carol@globaltech.example",
                  "department_id": "Analytics", "job_title": "Data Analyst", "parent_id": 2,
                  "active": True, "x_hire_date": "2025-01-10", "company_id": 2},
    "customers": {"id": 1, "name": "Acme Industries", "email": "contact@acme-ind.example",
                  "x_studio_segment": "Enterprise", "industry_id": "Manufacturing", "user_id": 2,
                  "active": True, "create_date": "2025-01-15 00:00:00", "customer_rank": 1},
    "deals": {"id": 1, "name": "Acme Platform Deal", "partner_id": 1, "user_id": 2,
              "stage_id": "negotiation", "expected_revenue": 150000.5, "company_currency": "INR",
              "probability": 75.0, "date_deadline": "2026-12-31", "active": True},
    "projects": {"id": 1, "name": "Platform Migration", "partner_id": 1, "user_id": 1,
                 "stage_id": "in_progress", "date_start": "2026-01-01", "date": "2026-12-31",
                 "x_budget": 500000.0, "active": True},
    "support_tickets": {"id": 2, "partner_id": 2, "user_id": 3, "priority": "medium",
                        "stage_id": "resolved", "category_id": "billing",
                        "name": "Invoice discrepancy Q3",
                        "description": "Invoice totals do not match the agreed contract.",
                        "create_date": "2026-08-15 00:00:00", "close_date": "2026-08-20 00:00:00"},
    "documents": {"id": 1, "name": "Employee Handbook 2026", "type": "policy",
                  "datas": "Section 1: Code of conduct.", "url": HANDBOOK_URI, "owner_id": 1,
                  "create_date": "2026-01-01 00:00:00", "write_date": "2026-06-15 00:00:00"},
}

REST_PAYLOADS = {
    "organizations": {"id": "ORG-002", "name": "GlobalTech Solutions", "industry": "Technology",
                      "country": "United States", "status": "active"},
    "employees": {"id": "EMP-003", "name": "Carol Analyst", "email": "carol@globaltech.example",
                  "department": "Analytics", "title": "Data Analyst", "managerId": "EMP-002",
                  "status": "active", "hireDate": "2025-01-10", "isActive": True,
                  "organizationId": "ORG-002"},
    "customers": {"id": "CUST-001", "name": "Acme Industries", "email": "contact@acme-ind.example",
                  "segment": "Enterprise", "industry": "Manufacturing", "ownerId": "EMP-002",
                  "status": "active", "createdAt": "2025-01-15T00:00:00Z", "isActive": True},
    "deals": {"id": "DEAL-001", "name": "Acme Platform Deal", "customerId": "CUST-001",
              "ownerId": "EMP-002", "stage": "negotiation", "amount": 150000.5, "currency": "INR",
              "probability": 75.0, "expectedCloseDate": "2026-12-31", "isActive": True},
    "projects": {"id": "PROJ-001", "name": "Platform Migration", "customerId": "CUST-001",
                 "ownerId": "EMP-001", "status": "in_progress", "startDate": "2026-01-01",
                 "endDate": "2026-12-31", "budget": 500000.0, "isActive": True},
    "support_tickets": {"id": "TKT-002", "customerId": "CUST-002", "assigneeId": "EMP-003",
                        "priority": "medium", "status": "resolved", "category": "billing",
                        "subject": "Invoice discrepancy Q3",
                        "description": "Invoice totals do not match the agreed contract.",
                        "createdAt": "2026-08-15T00:00:00Z", "resolvedAt": "2026-08-20T00:00:00Z"},
    "documents": {"id": "DOC-001", "title": "Employee Handbook 2026", "documentType": "policy",
                  "bodyText": "Section 1: Code of conduct.", "sourceUri": HANDBOOK_URI,
                  "ownerId": "EMP-001", "createdAt": "2026-01-01T00:00:00Z",
                  "updatedAt": "2026-06-15T00:00:00Z"},
}

# Expected converged canonical business content (relationship keys excluded).
CONVERGED = {
    "organizations": {"name": "GlobalTech Solutions", "industry": "Technology",
                      "country": "United States", "status": "active"},
    "employees": {"name": "Carol Analyst", "email": "carol@globaltech.example",
                  "department": "Analytics", "title": "Data Analyst", "status": "active",
                  "hire_date": utc(2025, 1, 10).date(), "is_active": True},
    "customers": {"name": "Acme Industries", "email": "contact@acme-ind.example",
                  "segment": "Enterprise", "industry": "Manufacturing", "status": "active",
                  "created_at": utc(2025, 1, 15), "is_active": True},
    "deals": {"name": "Acme Platform Deal", "stage": "negotiation", "amount": Decimal("150000.50"),
              "currency": "INR", "probability": Decimal("75.00"),
              "expected_close_date": utc(2026, 12, 31).date(), "is_active": True},
    "projects": {"name": "Platform Migration", "status": "in_progress",
                 "start_date": utc(2026, 1, 1).date(), "end_date": utc(2026, 12, 31).date(),
                 "budget": Decimal("500000.00"), "is_active": True},
    "support_tickets": {"subject": "Invoice discrepancy Q3",
                        "description": "Invoice totals do not match the agreed contract.",
                        "priority": "medium", "status": "resolved", "category": "billing",
                        "created_at": utc(2026, 8, 15), "resolved_at": utc(2026, 8, 20)},
    "documents": {"title": "Employee Handbook 2026", "document_type": "policy",
                  "body_text": "Section 1: Code of conduct.", "source_uri": HANDBOOK_URI,
                  "created_at": utc(2026, 1, 1), "updated_at": utc(2026, 6, 15)},
}

PAYLOADS = {"csv_demo": CSV_ROWS, "odoo_mock": ODOO_PAYLOADS, "rest_mock": REST_PAYLOADS}


def _key_fields(entity: str) -> list[str]:
    return [name for name, spec in default_config().fields[entity].items()
            if spec.kind == "source_key"]


def _expected_key(source: str, csv_key: str | None) -> str | None:
    """C3 contract: Odoo references are the numeric part; REST keeps CSV keys."""
    if csv_key is None or source != "odoo_mock":
        return csv_key
    return str(mock_source._to_int(csv_key))


def _normalize_all(entity: str) -> dict:
    return {source: normalize(source, entity, PAYLOADS[source][entity], RUN_ID, INGESTED_AT)
            for source in SOURCES}


# ---------------------------------------------------------------------------
# Fixture fidelity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", ENTITIES)
def test_fixtures_are_exact_c3_output(entity):
    _, odoo_transform, rest_transform = mock_source.ENTITY_CONFIG[entity]
    assert odoo_transform(CSV_ROWS[entity]) == ODOO_PAYLOADS[entity]
    assert rest_transform(CSV_ROWS[entity]) == REST_PAYLOADS[entity]


def test_csv_fixture_matches_c2_row_shape():
    CsvCustomerSource.model_validate(CSV_ROWS["customers"])
    assert all(isinstance(value, str) for row in CSV_ROWS.values() for value in row.values())


def test_converged_expectations_cover_all_non_key_business_fields():
    for entity in ENTITIES:
        assert set(CONVERGED[entity]) == set(BUSINESS_FIELDS[entity]) - set(_key_fields(entity))


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entity", ENTITIES)
def test_business_fields_converge(entity):
    keys = _key_fields(entity)
    for source, obj in _normalize_all(entity).items():
        fields = business(obj)
        assert {k: v for k, v in fields.items() if k not in keys} == CONVERGED[entity], source


@pytest.mark.parametrize("entity", ENTITIES)
def test_relationship_keys_follow_each_source_identity_space(entity):
    objs = _normalize_all(entity)
    for key in _key_fields(entity):
        csv_value = getattr(objs["csv_demo"], key)
        assert csv_value is not None
        for source in SOURCES:
            assert getattr(objs[source], key) == _expected_key(source, csv_value), (source, key)


@pytest.mark.parametrize("entity", ENTITIES)
def test_source_identities_are_never_merged(entity):
    objs = _normalize_all(entity)
    assert {obj.source_system for obj in objs.values()} == set(SOURCES)
    assert len({obj.id for obj in objs.values()}) == 3
    csv_id = objs["csv_demo"].source_id
    assert objs["rest_mock"].source_id == csv_id
    assert objs["odoo_mock"].source_id == str(mock_source._to_int(csv_id))
    assert objs["csv_demo"].id != objs["rest_mock"].id


def test_decimal_representation_converges_exactly():
    objs = _normalize_all("deals")
    assert {str(obj.amount) for obj in objs.values()} == {"150000.50"}
    assert {str(obj.probability) for obj in objs.values()} == {"75.00"}
    assert {str(obj.budget) for obj in _normalize_all("projects").values()} == {"500000.00"}


def test_datetimes_converge_to_identical_utc_representation():
    objs = _normalize_all("support_tickets")
    assert {obj.created_at.isoformat() for obj in objs.values()} == {"2026-08-15T00:00:00+00:00"}
    assert all(obj.resolved_at.utcoffset().total_seconds() == 0 for obj in objs.values())


def test_document_source_updated_at_converges():
    objs = _normalize_all("documents")
    assert {obj.source_updated_at for obj in objs.values()} == {utc(2026, 6, 15)}


def test_identical_content_without_relationship_keys_has_identical_hash():
    """Organizations have no source keys, so identical content is one content identity."""
    objs = _normalize_all("organizations")
    assert len({obj.record_hash for obj in objs.values()}) == 1
    assert len({obj.id for obj in objs.values()}) == 3


def test_source_specific_keys_keep_hashes_distinct():
    objs = _normalize_all("deals")
    assert objs["csv_demo"].record_hash == objs["rest_mock"].record_hash
    assert objs["odoo_mock"].record_hash != objs["csv_demo"].record_hash


# ---------------------------------------------------------------------------
# Full demo dataset through C2 and C3 representations
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_payloads():
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    connector = CsvConnector(config, base_path=REPO)
    odoo, rest = mock_source.load_source_data(REPO / "data" / "demo")
    csv_rows = {entity: connector.fetch_entities(entity, page_size=10_000).items
                for entity in ENTITIES}
    return connector.source_name, {"csv_demo": csv_rows, "odoo_mock": odoo, "rest_mock": rest}


@pytest.mark.parametrize("entity", ENTITIES)
def test_demo_dataset_converges_across_sources(demo_payloads, entity):
    csv_source_name, payloads = demo_payloads
    assert csv_source_name == "csv_demo"
    results = {}
    for source in SOURCES:
        ok, failures = normalize_batch(source, entity, payloads[source][entity], RUN_ID, INGESTED_AT)
        assert failures == [], [str(error) for _, error in failures]
        results[source] = ok
    assert len(results["csv_demo"]) == len(results["odoo_mock"]) == len(results["rest_mock"]) > 0

    odoo_by_id = {obj.source_id: obj for obj in results["odoo_mock"]}
    rest_by_id = {obj.source_id: obj for obj in results["rest_mock"]}
    keys = _key_fields(entity)
    for csv_obj in results["csv_demo"]:
        counterparts = {
            "odoo_mock": odoo_by_id[str(mock_source._to_int(csv_obj.source_id))],
            "rest_mock": rest_by_id[csv_obj.source_id],
        }
        for source, other in counterparts.items():
            for name in BUSINESS_FIELDS[entity]:
                expected = getattr(csv_obj, name)
                if name in keys:
                    expected = _expected_key(source, expected)
                assert getattr(other, name) == expected, (source, csv_obj.source_id, name)
            assert other.source_updated_at == csv_obj.source_updated_at
            assert other.id != csv_obj.id
