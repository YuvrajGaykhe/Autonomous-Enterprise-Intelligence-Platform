"""
B1 Database Integration Tests.

Tests that verify ORM models work correctly against real PostgreSQL.
Requires Docker PostgreSQL to be running.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
import app.persistence.models  # noqa: F401
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


@pytest.fixture
def engine(e1_engine, e1_sessions):
    """The migrated test database, with every table truncated first.

    These tests write the demo dataset's own source identities (CUST-001,
    EMP-001, ...), so they cannot share a database with anything that already
    holds them. e1_engine is the isolated <database>_test harness in
    tests/conftest.py; requesting e1_sessions truncates it before each test,
    which is what keeps those identities free.
    """
    return e1_engine


@pytest.fixture(scope="function")
def session(engine):
    """Create a session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    sess = Session(bind=connection)
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


# Helper: fixed UUIDs for deterministic tests
RUN_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
EMP_ID = uuid.uuid4()
CUST_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)


def _make_ingestion_run(run_id=None):
    return IngestionRun(
        id=run_id or uuid.uuid4(),
        source_system="csv_demo",
        source_entity="customers",
        status="SUCCESS",
        mode="full",
        started_at=NOW,
        finished_at=NOW,
        records_fetched=10,
        records_inserted=8,
        records_updated=1,
        records_unchanged=0,
        records_rejected=1,
        records_warnings=2,
        error_summary="1 record rejected due to missing email",
    )


@pytest.mark.integration
class TestInsertOrganization:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        org = Organization(
            id=ORG_ID,
            name="Acme Corp",
            industry="Technology",
            country="India",
            status="active",
            source_system="csv_demo",
            source_entity="organizations",
            source_id="ORG-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="abc123",
        )
        session.add(org)
        session.flush()

        loaded = session.get(Organization, ORG_ID)
        assert loaded is not None
        assert loaded.name == "Acme Corp"
        assert loaded.industry == "Technology"
        assert loaded.source_system == "csv_demo"
        assert loaded.record_hash == "abc123"


