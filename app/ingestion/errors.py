"""
Stable E1 finding codes persisted in ingestion_errors.error_code.

D1 ErrorCode and D2 QualityCode values are persisted verbatim for
quarantined records and D2 warnings; the codes below are the findings E1
itself produces.
"""

from __future__ import annotations

from enum import StrEnum


class IngestionCode(StrEnum):
    """E1-specific finding codes."""

    # A canonical source key does not resolve to a persisted parent from the
    # same source system; the canonical FK is left null (context decision:
    # "Canonical FK = NULL + source_id preserved + WARNING").
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
