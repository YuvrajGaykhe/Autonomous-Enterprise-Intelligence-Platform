"""
D1 Normalization package for Layer 1.

Public API:
    normalize:        Convert one source-native record to canonical form.
    normalize_batch:  Convert a batch, collecting per-record errors.
    canonical_id:     Deterministic UUID for a source identity triple.
    record_hash:      SHA-256 of a canonical record's business content.
    load_config / default_config / NormalizationConfig:
                      Centralized normalization configuration
                      (config/mappings/).

Exception hierarchy (all carry a stable ErrorCode and record context):
    NormalizationError
        UnsupportedSourceError
        UnsupportedEntityError
        InvalidRecordError
        IdentifierError
        FieldMappingError
        CoercionError
        SchemaValidationError
    NormalizationConfigError (configuration fault, not a record error)
"""

from app.normalization.config import NormalizationConfig, default_config, load_config
from app.normalization.errors import (
    CoercionError,
    ErrorCode,
    FieldMappingError,
    IdentifierError,
    InvalidRecordError,
    NormalizationConfigError,
    NormalizationError,
    SchemaValidationError,
    UnsupportedEntityError,
    UnsupportedSourceError,
)
from app.normalization.identifiers import canonical_id, record_hash
from app.normalization.pipeline import normalize, normalize_batch

__all__ = [
    "normalize",
    "normalize_batch",
    "canonical_id",
    "record_hash",
    "NormalizationConfig",
    "default_config",
    "load_config",
    "ErrorCode",
    "NormalizationError",
    "UnsupportedSourceError",
    "UnsupportedEntityError",
    "InvalidRecordError",
    "IdentifierError",
    "FieldMappingError",
    "CoercionError",
    "SchemaValidationError",
    "NormalizationConfigError",
]
