"""
B2 Canonical Schema Tests.

Verifies all seven canonical Pydantic schemas against the Layer 1
specification contract. Tests cover:

- Import correctness
- Valid instantiation
- UUID field validation
- Required field enforcement
- Nullable field behavior
- is_active placement
- Deal customer_id nullable behavior
- Decimal monetary fields
- Document body_text
- Provenance field representation
- Source identity preservation
- Timestamp validation
- ORM compatibility (from_attributes)
- Serialization (JSON-compatible)
- Contract protection (expected field sets)
- No source-specific field leakage
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.canonical import (
    CanonicalBase,
    CustomerCanonical,
    DealCanonical,
    DocumentCanonical,
    EmployeeCanonical,
    OrganizationCanonical,
    ProjectCanonical,
    SupportTicketCanonical,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
RUN_ID = uuid.uuid4()
RECORD_ID = uuid.uuid4()
CUST_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()


def _provenance_kwargs(**overrides):
    """Base provenance fields for constructing canonical schemas."""
    base = {
        "id": RECORD_ID,
        "source_system": "csv_demo",
        "source_entity": "test_entity",
        "source_id": "TEST-001",
        "source_updated_at": NOW,
        "ingested_at": NOW,
        "ingestion_run_id": RUN_ID,
        "record_hash": "abc123def456",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Import correctness
# ---------------------------------------------------------------------------


class TestImports:
    """All seven schemas and CanonicalBase must import correctly."""

    def test_canonical_base_import(self):
        assert CanonicalBase is not None

    def test_organization_import(self):
        assert OrganizationCanonical is not None

    def test_employee_import(self):
        assert EmployeeCanonical is not None

    def test_customer_import(self):
        assert CustomerCanonical is not None

    def test_deal_import(self):
        assert DealCanonical is not None

    def test_project_import(self):
        assert ProjectCanonical is not None

    def test_support_ticket_import(self):
        assert SupportTicketCanonical is not None

    def test_document_import(self):
        assert DocumentCanonical is not None


# ---------------------------------------------------------------------------
# 2. Valid instantiation
# ---------------------------------------------------------------------------


class TestValidInstantiation:
    """All seven schemas must accept valid canonical data."""

    def test_organization_valid(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Acme Corp",
            industry="Technology",
            country="India",
            status="active",
        )
        assert org.name == "Acme Corp"
        assert org.industry == "Technology"

    def test_employee_valid(self):
        emp = EmployeeCanonical(
            **_provenance_kwargs(source_entity="employees"),
            name="Alice Engineer",
            email="alice@acme.com",
            department="Engineering",
            title="Senior Developer",
            manager_source_id="EMP-MGR-001",
            status="active",
            hire_date=date(2024, 3, 15),
            is_active=True,
            organization_id=ORG_ID,
        )
        assert emp.name == "Alice Engineer"
        assert emp.is_active is True
        assert emp.organization_id == ORG_ID

    def test_customer_valid(self):
        cust = CustomerCanonical(
            **_provenance_kwargs(source_entity="customers"),
            name="Widget Inc",
            email="contact@widget.com",
            segment="Enterprise",
            industry="Manufacturing",
            status="active",
            owner_source_id="EMP-003",
            created_at=NOW,
            is_active=True,
        )
        assert cust.name == "Widget Inc"
        assert cust.is_active is True

    def test_deal_valid(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Big Deal",
            stage="negotiation",
            amount=Decimal("150000.50"),
            currency="INR",
            probability=Decimal("75.00"),
            expected_close_date=date(2026, 12, 31),
            is_active=True,
            customer_source_id="CUST-001",
            owner_source_id="EMP-005",
            customer_id=CUST_ID,
        )
        assert deal.name == "Big Deal"
        assert deal.amount == Decimal("150000.50")
        assert deal.customer_id == CUST_ID

    def test_project_valid(self):
        proj = ProjectCanonical(
            **_provenance_kwargs(source_entity="projects"),
            name="Platform Migration",
            status="in_progress",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            budget=Decimal("500000.00"),
            is_active=True,
            customer_source_id="CUST-010",
            owner_source_id="EMP-002",
            customer_id=CUST_ID,
        )
        assert proj.name == "Platform Migration"
        assert proj.budget == Decimal("500000.00")

    def test_support_ticket_valid(self):
        ticket = SupportTicketCanonical(
            **_provenance_kwargs(source_entity="support_tickets"),
            subject="Login not working",
            description="User cannot log in after password reset.",
            priority="high",
            status="open",
            category="auth",
            created_at=NOW,
            resolved_at=None,
            customer_source_id="CUST-005",
            assignee_source_id="EMP-012",
            customer_id=CUST_ID,
        )
        assert ticket.subject == "Login not working"
        assert ticket.priority == "high"

    def test_document_valid(self):
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            title="Employee Handbook 2026",
            document_type="policy",
            body_text="Full document content here with multiple paragraphs.",
            source_uri="https://internal.acme.com/docs/handbook.pdf",
            owner_source_id="EMP-001",
            created_at=NOW,
            updated_at=NOW,
        )
        assert doc.title == "Employee Handbook 2026"
        assert doc.body_text == "Full document content here with multiple paragraphs."


# ---------------------------------------------------------------------------
# 3. UUID field validation
# ---------------------------------------------------------------------------


class TestUUIDValidation:
    """UUID fields must reject invalid UUIDs."""

    def test_invalid_id_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationCanonical(
                **_provenance_kwargs(id="not-a-uuid", source_entity="organizations"),
                name="Test",
            )

    def test_invalid_ingestion_run_id_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationCanonical(
                **_provenance_kwargs(
                    ingestion_run_id="bad-uuid",
                    source_entity="organizations",
                ),
                name="Test",
            )

    def test_valid_uuid_string_accepted(self):
        uid = str(uuid.uuid4())
        org = OrganizationCanonical(
            **_provenance_kwargs(id=uid, source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.id, uuid.UUID)


# ---------------------------------------------------------------------------
# 4. Required field enforcement
# ---------------------------------------------------------------------------


class TestRequiredFields:
    """Required fields must raise ValidationError when missing."""

    def test_organization_name_required(self):
        with pytest.raises(ValidationError):
            OrganizationCanonical(
                **_provenance_kwargs(source_entity="organizations"),
                # name missing
            )

    def test_employee_name_required(self):
        with pytest.raises(ValidationError):
            EmployeeCanonical(
                **_provenance_kwargs(source_entity="employees"),
                is_active=True,
                # name missing
            )

    def test_employee_is_active_required(self):
        with pytest.raises(ValidationError):
            EmployeeCanonical(
                **_provenance_kwargs(source_entity="employees"),
                name="Test",
                # is_active missing
            )

    def test_customer_name_required(self):
        with pytest.raises(ValidationError):
            CustomerCanonical(
                **_provenance_kwargs(source_entity="customers"),
                is_active=True,
                # name missing
            )

    def test_deal_name_required(self):
        with pytest.raises(ValidationError):
            DealCanonical(
                **_provenance_kwargs(source_entity="deals"),
                is_active=True,
                # name missing
            )

    def test_project_name_required(self):
        with pytest.raises(ValidationError):
            ProjectCanonical(
                **_provenance_kwargs(source_entity="projects"),
                is_active=True,
                # name missing
            )

    def test_provenance_source_system_required(self):
        with pytest.raises(ValidationError):
            OrganizationCanonical(
                id=RECORD_ID,
                # source_system missing
                source_entity="organizations",
                source_id="ORG-001",
                ingested_at=NOW,
                ingestion_run_id=RUN_ID,
                record_hash="abc",
                name="Test",
            )

    def test_provenance_record_hash_required(self):
        with pytest.raises(ValidationError):
            OrganizationCanonical(
                id=RECORD_ID,
                source_system="csv_demo",
                source_entity="organizations",
                source_id="ORG-001",
                ingested_at=NOW,
                ingestion_run_id=RUN_ID,
                # record_hash missing
                name="Test",
            )


# ---------------------------------------------------------------------------
# 5. Nullable field behavior
# ---------------------------------------------------------------------------


class TestNullableFields:
    """Optional/nullable fields must accept None."""

    def test_organization_optional_fields_none(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Minimal Org",
        )
        assert org.industry is None
        assert org.country is None
        assert org.status is None

    def test_employee_optional_fields_none(self):
        emp = EmployeeCanonical(
            **_provenance_kwargs(source_entity="employees"),
            name="Minimal Employee",
            is_active=True,
        )
        assert emp.email is None
        assert emp.department is None
        assert emp.title is None
        assert emp.manager_source_id is None
        assert emp.status is None
        assert emp.hire_date is None
        assert emp.organization_id is None

    def test_deal_optional_fields_none(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Minimal Deal",
            is_active=True,
        )
        assert deal.stage is None
        assert deal.amount is None
        assert deal.currency is None
        assert deal.probability is None
        assert deal.expected_close_date is None
        assert deal.customer_source_id is None
        assert deal.owner_source_id is None
        assert deal.customer_id is None

    def test_provenance_source_updated_at_nullable(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(
                source_entity="organizations",
                source_updated_at=None,
            ),
            name="Test",
        )
        assert org.source_updated_at is None

    def test_support_ticket_all_business_fields_nullable(self):
        ticket = SupportTicketCanonical(
            **_provenance_kwargs(source_entity="support_tickets"),
        )
        assert ticket.subject is None
        assert ticket.description is None
        assert ticket.priority is None
        assert ticket.status is None
        assert ticket.category is None
        assert ticket.created_at is None
        assert ticket.resolved_at is None
        assert ticket.customer_source_id is None
        assert ticket.assignee_source_id is None
        assert ticket.customer_id is None


# ---------------------------------------------------------------------------
# 6 & 7. is_active placement
# ---------------------------------------------------------------------------


SCHEMAS_WITH_IS_ACTIVE = [
    EmployeeCanonical,
    CustomerCanonical,
    DealCanonical,
    ProjectCanonical,
]

SCHEMAS_WITHOUT_IS_ACTIVE = [
    OrganizationCanonical,
    SupportTicketCanonical,
    DocumentCanonical,
]


class TestIsActivePlacement:
    """is_active must exist only on Employee, Customer, Deal, Project."""

    @pytest.mark.parametrize("schema_cls", SCHEMAS_WITH_IS_ACTIVE)
    def test_has_is_active(self, schema_cls):
        assert "is_active" in schema_cls.model_fields

    @pytest.mark.parametrize("schema_cls", SCHEMAS_WITHOUT_IS_ACTIVE)
    def test_does_not_have_is_active(self, schema_cls):
        assert "is_active" not in schema_cls.model_fields


# ---------------------------------------------------------------------------
# 8. Deal customer_id nullable
# ---------------------------------------------------------------------------


class TestDealCustomerNullable:
    """Deal.customer_id MUST be nullable for unresolved FK behavior."""

    def test_deal_with_null_customer_id(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Orphan Deal",
            is_active=True,
            customer_source_id="UNKNOWN-CUST-999",
            customer_id=None,
        )
        assert deal.customer_id is None
        assert deal.customer_source_id == "UNKNOWN-CUST-999"

    def test_deal_with_resolved_customer_id(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Resolved Deal",
            is_active=True,
            customer_source_id="CUST-001",
            customer_id=CUST_ID,
        )
        assert deal.customer_id == CUST_ID

    def test_deal_customer_source_id_preserved_when_null_customer(self):
        """Source key must survive even when canonical FK is None."""
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Preserved Key Deal",
            is_active=True,
            customer_source_id="LEGACY-CUST-42",
            customer_id=None,
        )
        assert deal.customer_source_id == "LEGACY-CUST-42"
        assert deal.customer_id is None


# ---------------------------------------------------------------------------
# 9. Decimal monetary fields
# ---------------------------------------------------------------------------


class TestDecimalMonetary:
    """Financial fields must use Decimal, not float."""

    def test_deal_amount_decimal(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Decimal Test",
            is_active=True,
            amount=Decimal("150000.50"),
        )
        assert isinstance(deal.amount, Decimal)
        assert deal.amount == Decimal("150000.50")

    def test_deal_probability_decimal(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Prob Test",
            is_active=True,
            probability=Decimal("75.50"),
        )
        assert isinstance(deal.probability, Decimal)

    def test_project_budget_decimal(self):
        proj = ProjectCanonical(
            **_provenance_kwargs(source_entity="projects"),
            name="Budget Test",
            is_active=True,
            budget=Decimal("500000.00"),
        )
        assert isinstance(proj.budget, Decimal)
        assert proj.budget == Decimal("500000.00")

    def test_deal_amount_from_string(self):
        """Decimal fields should accept string representation."""
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="String Decimal",
            is_active=True,
            amount="99999.99",
        )
        assert deal.amount == Decimal("99999.99")


# ---------------------------------------------------------------------------
# 10. Document body_text
# ---------------------------------------------------------------------------


class TestDocumentBodyText:
    """Document body_text must accept full textual content."""

    def test_empty_body_text(self):
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            body_text="",
        )
        assert doc.body_text == ""

    def test_normal_body_text(self):
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            body_text="A short document.",
        )
        assert doc.body_text == "A short document."

    def test_multi_paragraph_body_text(self):
        body = (
            "Chapter 1: Introduction\n\n"
            "Welcome to the company. This handbook covers all policies.\n\n"
            "Chapter 2: Code of Conduct\n\n"
            "Maintain professional standards at all times.\n\n"
            "Chapter 3: Benefits\n\n"
            "Employees receive 24 days of paid leave annually."
        )
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            body_text=body,
        )
        assert "Chapter 3" in doc.body_text

    def test_long_body_text(self):
        """body_text should have no artificial length limit."""
        long_text = "x" * 100_000
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            body_text=long_text,
        )
        assert len(doc.body_text) == 100_000

    def test_null_body_text(self):
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
        )
        assert doc.body_text is None


# ---------------------------------------------------------------------------
# 11. Provenance fields
# ---------------------------------------------------------------------------


PROVENANCE_FIELDS = {
    "id", "source_system", "source_entity", "source_id",
    "source_updated_at", "ingested_at", "ingestion_run_id", "record_hash",
}

ALL_CANONICAL_SCHEMAS = [
    OrganizationCanonical,
    EmployeeCanonical,
    CustomerCanonical,
    DealCanonical,
    ProjectCanonical,
    SupportTicketCanonical,
    DocumentCanonical,
]


class TestProvenanceFields:
    """All canonical schemas must include the full provenance contract."""

    @pytest.mark.parametrize("schema_cls", ALL_CANONICAL_SCHEMAS)
    def test_provenance_fields_present(self, schema_cls):
        schema_fields = set(schema_cls.model_fields.keys())
        for field in PROVENANCE_FIELDS:
            assert field in schema_fields, (
                f"Provenance field '{field}' missing from {schema_cls.__name__}"
            )


# ---------------------------------------------------------------------------
# 12. Source identity preservation
# ---------------------------------------------------------------------------


class TestSourceIdentity:
    """Source identity fields must be preserved as strings."""

    def test_source_system_is_string(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.source_system, str)

    def test_source_id_is_string(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.source_id, str)

    def test_source_entity_is_string(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.source_entity, str)


# ---------------------------------------------------------------------------
# 13. Timestamp validation
# ---------------------------------------------------------------------------


class TestTimestampFields:
    """Timestamp fields must accept datetime objects."""

    def test_ingested_at_datetime(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.ingested_at, datetime)

    def test_source_updated_at_datetime(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Test",
        )
        assert isinstance(org.source_updated_at, datetime)

    def test_source_updated_at_timezone_preserved(self):
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        org = OrganizationCanonical(
            **_provenance_kwargs(
                source_entity="organizations",
                source_updated_at=ts,
            ),
            name="Test",
        )
        assert org.source_updated_at.tzinfo is not None

    def test_customer_created_at(self):
        cust = CustomerCanonical(
            **_provenance_kwargs(source_entity="customers"),
            name="Test",
            is_active=True,
            created_at=NOW,
        )
        assert isinstance(cust.created_at, datetime)

    def test_ticket_created_at_and_resolved_at(self):
        ticket = SupportTicketCanonical(
            **_provenance_kwargs(source_entity="support_tickets"),
            created_at=NOW,
            resolved_at=NOW,
        )
        assert isinstance(ticket.created_at, datetime)
        assert isinstance(ticket.resolved_at, datetime)


# ---------------------------------------------------------------------------
# 14. ORM compatibility (from_attributes)
# ---------------------------------------------------------------------------


class TestORMCompatibility:
    """Schemas must support from_attributes for ORM object conversion."""

    def test_from_attributes_enabled(self):
        assert CanonicalBase.model_config.get("from_attributes") is True

    @pytest.mark.parametrize("schema_cls", ALL_CANONICAL_SCHEMAS)
    def test_all_schemas_from_attributes(self, schema_cls):
        assert schema_cls.model_config.get("from_attributes") is True

    def test_from_attributes_with_mock_orm(self):
        """Simulate ORM object attribute access via a simple namespace."""

        class MockORM:
            pass

        obj = MockORM()
        obj.id = RECORD_ID
        obj.source_system = "csv_demo"
        obj.source_entity = "organizations"
        obj.source_id = "ORG-001"
        obj.source_updated_at = NOW
        obj.ingested_at = NOW
        obj.ingestion_run_id = RUN_ID
        obj.record_hash = "mock_hash"
        obj.name = "Mock Org"
        obj.industry = None
        obj.country = None
        obj.status = None

        org = OrganizationCanonical.model_validate(obj, from_attributes=True)
        assert org.name == "Mock Org"
        assert org.source_system == "csv_demo"


# ---------------------------------------------------------------------------
# 15. No source-specific fields
# ---------------------------------------------------------------------------


SOURCE_SPECIFIC_FIELDS = {
    "salesforce_contact_id", "odoo_partner_id", "sap_customer_number",
    "crm_lead_id", "erp_account_id", "hubspot_id", "zoho_id",
    "sf_opportunity_id",
}


class TestNoSourceSpecificFields:
    """Canonical schemas must not contain source-specific fields."""

    @pytest.mark.parametrize("schema_cls", ALL_CANONICAL_SCHEMAS)
    def test_no_source_specific_fields(self, schema_cls):
        schema_fields = set(schema_cls.model_fields.keys())
        leaked = schema_fields & SOURCE_SPECIFIC_FIELDS
        assert leaked == set(), (
            f"Source-specific fields found in {schema_cls.__name__}: {leaked}"
        )


# ---------------------------------------------------------------------------
# 33. Specification contract tests (expected field sets)
# ---------------------------------------------------------------------------


EXPECTED_FIELDS = {
    "OrganizationCanonical": PROVENANCE_FIELDS | {
        "name", "industry", "country", "status",
    },
    "EmployeeCanonical": PROVENANCE_FIELDS | {
        "name", "email", "department", "title", "manager_source_id",
        "status", "hire_date", "is_active", "organization_id",
    },
    "CustomerCanonical": PROVENANCE_FIELDS | {
        "name", "email", "segment", "industry", "status",
        "owner_source_id", "created_at", "is_active",
    },
    "DealCanonical": PROVENANCE_FIELDS | {
        "name", "stage", "amount", "currency", "probability",
        "expected_close_date", "is_active",
        "customer_source_id", "owner_source_id", "customer_id",
    },
    "ProjectCanonical": PROVENANCE_FIELDS | {
        "name", "status", "start_date", "end_date", "budget",
        "is_active",
        "customer_source_id", "owner_source_id", "customer_id",
    },
    "SupportTicketCanonical": PROVENANCE_FIELDS | {
        "subject", "description", "priority", "status", "category",
        "created_at", "resolved_at",
        "customer_source_id", "assignee_source_id", "customer_id",
    },
    "DocumentCanonical": PROVENANCE_FIELDS | {
        "title", "document_type", "body_text", "source_uri",
        "owner_source_id", "created_at", "updated_at",
    },
}


class TestContractProtection:
    """Each schema must have exactly the expected field set."""

    @pytest.mark.parametrize("schema_cls", ALL_CANONICAL_SCHEMAS)
    def test_exact_field_set(self, schema_cls):
        name = schema_cls.__name__
        actual = set(schema_cls.model_fields.keys())
        expected = EXPECTED_FIELDS[name]
        missing = expected - actual
        extra = actual - expected
        assert missing == set(), f"{name} missing fields: {missing}"
        assert extra == set(), f"{name} unexpected fields: {extra}"


# ---------------------------------------------------------------------------
# 35. Serialization tests
# ---------------------------------------------------------------------------


class TestSerialization:
    """Canonical schemas must serialize cleanly for JSON responses."""

    def test_organization_serialization(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(source_entity="organizations"),
            name="Serialize Test",
        )
        data = org.model_dump(mode="json")
        assert isinstance(data["id"], str)
        assert isinstance(data["ingestion_run_id"], str)
        assert isinstance(data["ingested_at"], str)

    def test_deal_decimal_serialization(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Decimal Serialize",
            is_active=True,
            amount=Decimal("150000.50"),
            probability=Decimal("75.00"),
        )
        data = deal.model_dump(mode="json")
        # Pydantic v2 serializes Decimal as string in JSON mode
        assert data["amount"] is not None
        assert data["probability"] is not None

    def test_nullable_values_serialize(self):
        org = OrganizationCanonical(
            **_provenance_kwargs(
                source_entity="organizations",
                source_updated_at=None,
            ),
            name="Null Serialize",
        )
        data = org.model_dump(mode="json")
        assert data["source_updated_at"] is None
        assert data["industry"] is None

    def test_document_body_text_serialization(self):
        body = "Long document\n\nWith paragraphs\n\nAnd newlines."
        doc = DocumentCanonical(
            **_provenance_kwargs(source_entity="documents"),
            body_text=body,
        )
        data = doc.model_dump(mode="json")
        assert data["body_text"] == body

    def test_date_serialization(self):
        deal = DealCanonical(
            **_provenance_kwargs(source_entity="deals"),
            name="Date Test",
            is_active=True,
            expected_close_date=date(2026, 12, 31),
        )
        data = deal.model_dump(mode="json")
        assert data["expected_close_date"] == "2026-12-31"

    def test_employee_hire_date_serialization(self):
        emp = EmployeeCanonical(
            **_provenance_kwargs(source_entity="employees"),
            name="Date Emp",
            is_active=True,
            hire_date=date(2024, 3, 15),
        )
        data = emp.model_dump(mode="json")
        assert data["hire_date"] == "2024-03-15"
