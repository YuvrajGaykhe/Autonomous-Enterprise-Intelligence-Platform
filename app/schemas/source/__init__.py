"""
Source schema package for Layer 1.

Provides source-specific Pydantic schemas for the three source
systems: CSV, Odoo mock, and Generic REST. These represent raw
source payloads BEFORE normalization into canonical schemas.
"""

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

__all__ = [
    "SourceBase",
    # CSV
    "CsvOrganizationSource",
    "CsvEmployeeSource",
    "CsvCustomerSource",
    "CsvDealSource",
    "CsvProjectSource",
    "CsvSupportTicketSource",
    "CsvDocumentSource",
    # Odoo
    "OdooOrganizationSource",
    "OdooEmployeeSource",
    "OdooCustomerSource",
    "OdooDealSource",
    "OdooProjectSource",
    "OdooSupportTicketSource",
    "OdooDocumentSource",
    # REST
    "RestOrganizationSource",
    "RestEmployeeSource",
    "RestCustomerSource",
    "RestDealSource",
    "RestProjectSource",
    "RestSupportTicketSource",
    "RestDocumentSource",
]
