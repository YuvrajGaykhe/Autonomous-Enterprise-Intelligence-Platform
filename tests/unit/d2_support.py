"""Shared helpers for the D2 validation and quarantine test modules."""

from __future__ import annotations

import copy
import json

from d1_support import ABSENT, INGESTED_AT, RUN_ID, full_case, with_value

from app.normalization import normalize
from app.validation import QualityGateResult, validate_source_batch

SECRET_TOKEN = "TEST_CREDENTIAL_VALUE_FOR_REDACTION"


def canonical(source: str = "csv_demo", entity: str = "deals"):
    """Real D1 canonical output for a fully populated fixture."""
    record, _ = full_case(source, entity)
    return normalize(source, entity, record, RUN_ID, INGESTED_AT)


def tamper(record, **updates):
    """Copy a canonical record with updated values, bypassing validation."""
    return record.model_copy(update=updates)


def fingerprint(result: QualityGateResult) -> str:
    """Deterministic JSON fingerprint of a quality gate result."""
    return json.dumps(
        {
            "summary": result.summary(),
            "valid": [record.model_dump(mode="json") for record in result.valid],
            "quarantined": [record.to_dict() for record in result.quarantined],
            "warnings": [finding.to_dict() for finding in result.warnings],
        },
        sort_keys=True,
    )


def mixed_customer_batch() -> list[object]:
    """Valid, invalid, non-mapping, warning, duplicate, and secret-bearing records."""
    good, _ = full_case("csv_demo", "customers")
    churned = with_value(with_value(good, "customer_id", "CUST-003"), "status", "churned")
    churned["api_key"] = f"Bearer {SECRET_TOKEN}"
    churned["tags"] = {"vip", "apac", "renewal"}
    return [
        good,
        with_value(good, "customer_name", ABSENT),
        None,
        with_value(with_value(good, "customer_id", "CUST-002"), "email_address", ""),
        copy.deepcopy(good),
        churned,
    ]


def mixed_customer_fingerprint() -> str:
    return fingerprint(validate_source_batch("csv_demo", "customers", mixed_customer_batch(),
                                             RUN_ID, INGESTED_AT))
