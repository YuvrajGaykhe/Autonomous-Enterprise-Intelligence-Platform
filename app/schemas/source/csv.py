"""
CSV source schemas.

Represents the row structure of CSV files as they arrive from the
csv_demo source system. Column names match the spec's sample CSV
mapping configuration (Section 12, lines 625-636).

For example, the CSV has 'customer_name' not 'name', 'email_address'
not 'email'. These source-native names are preserved here.
Normalization (D1) maps them to canonical field names.

All fields are strings or None because CSV is inherently untyped.
Amounts, dates, and booleans arrive as strings and are converted
during normalization, not here.
"""

from app.schemas.source.common import SourceBase


class CsvOrganizationSource(SourceBase):
    """CSV row for an organization record."""

    organization_id: str
    organization_name: str
    industry: str | None = None
    country: str | None = None
    status: str | None = None


class CsvEmployeeSource(SourceBase):
    """CSV row for an employee record."""

    employee_id: str
    employee_name: str
    email_address: str | None = None
    department: str | None = None
    title: str | None = None
    manager_id: str | None = None
    status: str | None = None
    hire_date: str | None = None
    is_active: str | None = None
    organization_id: str | None = None


class CsvCustomerSource(SourceBase):
    """
    CSV row for a customer record.

    Column names match the spec's sample CSV mapping configuration:
        customer_id -> source_id
        customer_name -> name
        email_address -> email
        customer_segment -> segment
        industry_name -> industry
        account_owner_id -> owner_source_id
        status -> status
        created_date -> created_at
    """

    customer_id: str
    customer_name: str
    email_address: str | None = None
    customer_segment: str | None = None
    industry_name: str | None = None
    account_owner_id: str | None = None
    status: str | None = None
    created_date: str | None = None


class CsvDealSource(SourceBase):
    """CSV row for a deal record."""

    deal_id: str
    deal_name: str
    customer_id: str | None = None
    owner_id: str | None = None
    stage: str | None = None
    amount: str | None = None
    currency: str | None = None
    probability: str | None = None
    expected_close_date: str | None = None
    is_active: str | None = None


class CsvProjectSource(SourceBase):
    """CSV row for a project record."""

    project_id: str
    project_name: str
    customer_id: str | None = None
    owner_id: str | None = None
    status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    budget: str | None = None
    is_active: str | None = None


class CsvSupportTicketSource(SourceBase):
    """CSV row for a support ticket record."""

    ticket_id: str
    customer_id: str | None = None
    assignee_id: str | None = None
    priority: str | None = None
    status: str | None = None
    category: str | None = None
    subject: str | None = None
    description: str | None = None
    created_date: str | None = None
    resolved_date: str | None = None


class CsvDocumentSource(SourceBase):
    """CSV row for a document record."""

    document_id: str
    title: str | None = None
    document_type: str | None = None
    body_text: str | None = None
    source_uri: str | None = None
    owner_id: str | None = None
    created_date: str | None = None
    updated_date: str | None = None
