"""
Normalization exception hierarchy for Layer 1.

These exceptions are raised by the D1 normalization pipeline when
source-native payloads cannot be converted to canonical form.

They are intentionally separate from the connector exception hierarchy
(ConnectorError and subclasses) because normalization failures are
a different failure category: the data was successfully fetched but
cannot be transformed.

Hierarchy:
    NormalizationError
        UnsupportedSourceError
        UnsupportedEntityError
        FieldMappingError
        CoercionError
"""

from __future__ import annotations


class NormalizationError(Exception):
    """Base exception for all normalization failures.

    Attributes:
        source_system: Which source produced the record (if known).
        entity_type: Which entity was being normalized (if known).
        source_id: Source record identifier (if known).
    """

    def __init__(
        self,
        message: str,
        source_system: str | None = None,
        entity_type: str | None = None,
        source_id: str | None = None,
    ) -> None:
        self.source_system = source_system
        self.entity_type = entity_type
        self.source_id = source_id
        super().__init__(message)


class UnsupportedSourceError(NormalizationError):
    """Raised when the source_system is not recognized by the normalizer."""


class UnsupportedEntityError(NormalizationError):
    """Raised when the entity_type is not supported for a given source."""


class FieldMappingError(NormalizationError):
    """Raised when a required field is missing or cannot be mapped.

    Attributes:
        field_name: The canonical or source field that caused the error.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        **kwargs: str | None,
    ) -> None:
        self.field_name = field_name
        super().__init__(message, **kwargs)


class CoercionError(NormalizationError):
    """Raised when a value cannot be converted to the required canonical type.

    Attributes:
        field_name: The field being coerced.
        raw_value: The original value that failed coercion.
        target_type: The type it was being converted to.
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        raw_value: object = None,
        target_type: str | None = None,
        **kwargs: str | None,
    ) -> None:
        self.field_name = field_name
        self.raw_value = raw_value
        self.target_type = target_type
        super().__init__(message, **kwargs)