@pytest.mark.integration
class TestInsertEmployee:
    def test_insert_with_organization(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        org = Organization(
            name="Acme Corp",
            source_system="csv_demo",
            source_entity="organizations",
            source_id="ORG-EMP-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="orghash1",
        )
        session.add(org)
        session.flush()

        emp = Employee(
            name="Alice Engineer",
            email="alice@acme.com",
            department="Engineering",
            title="Senior Developer",
            manager_source_id="EMP-MGR-001",
            status="active",
            hire_date=date(2024, 3, 15),
            is_active=True,
            organization_id=org.id,
            source_system="csv_demo",
            source_entity="employees",
            source_id="EMP-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="emphash1",
        )
        session.add(emp)
        session.flush()

        loaded = session.get(Employee, emp.id)
        assert loaded is not None
        assert loaded.name == "Alice Engineer"
        assert loaded.is_active is True
        assert loaded.organization_id == org.id
        assert loaded.hire_date == date(2024, 3, 15)


@pytest.mark.integration
class TestInsertCustomer:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        cust = Customer(
            name="Widget Inc",
            email="contact@widget.com",
            segment="Enterprise",
            industry="Manufacturing",
            status="active",
            owner_source_id="EMP-003",
            created_at=NOW,
            is_active=True,
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="custhash1",
        )
        session.add(cust)
        session.flush()

        loaded = session.get(Customer, cust.id)
        assert loaded is not None
        assert loaded.name == "Widget Inc"
        assert loaded.is_active is True
        assert loaded.source_id == "CUST-001"


@pytest.mark.integration
class TestInsertDeal:
    def test_deal_with_customer(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        cust = Customer(
            name="DealCust",
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-DEAL-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="custhash2",
            is_active=True,
        )
        session.add(cust)
        session.flush()

        deal = Deal(
            name="Big Deal",
            stage="negotiation",
            amount=Decimal("150000.50"),
            currency="INR",
            probability=Decimal("75.00"),
            expected_close_date=date(2026, 12, 31),
            is_active=True,
            customer_source_id="CUST-DEAL-TEST",
            owner_source_id="EMP-005",
            customer_id=cust.id,
            source_system="csv_demo",
            source_entity="deals",
            source_id="DEAL-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="dealhash1",
        )
        session.add(deal)
        session.flush()

        loaded = session.get(Deal, deal.id)
        assert loaded is not None
        assert loaded.amount == Decimal("150000.50")
        assert loaded.customer_id == cust.id

    def test_deal_with_null_customer(self, session):
        """Critical test: deal with unresolvable customer FK."""
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        deal = Deal(
            name="Orphan Deal",
            stage="prospecting",
            amount=Decimal("5000.00"),
            currency="USD",
            is_active=True,
            customer_source_id="UNKNOWN-CUST-999",
            owner_source_id="EMP-007",
            customer_id=None,  # unresolved
            source_system="csv_demo",
            source_entity="deals",
            source_id="DEAL-ORPHAN-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="dealhash_orphan",
        )
        session.add(deal)
        session.flush()

        loaded = session.get(Deal, deal.id)
        assert loaded is not None
        assert loaded.customer_id is None
        assert loaded.customer_source_id == "UNKNOWN-CUST-999"


@pytest.mark.integration
class TestInsertProject:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        proj = Project(
            name="Platform Migration",
            status="in_progress",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            budget=Decimal("500000.00"),
            is_active=True,
            customer_source_id="CUST-010",
            owner_source_id="EMP-002",
            source_system="csv_demo",
            source_entity="projects",
            source_id="PROJ-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="projhash1",
        )
        session.add(proj)
        session.flush()

        loaded = session.get(Project, proj.id)
        assert loaded is not None
        assert loaded.budget == Decimal("500000.00")
        assert loaded.is_active is True


@pytest.mark.integration
class TestInsertSupportTicket:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        ticket = SupportTicket(
            subject="Login not working",
            description="User cannot log in after password reset.",
            priority="high",
            status="open",
            category="auth",
            created_at=NOW,
            customer_source_id="CUST-005",
            assignee_source_id="EMP-012",
            source_system="csv_demo",
            source_entity="support_tickets",
            source_id="TICKET-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="tickethash1",
        )
        session.add(ticket)
        session.flush()

        loaded = session.get(SupportTicket, ticket.id)
        assert loaded is not None
        assert loaded.subject == "Login not working"
        assert loaded.priority == "high"
        assert not hasattr(loaded, "is_active") or "is_active" not in {
            c.name for c in loaded.__table__.columns
        }


@pytest.mark.integration
class TestInsertDocument:
    def test_insert_with_body_text(self, session):
        """Document must support full multi-paragraph body_text."""
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        body = (
            "ACME CORPORATION - EMPLOYEE HANDBOOK\n\n"
            "Chapter 1: Introduction\n"
            "Welcome to Acme Corporation. This handbook outlines company policies, "
            "procedures, and expectations for all employees.\n\n"
            "Chapter 2: Code of Conduct\n"
            "All employees are expected to maintain the highest standards of "
            "professional conduct. This includes respect for colleagues, adherence "
            "to company policies, and commitment to ethical business practices.\n\n"
            "Chapter 3: Leave Policies\n"
            "Employees are entitled to 24 days of paid leave per year. Leave must "
            "be requested through the HR portal at least 7 days in advance for "
            "planned absences.\n"
        )

        doc = Document(
            title="Employee Handbook 2026",
            document_type="policy",
            body_text=body,
            source_uri="https://internal.acme.com/docs/handbook-2026.pdf",
            owner_source_id="EMP-001",
            created_at=NOW,
            updated_at=NOW,
            source_system="csv_demo",
            source_entity="documents",
            source_id="DOC-001",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="dochash1",
        )
        session.add(doc)
        session.flush()

        loaded = session.get(Document, doc.id)
        assert loaded is not None
        assert loaded.body_text == body
        assert "Chapter 3" in loaded.body_text
        assert loaded.title == "Employee Handbook 2026"


@pytest.mark.integration
class TestInsertIngestionRun:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        loaded = session.get(IngestionRun, run.id)
        assert loaded is not None
        assert loaded.status == "SUCCESS"
        assert loaded.records_fetched == 10
        assert loaded.records_rejected == 1


@pytest.mark.integration
class TestInsertIngestionError:
    def test_insert_with_run(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        error = IngestionError(
            ingestion_run_id=run.id,
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-BAD-001",
            severity="ERROR",
            error_code="MISSING_REQUIRED_FIELD",
            message="Required field 'email' is missing",
            detail="Row 42 in customers.csv",
        )
        session.add(error)
        session.flush()

        loaded = session.get(IngestionError, error.id)
        assert loaded is not None
        assert loaded.severity == "ERROR"
        assert loaded.ingestion_run_id == run.id


@pytest.mark.integration
class TestInsertSourceRecord:
    def test_insert_with_json_payload(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        record = SourceRecord(
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-RAW-001",
            ingestion_run_id=run.id,
            raw_payload={
                "customer_id": "CUST-RAW-001",
                "name": "Raw Customer",
                "email": "raw@example.com",
                "segment": "SMB",
            },
            content_hash="rawhash1",
        )
        session.add(record)
        session.flush()

        loaded = session.get(SourceRecord, record.id)
        assert loaded is not None
        assert loaded.raw_payload["name"] == "Raw Customer"
        assert loaded.content_hash == "rawhash1"


@pytest.mark.integration
class TestInsertConnectorConfig:
    def test_insert_without_secrets(self, session):
        config = ConnectorConfig(
            source_name="csv_demo",
            source_type="csv",
            enabled=True,
            config={
                "data_dir": "data/demo",
                "file_pattern": "*.csv",
            },
        )
        session.add(config)
        session.flush()

        loaded = session.get(ConnectorConfig, config.id)
        assert loaded is not None
        assert loaded.source_name == "csv_demo"
        assert loaded.config["data_dir"] == "data/demo"


@pytest.mark.integration
class TestInsertIngestionCursor:
    def test_insert_and_read(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        cursor = IngestionCursor(
            source_system="odoo_mock",
            source_entity="customers",
            last_cursor="2026-09-07T10:00:00Z",
            last_successful_run_id=run.id,
        )
        session.add(cursor)
        session.flush()

        loaded = session.get(IngestionCursor, cursor.id)
        assert loaded is not None
        assert loaded.source_system == "odoo_mock"
        assert loaded.last_cursor == "2026-09-07T10:00:00Z"


@pytest.mark.integration
class TestProvenancePersistence:
    """Verify all provenance fields persist correctly on a representative entity."""

    def test_full_provenance(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        source_updated = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

        cust = Customer(
            name="Provenance Test Customer",
            source_system="odoo_mock",
            source_entity="res.partner",
            source_id="ODOO-CUST-42",
            source_updated_at=source_updated,
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="provenance_test_hash",
            is_active=True,
        )
        session.add(cust)
        session.flush()

        loaded = session.get(Customer, cust.id)
        assert loaded.source_system == "odoo_mock"
        assert loaded.source_entity == "res.partner"
        assert loaded.source_id == "ODOO-CUST-42"
        assert loaded.source_updated_at == source_updated
        assert loaded.ingested_at is not None
        assert loaded.ingestion_run_id == run.id
        assert loaded.record_hash == "provenance_test_hash"


@pytest.mark.integration
class TestForeignKeyRelationships:
    """Verify FK relationships resolve correctly."""

    def test_employee_organization_relationship(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        org = Organization(
            name="FK Test Org",
            source_system="csv_demo",
            source_entity="organizations",
            source_id="ORG-FK-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="orgfkhash",
        )
        session.add(org)
        session.flush()

        emp = Employee(
            name="FK Test Employee",
            is_active=True,
            organization_id=org.id,
            source_system="csv_demo",
            source_entity="employees",
            source_id="EMP-FK-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="empfkhash",
        )
        session.add(emp)
        session.flush()

        loaded_emp = session.get(Employee, emp.id)
        assert loaded_emp.organization.name == "FK Test Org"

    def test_deal_customer_relationship(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        cust = Customer(
            name="FK Deal Customer",
            is_active=True,
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-FK-DEAL",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="custfkdealhash",
        )
        session.add(cust)
        session.flush()

        deal = Deal(
            name="FK Test Deal",
            is_active=True,
            customer_id=cust.id,
            customer_source_id="CUST-FK-DEAL",
            source_system="csv_demo",
            source_entity="deals",
            source_id="DEAL-FK-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="dealfkhash",
        )
        session.add(deal)
        session.flush()

        loaded_deal = session.get(Deal, deal.id)
        assert loaded_deal.customer.name == "FK Deal Customer"

    def test_ticket_customer_relationship(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        cust = Customer(
            name="FK Ticket Customer",
            is_active=True,
            source_system="csv_demo",
            source_entity="customers",
            source_id="CUST-FK-TICKET",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="custfktickethash",
        )
        session.add(cust)
        session.flush()

        ticket = SupportTicket(
            subject="FK Test Ticket",
            customer_id=cust.id,
            customer_source_id="CUST-FK-TICKET",
            source_system="csv_demo",
            source_entity="support_tickets",
            source_id="TICKET-FK-TEST",
            ingested_at=NOW,
            ingestion_run_id=run.id,
            record_hash="ticketfkhash",
        )
        session.add(ticket)
        session.flush()

        loaded_ticket = session.get(SupportTicket, ticket.id)
        assert loaded_ticket.customer.name == "FK Ticket Customer"

    def test_error_run_relationship(self, session):
        run = _make_ingestion_run()
        session.add(run)
        session.flush()

        error = IngestionError(
            ingestion_run_id=run.id,
            severity="WARNING",
            message="Unresolved FK",
        )
        session.add(error)
        session.flush()

        loaded_error = session.get(IngestionError, error.id)
        assert loaded_error.ingestion_run.status == "SUCCESS"
