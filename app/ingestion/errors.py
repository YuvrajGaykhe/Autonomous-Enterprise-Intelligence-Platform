"""
Stable E1 finding codes and exceptions.

D1 ErrorCode and D2 QualityCode values are persisted verbatim for
quarantined records and D2 warnings; the codes below are the findings E1
itself produces in ingestion_errors.error_code.
"""

from __future__ import annotations

from enum import StrEnum


class IngestionCode(StrEnum):
    """E1-specific finding codes."""

    # A canonical source key does not resolve to a persisted parent from the
    # same source system; the canonical FK is left null (context decision:
    # "Canonical FK = NULL + source_id preserved + WARNING").
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
    # The connector health check failed or raised; no entity was fetched.
    CONNECTOR_UNHEALTHY = "CONNECTOR_UNHEALTHY"
    # The connector raised while fetching an entity page.
    CONNECTOR_FAILED = "CONNECTOR_FAILED"
    # A batch transaction was rolled back by a database integrity/data error.
    BATCH_FAILED = "BATCH_FAILED"


class IngestionRequestError(ValueError):
    """The ingestion request is invalid for this connector; no run is created."""


class ConnectorContractError(Exception):
    """A connector returned a result that violates the SourceConnector contract.

    This is a system failure (a connector defect), never a data failure.
    """
