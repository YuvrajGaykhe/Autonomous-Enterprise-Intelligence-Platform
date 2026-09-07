"""
B1 ORM Metadata Tests.

These tests verify that all 12 models are correctly registered with
Base.metadata and have the expected table names, column configurations,
and structural properties.

These are pure unit tests — no database connection required.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import inspect

from app.core.database import Base
import app.persistence.models  # noqa: F401 — triggers model registration
from app.persistence.models import (
    ConnectorConfig,
    Customer,
    Deal,
    Document,
    Employee,
    IngestionCursor,
    IngestionError,
    IngestionRun,
    Organization,
    Project,
    SourceRecord,
    SupportTicket,
)


# --- Metadata registration tests ---


EXPECTED_CANONICAL_TABLES = {
    "organizations",
    "employees",
    "customers",
    "deals",
    "projects",
    "support_tickets",
    "documents",
}

EXPECTED_OPERATIONAL_TABLES = {
    "ingestion_runs",
    "ingestion_errors",
    "source_records",
    "connector_configs",
    "ingestion_cursors",
}

ALL_EXPECTED_TABLES = EXPECTED_CANONICAL_TABLES | EXPECTED_OPERATIONAL_TABLES


class TestMetadataRegistration:
    """Verify all models are registered with Base.metadata."""

    def test_all_tables_registered(self):
        registered = set(Base.metadata.tables.keys())
        for table in ALL_EXPECTED_TABLES:
            assert table in registered, f"Table '{table}' not in Base.metadata"

    def test_canonical_table_count(self):
        canonical_found = EXPECTED_CANONICAL_TABLES & set(Base.metadata.tables.keys())
        assert len(canonical_found) == 7

    def test_operational_table_count(self):
        operational_found = EXPECTED_OPERATIONAL_TABLES & set(Base.metadata.tables.keys())
        assert len(operational_found) == 5


# --- Table name tests ---


class TestTableNames:
    """Verify ORM classes map to expected table names."""

    @pytest.mark.parametrize("model_cls, expected_name", [
        (Organization, "organizations"),
        (Employee, "employees"),
        (Customer, "customers"),
        (Deal, "deals"),
        (Project, "projects"),
        (SupportTicket, "support_tickets"),
        (Document, "documents"),
        (IngestionRun, "ingestion_runs"),
        (IngestionError, "ingestion_errors"),
        (SourceRecord, "source_records"),
        (ConnectorConfig, "connector_configs"),
        (IngestionCursor, "ingestion_cursors"),
    ])
    def test_table_name(self, model_cls, expected_name):
        assert model_cls.__tablename__ == expected_name


# --- UUID Primary Key tests ---


CANONICAL_MODELS = [
    Organization, Employee, Customer, Deal, Project, SupportTicket, Document,
]


class TestUUIDPrimaryKeys:
    """Verify canonical entities use UUID primary keys."""

    @pytest.mark.parametrize("model_cls", CANONICAL_MODELS)
    def test_uuid_pk(self, model_cls):
        table = Base.metadata.tables[model_cls.__tablename__]
        pk_cols = [c for c in table.primary_key.columns]
        assert len(pk_cols) == 1
        pk_col = pk_cols[0]
        assert pk_col.name == "id"
        # UUID type check
        assert "UUID" in str(pk_col.type).upper()


# --- Provenance field tests ---


PROVENANCE_FIELDS = {
    "id", "source_system", "source_entity", "source_id",
    "source_updated_at", "ingested_at", "ingestion_run_id", "record_hash",
}


class TestProvenanceFields:
    """Verify all canonical entities have the required provenance fields."""

    @pytest.mark.parametrize("model_cls", CANONICAL_MODELS)
    def test_provenance_columns_exist(self, model_cls):
        table = Base.metadata.tables[model_cls.__tablename__]
        col_names = {c.name for c in table.columns}
        for field in PROVENANCE_FIELDS:
            assert field in col_names, (
                f"Provenance field '{field}' missing from {model_cls.__tablename__}"
            )


# --- is_active placement tests ---


MODELS_WITH_IS_ACTIVE = [Employee, Customer, Deal, Project]
MODELS_WITHOUT_IS_ACTIVE = [Organization, SupportTicket, Document]


class TestIsActivePlacement:
    """is_active must appear only on employees, customers, deals, projects."""

    @pytest.mark.parametrize("model_cls", MODELS_WITH_IS_ACTIVE)
    def test_has_is_active(self, model_cls):
        table = Base.metadata.tables[model_cls.__tablename__]
        col_names = {c.name for c in table.columns}
        assert "is_active" in col_names

    @pytest.mark.parametrize("model_cls", MODELS_WITHOUT_IS_ACTIVE)
    def test_does_not_have_is_active(self, model_cls):
        table = Base.metadata.tables[model_cls.__tablename__]
        col_names = {c.name for c in table.columns}
        assert "is_active" not in col_names


# --- Deal nullable customer FK test ---


class TestDealCustomerFK:
    """Deal.customer_id MUST be nullable for unresolved FK behavior."""

    def test_deal_customer_id_nullable(self):
        table = Base.metadata.tables["deals"]
        customer_id_col = table.c["customer_id"]
        assert customer_id_col.nullable is True

    def test_deal_customer_source_id_exists(self):
        table = Base.metadata.tables["deals"]
        col_names = {c.name for c in table.columns}
        assert "customer_source_id" in col_names

    def test_deal_owner_source_id_exists(self):
        table = Base.metadata.tables["deals"]
        col_names = {c.name for c in table.columns}
        assert "owner_source_id" in col_names


# --- Document body_text test ---


class TestDocumentBodyText:
    """Documents must have a body_text field capable of storing full text."""

    def test_body_text_exists(self):
        table = Base.metadata.tables["documents"]
        col_names = {c.name for c in table.columns}
        assert "body_text" in col_names

    def test_body_text_is_text_type(self):
        table = Base.metadata.tables["documents"]
        body_text_col = table.c["body_text"]
        # Text type, not limited VARCHAR
        assert "TEXT" in str(body_text_col.type).upper()


# --- Ingestion cursor identity test ---


class TestIngestionCursorIdentity:
    """Cursor key must support (source_system, source_entity) uniqueness."""

    def test_cursor_unique_constraint_exists(self):
        table = Base.metadata.tables["ingestion_cursors"]
        unique_constraints = [
            c for c in table.constraints
            if hasattr(c, "columns") and len(c.columns) > 1
        ]
        # Find the (source_system, source_entity) unique constraint
        found = False
        for uc in unique_constraints:
            col_names = {c.name for c in uc.columns}
            if col_names == {"source_system", "source_entity"}:
                found = True
                break
        assert found, "No unique constraint on (source_system, source_entity)"


# --- Monetary field precision tests ---


class TestMonetaryFields:
    """Financial amounts must use fixed-precision Numeric, not Float."""

    def test_deal_amount_is_numeric(self):
        table = Base.metadata.tables["deals"]
        amount_col = table.c["amount"]
        assert "NUMERIC" in str(amount_col.type).upper()

    def test_project_budget_is_numeric(self):
        table = Base.metadata.tables["projects"]
        budget_col = table.c["budget"]
        assert "NUMERIC" in str(budget_col.type).upper()


# --- Operational table tests ---


class TestOperationalTables:
    """Verify operational tables have expected columns."""

    def test_ingestion_run_has_status(self):
        table = Base.metadata.tables["ingestion_runs"]
        col_names = {c.name for c in table.columns}
        assert "status" in col_names
        assert "started_at" in col_names
        assert "finished_at" in col_names
        assert "records_fetched" in col_names
        assert "records_rejected" in col_names

    def test_ingestion_error_has_severity(self):
        table = Base.metadata.tables["ingestion_errors"]
        col_names = {c.name for c in table.columns}
        assert "severity" in col_names
        assert "message" in col_names
        assert "ingestion_run_id" in col_names

    def test_source_record_has_raw_payload(self):
        table = Base.metadata.tables["source_records"]
        col_names = {c.name for c in table.columns}
        assert "raw_payload" in col_names
        assert "content_hash" in col_names

    def test_connector_config_has_no_secret_columns(self):
        table = Base.metadata.tables["connector_configs"]
        col_names = {c.name for c in table.columns}
        forbidden = {"password", "api_key", "secret", "token", "bearer_token"}
        assert col_names & forbidden == set(), "ConnectorConfig must not store secrets"

    def test_connector_config_has_source_name_unique(self):
        table = Base.metadata.tables["connector_configs"]
        source_name_col = table.c["source_name"]
        assert source_name_col.unique is True


# --- Source identity unique constraint tests ---


class TestSourceIdentityConstraints:
    """Canonical entities must have unique (source_system, source_entity, source_id)."""

    @pytest.mark.parametrize("table_name", [
        "organizations", "employees", "customers", "deals",
        "projects", "support_tickets", "documents",
    ])
    def test_source_identity_unique(self, table_name):
        table = Base.metadata.tables[table_name]
        found = False
        for constraint in table.constraints:
            if hasattr(constraint, "columns"):
                col_names = {c.name for c in constraint.columns}
                if col_names == {"source_system", "source_entity", "source_id"}:
                    found = True
                    break
        assert found, f"No unique constraint on source identity for {table_name}"
