"""
Odoo source schemas.

Represents the JSON payload structure returned by the Odoo-style
mock REST endpoints (/odoo/...). Field names use Odoo conventions
(e.g. partner_id, x_studio_segment) to demonstrate that source
schemas preserve source-native naming.

The Odoo mock (C3) will return typed JSON, so fields have
appropriate Python types rather than being all-string like CSV.
Normalization (D1) maps these to canonical field names and values.
"""

from app.schemas.source.common import SourceBase


class OdooOrganizationSource(SourceBase):
    """Odoo company/organization record."""

    id: int
    name: str
    industry_id: str | None = None
    country_id: str | None = None
    active: bool | None = None


class OdooEmployeeSource(SourceBase):
    """Odoo hr.employee record."""

    id: int
    name: str
    work_email: str | None = None
    department_id: str | None = None
    job_title: str | None = None
    parent_id: int | None = None
    active: bool | None = None
    x_hire_date: str | None = None
    company_id: int | None = None


class OdooCustomerSource(SourceBase):
    """
    Odoo res.partner record (customer type).

    Odoo uses 'partner' for both customers and suppliers.
    The 'customer_rank' field distinguishes them.
    """

    id: int
    name: str
    email: str | None = None
    x_studio_segment: str | None = None
    industry_id: str | None = None
    user_id: int | None = None
    active: bool | None = None
    create_date: str | None = None
    customer_rank: int | None = None


class OdooDealSource(SourceBase):
    """Odoo crm.lead record (opportunity)."""

    id: int
    name: str
    partner_id: int | None = None
    user_id: int | None = None
    stage_id: str | None = None
    expected_revenue: float | None = None
    company_currency: str | None = None
    probability: float | None = None
    date_deadline: str | None = None
    active: bool | None = None


class OdooProjectSource(SourceBase):
    """Odoo project.project record."""

    id: int
    name: str
    partner_id: int | None = None
    user_id: int | None = None
    stage_id: str | None = None
    date_start: str | None = None
    date: str | None = None
    x_budget: float | None = None
    active: bool | None = None


class OdooSupportTicketSource(SourceBase):
    """Odoo helpdesk.ticket record."""

    id: int
    partner_id: int | None = None
    user_id: int | None = None
    priority: str | None = None
    stage_id: str | None = None
    category_id: str | None = None
    name: str | None = None
    description: str | None = None
    create_date: str | None = None
    close_date: str | None = None


class OdooDocumentSource(SourceBase):
    """Odoo documents.document record."""

    id: int
    name: str | None = None
    type: str | None = None
    datas: str | None = None
    url: str | None = None
    owner_id: int | None = None
    create_date: str | None = None
    write_date: str | None = None
