"""
B3 Source Schema Tests.

Verifies all 21 source schemas (7 entities x 3 source systems) against
the Layer 1 source contract. Tests cover:

- Import correctness
- Valid source payload accepted
- Required source fields enforced
- Invalid types rejected
- Nullable/optional fields
- Source ID preserved exactly (no UUID conversion)
- Source-native status/values preserved (no normalization)
- Source-native relationship keys preserved
- No whitespace transformation
- No canonical UUID conversion
- No canonical hash generation
- No ingestion metadata invented
- Unknown-field behavior (extra="ignore")
- Timestamp behavior (source-native)
- Monetary source representation
- Long document text
- Cross-contract tests (B3 != B2)
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.source.common import SourceBase
from app.schemas.source.csv import (
    CsvOrganizationSource,
    CsvEmployeeSource,
    CsvCustomerSource,
    CsvDealSource,
    CsvProjectSource,
    CsvSupportTicketSource,
    CsvDocumentSource,
)
from app.schemas.source.odoo import (
    OdooOrganizationSource,
    OdooEmployeeSource,
    OdooCustomerSource,
    OdooDealSource,
    OdooProjectSource,
    OdooSupportTicketSource,
    OdooDocumentSource,
)
from app.schemas.source.rest import (
    RestOrganizationSource,
    RestEmployeeSource,
    RestCustomerSource,
    RestDealSource,
    RestProjectSource,
    RestSupportTicketSource,
    RestDocumentSource,
)


ALL_CSV_SCHEMAS = [
    CsvOrganizationSource,
    CsvEmployeeSource,
    CsvCustomerSource,
    CsvDealSource,
    CsvProjectSource,
    CsvSupportTicketSource,
    CsvDocumentSource,
]

ALL_ODOO_SCHEMAS = [
    OdooOrganizationSource,
    OdooEmployeeSource,
    OdooCustomerSource,
    OdooDealSource,
    OdooProjectSource,
    OdooSupportTicketSource,
    OdooDocumentSource,
]

ALL_REST_SCHEMAS = [
    RestOrganizationSource,
    RestEmployeeSource,
    RestCustomerSource,
    RestDealSource,
    RestProjectSource,
    RestSupportTicketSource,
    RestDocumentSource,
]

ALL_SOURCE_SCHEMAS = ALL_CSV_SCHEMAS + ALL_ODOO_SCHEMAS + ALL_REST_SCHEMAS


# ---------------------------------------------------------------------------
# 1. Import correctness
# ---------------------------------------------------------------------------


class TestImports:
    """All source schemas must import correctly."""

    def test_source_base_import(self):
        assert SourceBase is not None

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_source_schema_import(self, schema_cls):
        assert schema_cls is not None

    def test_csv_count(self):
        assert len(ALL_CSV_SCHEMAS) == 7

    def test_odoo_count(self):
        assert len(ALL_ODOO_SCHEMAS) == 7

    def test_rest_count(self):
        assert len(ALL_REST_SCHEMAS) == 7

    def test_total_count(self):
        assert len(ALL_SOURCE_SCHEMAS) == 21


# ---------------------------------------------------------------------------
# 2. Valid source payloads accepted
# ---------------------------------------------------------------------------


class TestCsvValidPayloads:
    """CSV source schemas must accept valid CSV row data."""

    def test_csv_organization(self):
        org = CsvOrganizationSource(
            organization_id="ORG-001",
            organization_name="Acme Corp",
            industry="Technology",
            country="India",
            status="active",
        )
        assert org.organization_id == "ORG-001"
        assert org.organization_name == "Acme Corp"

    def test_csv_employee(self):
        emp = CsvEmployeeSource(
            employee_id="EMP-001",
            employee_name="Alice Engineer",
            email_address="alice@acme.com",
            department="Engineering",
            title="Senior Developer",
            manager_id="EMP-MGR-001",
            status="active",
            hire_date="2024-03-15",
            is_active="true",
            organization_id="ORG-001",
        )
        assert emp.employee_id == "EMP-001"
        assert emp.hire_date == "2024-03-15"

    def test_csv_customer(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Widget Inc",
            email_address="contact@widget.com",
            customer_segment="Enterprise",
            industry_name="Manufacturing",
            account_owner_id="EMP-003",
            status="active",
            created_date="2024-01-15",
        )
        assert cust.customer_id == "CUST-001"
        assert cust.customer_name == "Widget Inc"
        assert cust.customer_segment == "Enterprise"

    def test_csv_deal(self):
        deal = CsvDealSource(
            deal_id="DEAL-001",
            deal_name="Big Deal",
            customer_id="CUST-001",
            owner_id="EMP-005",
            stage="negotiation",
            amount="150000.50",
            currency="INR",
            probability="0.75",
            expected_close_date="2026-12-31",
            is_active="true",
        )
        assert deal.deal_id == "DEAL-001"
        assert deal.amount == "150000.50"

    def test_csv_project(self):
        proj = CsvProjectSource(
            project_id="PROJ-001",
            project_name="Platform Migration",
            customer_id="CUST-010",
            owner_id="EMP-002",
            status="in_progress",
            start_date="2026-01-01",
            end_date="2026-12-31",
            budget="500000.00",
            is_active="true",
        )
        assert proj.project_id == "PROJ-001"
        assert proj.budget == "500000.00"

    def test_csv_support_ticket(self):
        ticket = CsvSupportTicketSource(
            ticket_id="TKT-001",
            customer_id="CUST-005",
            assignee_id="EMP-012",
            priority="high",
            status="open",
            category="auth",
            subject="Login not working",
            description="User cannot log in after password reset.",
            created_date="2026-09-01",
            resolved_date=None,
        )
        assert ticket.ticket_id == "TKT-001"

    def test_csv_document(self):
        doc = CsvDocumentSource(
            document_id="DOC-001",
            title="Employee Handbook 2026",
            document_type="policy",
            body_text="Full document content here.",
            source_uri="https://internal.acme.com/docs/handbook.pdf",
            owner_id="EMP-001",
            created_date="2026-01-01",
            updated_date="2026-06-15",
        )
        assert doc.document_id == "DOC-001"


class TestOdooValidPayloads:
    """Odoo source schemas must accept valid Odoo-style JSON data."""

    def test_odoo_organization(self):
        org = OdooOrganizationSource(
            id=1,
            name="Acme Corp",
            industry_id="tech",
            country_id="IN",
            active=True,
        )
        assert org.id == 1
        assert isinstance(org.id, int)

    def test_odoo_employee(self):
        emp = OdooEmployeeSource(
            id=42,
            name="Alice Engineer",
            work_email="alice@acme.com",
            department_id="engineering",
            job_title="Senior Developer",
            parent_id=10,
            active=True,
            x_hire_date="2024-03-15",
            company_id=1,
        )
        assert emp.id == 42
        assert emp.parent_id == 10

    def test_odoo_customer(self):
        cust = OdooCustomerSource(
            id=100,
            name="Widget Inc",
            email="contact@widget.com",
            x_studio_segment="Enterprise",
            industry_id="manufacturing",
            user_id=5,
            active=True,
            create_date="2024-01-15 10:30:00",
            customer_rank=1,
        )
        assert cust.id == 100
        assert cust.x_studio_segment == "Enterprise"
        assert cust.customer_rank == 1

    def test_odoo_deal(self):
        deal = OdooDealSource(
            id=200,
            name="Big Opportunity",
            partner_id=100,
            user_id=5,
            stage_id="negotiation",
            expected_revenue=150000.50,
            company_currency="INR",
            probability=75.0,
            date_deadline="2026-12-31",
            active=True,
        )
        assert deal.id == 200
        assert deal.expected_revenue == 150000.50

    def test_odoo_project(self):
        proj = OdooProjectSource(
            id=300,
            name="Platform Migration",
            partner_id=100,
            user_id=5,
            stage_id="in_progress",
            date_start="2026-01-01",
            date="2026-12-31",
            x_budget=500000.0,
            active=True,
        )
        assert proj.id == 300
        assert proj.x_budget == 500000.0

    def test_odoo_support_ticket(self):
        ticket = OdooSupportTicketSource(
            id=400,
            partner_id=100,
            user_id=12,
            priority="2",
            stage_id="open",
            category_id="auth",
            name="Login not working",
            description="User cannot log in.",
            create_date="2026-09-01 08:00:00",
            close_date=None,
        )
        assert ticket.id == 400

    def test_odoo_document(self):
        doc = OdooDocumentSource(
            id=500,
            name="Employee Handbook",
            type="policy",
            datas=None,
            url="https://internal.acme.com/docs/handbook.pdf",
            owner_id=1,
            create_date="2026-01-01 00:00:00",
            write_date="2026-06-15 12:00:00",
        )
        assert doc.id == 500


class TestRestValidPayloads:
    """REST source schemas must accept valid generic REST JSON data."""

    def test_rest_organization(self):
        org = RestOrganizationSource(
            id="org-001",
            name="Acme Corp",
            industry="Technology",
            country="India",
            status="active",
        )
        assert org.id == "org-001"

    def test_rest_customer(self):
        cust = RestCustomerSource(
            id="cust-001",
            name="Widget Inc",
            email="contact@widget.com",
            segment="Enterprise",
            industry="Manufacturing",
            ownerId="emp-003",
            status="active",
            createdAt="2024-01-15T10:30:00Z",
            isActive=True,
        )
        assert cust.id == "cust-001"
        assert cust.ownerId == "emp-003"

    def test_rest_deal(self):
        deal = RestDealSource(
            id="deal-001",
            name="Big Deal",
            customerId="cust-001",
            ownerId="emp-005",
            stage="negotiation",
            amount=150000.50,
            currency="INR",
            probability=0.75,
            expectedCloseDate="2026-12-31",
            isActive=True,
        )
        assert deal.id == "deal-001"
        assert deal.amount == 150000.50


# ---------------------------------------------------------------------------
# 3. Required source fields enforced
# ---------------------------------------------------------------------------


class TestRequiredFields:
    """Required source fields must raise ValidationError when missing."""

    def test_csv_customer_id_required(self):
        with pytest.raises(ValidationError):
            CsvCustomerSource(customer_name="Test")

    def test_csv_customer_name_required(self):
        with pytest.raises(ValidationError):
            CsvCustomerSource(customer_id="CUST-001")

    def test_csv_deal_id_required(self):
        with pytest.raises(ValidationError):
            CsvDealSource(deal_name="Test")

    def test_odoo_customer_id_required(self):
        with pytest.raises(ValidationError):
            OdooCustomerSource(name="Test")

    def test_odoo_customer_name_required(self):
        with pytest.raises(ValidationError):
            OdooCustomerSource(id=1)

    def test_rest_customer_id_required(self):
        with pytest.raises(ValidationError):
            RestCustomerSource(name="Test")

    def test_rest_customer_name_required(self):
        with pytest.raises(ValidationError):
            RestCustomerSource(id="cust-001")


# ---------------------------------------------------------------------------
# 4. Invalid types rejected
# ---------------------------------------------------------------------------


class TestInvalidTypes:
    """Source schemas must reject invalid types."""

    def test_odoo_id_rejects_string(self):
        with pytest.raises(ValidationError):
            OdooCustomerSource(id="not-an-int", name="Test")

    def test_odoo_expected_revenue_rejects_string(self):
        with pytest.raises(ValidationError):
            OdooDealSource(id=1, name="Test", expected_revenue="not-a-number")


# ---------------------------------------------------------------------------
# 5. Nullable/optional fields
# ---------------------------------------------------------------------------


class TestNullableOptionalFields:
    """Optional fields must accept None or be omittable."""

    def test_csv_customer_minimal(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Minimal",
        )
        assert cust.email_address is None
        assert cust.customer_segment is None
        assert cust.industry_name is None
        assert cust.account_owner_id is None
        assert cust.status is None
        assert cust.created_date is None

    def test_odoo_customer_minimal(self):
        cust = OdooCustomerSource(id=1, name="Minimal")
        assert cust.email is None
        assert cust.x_studio_segment is None
        assert cust.industry_id is None
        assert cust.user_id is None
        assert cust.active is None
        assert cust.create_date is None
        assert cust.customer_rank is None

    def test_rest_customer_minimal(self):
        cust = RestCustomerSource(id="cust-001", name="Minimal")
        assert cust.email is None
        assert cust.segment is None
        assert cust.ownerId is None

    def test_csv_support_ticket_minimal(self):
        ticket = CsvSupportTicketSource(ticket_id="TKT-001")
        assert ticket.customer_id is None
        assert ticket.subject is None
        assert ticket.description is None


# ---------------------------------------------------------------------------
# 6. Source ID preserved exactly (no UUID conversion)
# ---------------------------------------------------------------------------


class TestSourceIdPreserved:
    """Source IDs must remain source-native, never converted to UUID."""

    def test_csv_customer_id_is_string(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
        )
        assert isinstance(cust.customer_id, str)
        assert cust.customer_id == "CUST-001"

    def test_odoo_customer_id_is_int(self):
        cust = OdooCustomerSource(id=42, name="Test")
        assert isinstance(cust.id, int)
        assert cust.id == 42

    def test_rest_customer_id_is_string(self):
        cust = RestCustomerSource(id="cust-042", name="Test")
        assert isinstance(cust.id, str)
        assert cust.id == "cust-042"

    def test_csv_id_not_uuid(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
        )
        with pytest.raises(ValueError):
            uuid.UUID(cust.customer_id)

    def test_rest_id_not_uuid(self):
        cust = RestCustomerSource(id="cust-001", name="Test")
        with pytest.raises(ValueError):
            uuid.UUID(cust.id)


# ---------------------------------------------------------------------------
# 7. Source-native status values preserved
# ---------------------------------------------------------------------------


class TestSourceNativeValues:
    """Source status/stage values must remain source-native."""

    def test_odoo_priority_is_source_native(self):
        ticket = OdooSupportTicketSource(
            id=1,
            priority="2",
        )
        assert ticket.priority == "2"

    def test_csv_status_is_source_native(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
            status="ACTIVE",
        )
        assert cust.status == "ACTIVE"

    def test_rest_status_is_source_native(self):
        org = RestOrganizationSource(
            id="org-001",
            name="Test",
            status="enabled",
        )
        assert org.status == "enabled"


# ---------------------------------------------------------------------------
# 8. Source-native relationship keys preserved
# ---------------------------------------------------------------------------


class TestSourceRelationshipKeys:
    """Source relationship keys must remain source references."""

    def test_csv_deal_customer_id_is_source_key(self):
        deal = CsvDealSource(
            deal_id="DEAL-001",
            deal_name="Test",
            customer_id="CUST-042",
        )
        assert deal.customer_id == "CUST-042"

    def test_odoo_deal_partner_id_is_int(self):
        deal = OdooDealSource(
            id=1,
            name="Test",
            partner_id=42,
        )
        assert isinstance(deal.partner_id, int)
        assert deal.partner_id == 42

    def test_rest_deal_customer_id_is_string(self):
        deal = RestDealSource(
            id="deal-001",
            name="Test",
            customerId="cust-042",
        )
        assert deal.customerId == "cust-042"

    def test_csv_employee_manager_id_preserved(self):
        emp = CsvEmployeeSource(
            employee_id="EMP-001",
            employee_name="Test",
            manager_id="EMP-MGR-010",
        )
        assert emp.manager_id == "EMP-MGR-010"

    def test_odoo_employee_parent_id_preserved(self):
        emp = OdooEmployeeSource(
            id=1,
            name="Test",
            parent_id=10,
        )
        assert emp.parent_id == 10


# ---------------------------------------------------------------------------
# 9. No whitespace transformation
# ---------------------------------------------------------------------------


class TestNoWhitespaceTransformation:
    """Source schemas must NOT strip whitespace."""

    def test_csv_name_whitespace_preserved(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="  Widget Inc  ",
        )
        assert cust.customer_name == "  Widget Inc  "

    def test_odoo_name_whitespace_preserved(self):
        cust = OdooCustomerSource(
            id=1,
            name="  Widget Inc  ",
        )
        assert cust.name == "  Widget Inc  "

    def test_rest_name_whitespace_preserved(self):
        cust = RestCustomerSource(
            id="cust-001",
            name="  Widget Inc  ",
        )
        assert cust.name == "  Widget Inc  "

    def test_csv_email_whitespace_preserved(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
            email_address="  alice@acme.com  ",
        )
        assert cust.email_address == "  alice@acme.com  "


# ---------------------------------------------------------------------------
# 10-12. No canonical conversions or inventions
# ---------------------------------------------------------------------------


class TestNoCanonicalConversions:
    """Source schemas must not contain canonical-only fields."""

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_canonical_id_field(self, schema_cls):
        """No source schema should have a UUID 'id' that is canonical."""
        fields = schema_cls.model_fields
        if "id" in fields:
            field_type = fields["id"].annotation
            assert field_type is not uuid.UUID, (
                f"{schema_cls.__name__} has UUID id, should be source-native"
            )

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_ingestion_run_id(self, schema_cls):
        assert "ingestion_run_id" not in schema_cls.model_fields, (
            f"{schema_cls.__name__} has ingestion_run_id"
        )

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_ingested_at(self, schema_cls):
        assert "ingested_at" not in schema_cls.model_fields, (
            f"{schema_cls.__name__} has ingested_at"
        )

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_record_hash(self, schema_cls):
        assert "record_hash" not in schema_cls.model_fields, (
            f"{schema_cls.__name__} has record_hash"
        )

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_source_system(self, schema_cls):
        """source_system is a canonical provenance field, not a source field."""
        assert "source_system" not in schema_cls.model_fields, (
            f"{schema_cls.__name__} has source_system"
        )

    @pytest.mark.parametrize("schema_cls", ALL_SOURCE_SCHEMAS)
    def test_no_source_entity(self, schema_cls):
        """source_entity is a canonical provenance field, not a source field."""
        assert "source_entity" not in schema_cls.model_fields, (
            f"{schema_cls.__name__} has source_entity"
        )


# ---------------------------------------------------------------------------
# 13. Unknown-field behavior
# ---------------------------------------------------------------------------


class TestUnknownFieldPolicy:
    """Source schemas must ignore unknown fields (extra='ignore')."""

    def test_extra_fields_ignored_csv(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
            some_unknown_field="should be ignored",
            another_field="also ignored",
        )
        assert not hasattr(cust, "some_unknown_field")
        assert cust.customer_id == "CUST-001"

    def test_extra_fields_ignored_odoo(self):
        cust = OdooCustomerSource(
            id=1,
            name="Test",
            x_custom_field="ignored",
        )
        assert not hasattr(cust, "x_custom_field")

    def test_extra_fields_ignored_rest(self):
        cust = RestCustomerSource(
            id="cust-001",
            name="Test",
            extraApiField="ignored",
        )
        assert not hasattr(cust, "extraApiField")

    def test_extra_config_is_ignore(self):
        assert SourceBase.model_config.get("extra") == "ignore"


# ---------------------------------------------------------------------------
# 14. Timestamp behavior (source-native)
# ---------------------------------------------------------------------------


class TestTimestampSourceNative:
    """Source timestamps must remain in source-native format."""

    def test_csv_dates_are_strings(self):
        cust = CsvCustomerSource(
            customer_id="CUST-001",
            customer_name="Test",
            created_date="15/01/2024",
        )
        assert isinstance(cust.created_date, str)
        assert cust.created_date == "15/01/2024"

    def test_odoo_dates_are_strings(self):
        cust = OdooCustomerSource(
            id=1,
            name="Test",
            create_date="2024-01-15 10:30:00",
        )
        assert isinstance(cust.create_date, str)
        assert cust.create_date == "2024-01-15 10:30:00"

    def test_rest_dates_are_strings(self):
        cust = RestCustomerSource(
            id="cust-001",
            name="Test",
            createdAt="2024-01-15T10:30:00Z",
        )
        assert isinstance(cust.createdAt, str)
        assert cust.createdAt == "2024-01-15T10:30:00Z"


# ---------------------------------------------------------------------------
# 15. Monetary source representation
# ---------------------------------------------------------------------------


class TestMonetarySourceRepresentation:
    """Source monetary values must remain in source-native types."""

    def test_csv_amount_is_string(self):
        deal = CsvDealSource(
            deal_id="DEAL-001",
            deal_name="Test",
            amount="1,50,000.50",
        )
        assert isinstance(deal.amount, str)
        assert deal.amount == "1,50,000.50"

    def test_odoo_amount_is_float(self):
        deal = OdooDealSource(
            id=1,
            name="Test",
            expected_revenue=150000.50,
        )
        assert isinstance(deal.expected_revenue, float)

    def test_rest_amount_is_float(self):
        deal = RestDealSource(
            id="deal-001",
            name="Test",
            amount=150000.50,
        )
        assert isinstance(deal.amount, float)


# ---------------------------------------------------------------------------
# 16. Long document text
# ---------------------------------------------------------------------------


class TestLongDocumentText:
    """Source document body must survive without truncation."""

    def test_csv_document_long_body(self):
        body = "x" * 100_000
        doc = CsvDocumentSource(
            document_id="DOC-001",
            body_text=body,
        )
        assert len(doc.body_text) == 100_000

    def test_odoo_document_long_datas(self):
        body = "y" * 100_000
        doc = OdooDocumentSource(
            id=1,
            datas=body,
        )
        assert len(doc.datas) == 100_000

    def test_rest_document_long_body(self):
        body = "z" * 100_000
        doc = RestDocumentSource(
            id="doc-001",
            bodyText=body,
        )
        assert len(doc.bodyText) == 100_000


# ---------------------------------------------------------------------------
# 28. Cross-contract tests (B3 != B2)
# ---------------------------------------------------------------------------


class TestCrossContractSeparation:
    """B3 source schemas must NOT be canonical schemas."""

    def test_source_base_is_not_canonical_base(self):
        from app.schemas.canonical.common import CanonicalBase
        assert not issubclass(SourceBase, CanonicalBase)

    def test_csv_customer_is_not_canonical_customer(self):
        from app.schemas.canonical.customer import CustomerCanonical
        assert not issubclass(CsvCustomerSource, CustomerCanonical)

    def test_odoo_customer_is_not_canonical_customer(self):
        from app.schemas.canonical.customer import CustomerCanonical
        assert not issubclass(OdooCustomerSource, CustomerCanonical)

    def test_csv_customer_has_source_native_fields(self):
        """CSV customer uses 'customer_name', not canonical 'name'."""
        assert "customer_name" in CsvCustomerSource.model_fields
        assert "name" not in CsvCustomerSource.model_fields

    def test_odoo_customer_has_source_native_fields(self):
        """Odoo customer uses 'x_studio_segment', not canonical 'segment'."""
        assert "x_studio_segment" in OdooCustomerSource.model_fields
        assert "segment" not in OdooCustomerSource.model_fields

    def test_csv_deal_has_source_native_amount(self):
        """CSV deal amount is string, canonical is Decimal."""
        from app.schemas.canonical.deal import DealCanonical
        csv_type = CsvDealSource.model_fields["amount"].annotation
        canon_type = DealCanonical.model_fields["amount"].annotation
        assert csv_type != canon_type

    def test_odoo_deal_uses_partner_id_not_customer_id(self):
        """Odoo uses partner_id, not canonical customer_id."""
        assert "partner_id" in OdooDealSource.model_fields
        assert "customer_id" not in OdooDealSource.model_fields

    def test_rest_deal_uses_camelCase(self):
        """REST uses camelCase, not canonical snake_case."""
        assert "customerId" in RestDealSource.model_fields
        assert "customer_id" not in RestDealSource.model_fields

    def test_source_has_no_from_attributes(self):
        """Source schemas don't need ORM compatibility."""
        assert SourceBase.model_config.get("from_attributes") is not True

    def test_canonical_has_no_extra_ignore(self):
        """Canonical schemas don't use extra='ignore'."""
        from app.schemas.canonical.common import CanonicalBase
        assert CanonicalBase.model_config.get("extra") != "ignore"
