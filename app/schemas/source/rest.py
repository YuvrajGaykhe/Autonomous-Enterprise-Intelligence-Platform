"""
Generic REST source schemas.

Represents the JSON payload structure from a generic REST API.
The Generic REST connector (C5) is configurable with arbitrary
base URLs and endpoints. These schemas define a reasonable
default JSON payload contract that the REST adapter produces.

Field names use common REST/API conventions (e.g. camelCase IDs,
standard JSON types). The actual field mapping is configurable
per-source through the connector configuration.

Since REST APIs return typed JSON, fields have appropriate Python
types. Normalization (D1) maps these to canonical field names.
"""

from app.schemas.source.common import SourceBase


class RestOrganizationSource(SourceBase):
    """Generic REST organization payload."""

    id: str
    name: str
    industry: str | None = None
    country: str | None = None
    status: str | None = None


class RestEmployeeSource(SourceBase):
    """Generic REST employee payload."""

    id: str
    name: str
    email: str | None = None
    department: str | None = None
    title: str | None = None
    managerId: str | None = None
    status: str | None = None
    hireDate: str | None = None
    isActive: bool | None = None
    organizationId: str | None = None


class RestCustomerSource(SourceBase):
    """Generic REST customer payload."""

    id: str
    name: str
    email: str | None = None
    segment: str | None = None
    industry: str | None = None
    ownerId: str | None = None
    status: str | None = None
    createdAt: str | None = None
    isActive: bool | None = None


class RestDealSource(SourceBase):
    """Generic REST deal/opportunity payload."""

    id: str
    name: str
    customerId: str | None = None
    ownerId: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    probability: float | None = None
    expectedCloseDate: str | None = None
    isActive: bool | None = None


class RestProjectSource(SourceBase):
    """Generic REST project payload."""

    id: str
    name: str
    customerId: str | None = None
    ownerId: str | None = None
    status: str | None = None
    startDate: str | None = None
    endDate: str | None = None
    budget: float | None = None
    isActive: bool | None = None


class RestSupportTicketSource(SourceBase):
    """Generic REST support ticket payload."""

    id: str
    customerId: str | None = None
    assigneeId: str | None = None
    priority: str | None = None
    status: str | None = None
    category: str | None = None
    subject: str | None = None
    description: str | None = None
    createdAt: str | None = None
    resolvedAt: str | None = None


class RestDocumentSource(SourceBase):
    """Generic REST document payload."""

    id: str
    title: str | None = None
    documentType: str | None = None
    bodyText: str | None = None
    sourceUri: str | None = None
    ownerId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
