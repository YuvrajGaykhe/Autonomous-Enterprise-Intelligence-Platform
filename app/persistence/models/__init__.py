"""
ORM model package for Layer 1.

Importing this module registers all 17 models with Base.metadata,
which is required for Alembic autogenerate to detect them.

Canonical entities (7): Organization, Employee, Customer, Deal,
                        Project, SupportTicket, Document

Operational tables (5): IngestionRun, IngestionError, SourceRecord,
                        ConnectorConfig, IngestionCursor

Layer 2 tables (5):     DocumentCustomerLink (VS-01 M4). Additive: it holds
                        derived links and changes no canonical table.
                        RiskAssessment, RiskPosition, RiskBrief (VS-01 M7).
                        Additive: they hold assessment results and change no
                        canonical table.
                        BriefDecision (VS-01 M8). Additive: it holds the
                        decisions recorded on briefs and changes no canonical
                        table.
"""

from app.persistence.models.organization import Organization
from app.persistence.models.employee import Employee
from app.persistence.models.customer import Customer
from app.persistence.models.deal import Deal
from app.persistence.models.project import Project
from app.persistence.models.support_ticket import SupportTicket
from app.persistence.models.document import Document
from app.persistence.models.ingestion_run import IngestionRun
from app.persistence.models.ingestion_error import IngestionError
from app.persistence.models.source_record import SourceRecord
from app.persistence.models.connector_config import ConnectorConfig
from app.persistence.models.ingestion_cursor import IngestionCursor
from app.persistence.models.document_customer_link import DocumentCustomerLink
from app.persistence.models.risk_assessment import RiskAssessment
from app.persistence.models.risk_position import RiskPosition
from app.persistence.models.risk_brief import RiskBrief
from app.persistence.models.brief_decision import BriefDecision

__all__ = [
    "Organization",
    "Employee",
    "Customer",
    "Deal",
    "Project",
    "SupportTicket",
    "Document",
    "IngestionRun",
    "IngestionError",
    "SourceRecord",
    "ConnectorConfig",
    "IngestionCursor",
    "DocumentCustomerLink",
    "RiskAssessment",
    "RiskPosition",
    "RiskBrief",
    "BriefDecision",
]
