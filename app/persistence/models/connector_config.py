"""
ConnectorConfig operational model.

Stores non-secret connector configuration. Secrets MUST NOT be stored
here. The project architecture requires: secrets -> environment variables.

Secret env var names may be referenced (e.g. "ODOO_API_KEY") but the
actual secret values are never persisted in this table.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConnectorConfig(Base):
    __tablename__ = "connector_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    source_name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Unique logical name for this source, e.g. csv_demo",
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Connector type: csv, odoo_mock, rest",
    )
    base_url: Mapped[str | None] = mapped_column(
        String(1000), nullable=True,
        comment="Base URL for HTTP-based connectors",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Non-secret connector parameters (mappings, paths, etc.)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
