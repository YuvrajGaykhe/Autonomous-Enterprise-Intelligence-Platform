"""
Type coercion utilities for D1 normalization.

Converts source-native values to canonical Python types according to
the spec's type normalization rules (Section 7).

Design principles:
    - Explicit, not magical. Each coercion function has a clear contract.
    - Never guess silently. Ambiguous values raise CoercionError.
    - Preserve semantics. None stays None. Zero stays zero. False stays
      False. Empty string becomes None only when it represents a missing
      value (null token), not when it represents an intentional empty value.
    - No lossy rounding. Decimal values are parsed from string
      representations to preserve precision.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.normalization.errors import CoercionError


# Tokens that should be treated as null/missing.
# Spec Section 7: "NULL / N/A / - / empty -> Map configured null tokens to null."
_NULL_TOKENS = frozenset({
    "",
    "null",
    "none",
    "n/a",
    "na",
    "-",
    "nil",
})

# Accepted boolean truthy values.
# Spec Section 7: "true / True / yes / 1 -> Normalize to boolean using
# explicit accepted values."
_TRUE_TOKENS = frozenset({"true", "yes", "1"})
_FALSE_TOKENS = frozenset({"false", "no", "0"})


def coerce_str(value: object) -> str | None:
    """Coerce a value to a string, mapping null tokens to None.

    Whitespace-only strings are treated as null tokens per the spec's
    "empty" null token rule.

    Args:
        value: Source value.

    Returns:
        String value, or None if the value is a null token.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NULL_TOKENS:
        return None
    return s


def coerce_email(value: object) -> str | None:
    """Coerce an email value: trim whitespace and lowercase.

    Spec Section 7: "Emails with surrounding spaces -> Trim and lowercase
    for normalized comparison."

    Args:
        value: Source email value.

    Returns:
        Lowercased, trimmed email string, or None.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NULL_TOKENS:
        return None
    return s.lower()


def coerce_bool(value: object) -> bool | None:
    """Coerce a value to a boolean.

    Spec Section 7: "true / True / yes / 1 -> Normalize to boolean
    using explicit accepted values."

    Accepts Python bool directly, or string representations.
    None and null tokens return None.

    Args:
        value: Source value.

    Returns:
        Boolean value, or None if null.

    Raises:
        CoercionError: If the value is not a recognized boolean.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in _NULL_TOKENS:
        return None
    if s in _TRUE_TOKENS:
        return True
    if s in _FALSE_TOKENS:
        return False
    raise CoercionError(
        f"Cannot coerce '{value}' to boolean",
        field_name=None,
        raw_value=value,
        target_type="bool",
    )


def coerce_date(value: object) -> date | None:
    """Coerce a value to a date.

    Supports ISO 8601 format (YYYY-MM-DD). Rejects ambiguous formats
    per spec: "Parse using source-specific format configuration; reject
    ambiguous values."

    Args:
        value: Source date value (string or date).

    Returns:
        date object, or None if null.

    Raises:
        CoercionError: If the value cannot be parsed as a date.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s.lower() in _NULL_TOKENS:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        raise CoercionError(
            f"Cannot coerce '{value}' to date (expected YYYY-MM-DD)",
            field_name=None,
            raw_value=value,
            target_type="date",
        ) from exc


def coerce_datetime(value: object) -> datetime | None:
    """Coerce a value to a datetime.

    Supports ISO 8601 formats. If only a date is provided (YYYY-MM-DD),
    it is promoted to midnight UTC-naive datetime for compatibility.

    Args:
        value: Source datetime value (string or datetime).

    Returns:
        datetime object, or None if null.

    Raises:
        CoercionError: If the value cannot be parsed as a datetime.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    s = str(value).strip()
    if s.lower() in _NULL_TOKENS:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError) as exc:
        # Try date-only format and promote to datetime
        try:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day)
        except (ValueError, TypeError):
            pass
        raise CoercionError(
            f"Cannot coerce '{value}' to datetime",
            field_name=None,
            raw_value=value,
            target_type="datetime",
        ) from exc


def coerce_decimal(value: object) -> Decimal | None:
    """Coerce a value to Decimal for fixed-precision financial values.

    Spec Section 7: "Store numeric amount + ISO currency code separately."
    Never guess locale silently. Does NOT silently round.

    Accepts: int, float, Decimal, numeric strings.
    Float values are converted via str(float) to preserve the displayed
    representation rather than the binary floating-point bits.

    Args:
        value: Source numeric value.

    Returns:
        Decimal value, or None if null.

    Raises:
        CoercionError: If the value cannot be parsed as a number.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        # Prevent bool being treated as int
        raise CoercionError(
            f"Cannot coerce boolean '{value}' to Decimal",
            field_name=None,
            raw_value=value,
            target_type="Decimal",
        )
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise CoercionError(
                f"Cannot coerce '{value}' to Decimal",
                field_name=None,
                raw_value=value,
                target_type="Decimal",
            ) from exc
    s = str(value).strip()
    if s.lower() in _NULL_TOKENS:
        return None
    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise CoercionError(
            f"Cannot coerce '{value}' to Decimal",
            field_name=None,
            raw_value=value,
            target_type="Decimal",
        ) from exc


def coerce_int_id_to_str(value: object) -> str | None:
    """Convert an integer source ID (e.g. Odoo) to its string representation.

    Odoo uses integer IDs; canonical source_id is always a string.

    Args:
        value: Source integer ID.

    Returns:
        String representation, or None if null.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CoercionError(
            f"Cannot coerce boolean '{value}' to string ID",
            field_name=None,
            raw_value=value,
            target_type="str",
        )
    return str(value)
