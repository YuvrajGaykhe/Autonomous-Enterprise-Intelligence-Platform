"""
D1 Normalization package for Layer 1.

Public API:
    normalize: Convert a single source-native record to canonical form.
    normalize_batch: Convert a batch of records, collecting errors separately.
    canonical_id: Generate a deterministic UUID for a source identity triple.
    record_hash: Compute SHA-256 over canonical business fields.

Exception hierarchy:
    NormalizationError
        UnsupportedSourceError
        UnsupportedEntityError
        FieldMappingError
        CoercionError
"""

from app.normalization.errors import (
    CoercionError,
    FieldMappingError,
    NormalizationError,
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
    "NormalizationError",
    "UnsupportedSourceError",
    "UnsupportedEntityError",
    "FieldMappingError",
    "CoercionError",
]
