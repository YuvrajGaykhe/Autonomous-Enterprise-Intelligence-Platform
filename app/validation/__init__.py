"""
D2 Validation and quarantine package for Layer 1.

D1 turns source-specific data into canonical records. D2 validates canonical
records and partitions every batch into valid records OR quarantine records:

    DATA failure   -> QuarantineRecord (structured, redacted, batch continues)
    SYSTEM failure -> exception (configuration, programming, or invariant fault)

Public API:
    validate_source_batch     D1 normalization + D2 validation of source records
    validate_canonical_batch  D2 validation of canonical records
    QualityGateResult, QuarantineRecord, QualityFinding
    load_validation_config / default_validation_config / ValidationConfig
"""

from app.validation.config import (
    ValidationConfig,
    default_validation_config,
    load_validation_config,
)
from app.validation.errors import (
    DATA_FAILURE_CODES,
    SYSTEM_FAILURE_CODES,
    CanonicalInvariantError,
    QualityCode,
    QualityGateSystemError,
    Severity,
    Stage,
    SystemFailureCode,
    ValidationConfigError,
    is_data_failure,
)
from app.validation.gate import QualityGateResult, validate_canonical_batch, validate_source_batch
from app.validation.quarantine import QualityFinding, QuarantineRecord

__all__ = [
    "validate_source_batch",
    "validate_canonical_batch",
    "QualityGateResult",
    "QuarantineRecord",
    "QualityFinding",
    "ValidationConfig",
    "default_validation_config",
    "load_validation_config",
    "Severity",
    "Stage",
    "QualityCode",
    "SystemFailureCode",
    "DATA_FAILURE_CODES",
    "SYSTEM_FAILURE_CODES",
    "is_data_failure",
    "QualityGateSystemError",
    "CanonicalInvariantError",
    "ValidationConfigError",
]
