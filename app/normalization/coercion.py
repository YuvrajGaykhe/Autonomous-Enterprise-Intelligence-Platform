"""
Type coercion primitives for D1 normalization.

Every function is pure: its result is fully determined by the value and the
explicit rule parameters passed in (null tokens, formats, precision, ...),
which the pipeline takes from the centralized normalization configuration.

Principles (spec Section 7):
    - Never guess silently. Unrecognized or ambiguous input raises a
      NormalizationError subclass with a stable ErrorCode.
    - Explicit null handling. None and blank strings are null; configured
      null tokens are null for tokenized kinds. The caller decides whether
      null is acceptable for the canonical field.
    - Strict source types. Text kinds accept only str; a JSON number in a
      string field is an error, not a silent conversion.
    - No lossy conversion. Decimals are never rounded or truncated;
      datetimes are converted to UTC without changing the instant.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, tzinfo
from decimal import Context, Decimal, Inexact

from app.normalization.errors import (
    CoercionError,
    ErrorCode,
    IdentifierError,
    describe_value,
)

IDENTIFIER_TYPES = frozenset({"string", "integer"})

_ENUM_SEPARATORS = re.compile(r"[\s\-]+")


def _is_null(text: str, null_tokens: frozenset[str]) -> bool:
    stripped = text.strip()
    return not stripped or stripped.casefold() in null_tokens


def _require_str(value: object, kind: str) -> str:
    if not isinstance(value, str):
        raise CoercionError(
            f"expected a string for a {kind} value, got {type(value).__name__} "
            f"{describe_value(value)}",
            code=ErrorCode.INVALID_TYPE,
            raw_value=value,
        )
    return value


def coerce_string(value: object, *, null_tokens: frozenset[str]) -> str | None:
    """Trim a string; blank and null tokens become None."""
    if value is None:
        return None
    text = _require_str(value, "string")
    return None if _is_null(text, null_tokens) else text.strip()


def coerce_text(value: object) -> str | None:
    """Preserve free text exactly; only blank text becomes None.

    Null tokens are not applied: "N/A" inside a description is content.
    """
    if value is None:
        return None
    text = _require_str(value, "text")
    return text if text.strip() else None


def coerce_email(value: object, *, null_tokens: frozenset[str]) -> str | None:
    """Trim and lowercase an email for normalized comparison."""
    text = coerce_string(value, null_tokens=null_tokens)
    return None if text is None else text.lower()


def coerce_boolean(
    value: object,
    *,
    null_tokens: frozenset[str],
    true_tokens: frozenset[str],
    false_tokens: frozenset[str],
) -> bool | None:
    """Normalize a boolean using explicit accepted representations.

    Accepts bool, the integers 0 and 1, and configured string tokens
    (case-insensitive, trimmed). Everything else is rejected.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if _is_null(value, null_tokens):
            return None
        token = value.strip().casefold()
        if token in true_tokens:
            return True
        if token in false_tokens:
            return False
    raise CoercionError(
        f"cannot interpret {describe_value(value)} as a boolean",
        code=ErrorCode.INVALID_BOOLEAN,
        raw_value=value,
    )


def normalize_enum_token(text: str) -> str:
    """Lexically normalize an enum label: trim, casefold, spaces/hyphens -> '_'."""
    return _ENUM_SEPARATORS.sub("_", text.strip().casefold())


def coerce_enum(
    value: object,
    *,
    null_tokens: frozenset[str],
    allowed: frozenset[str],
    aliases: Mapping[str, str],
) -> str | None:
    """Map a source label to a canonical enum value; unknown labels are rejected."""
    if value is None:
        return None
    text = _require_str(value, "enum")
    if _is_null(text, null_tokens):
        return None
    token = normalize_enum_token(text)
    token = aliases.get(token, token)
    if token not in allowed:
        raise CoercionError(
            f"unknown value {describe_value(value)}; expected one of {sorted(allowed)}",
            code=ErrorCode.UNKNOWN_ENUM_VALUE,
            raw_value=value,
        )
    return token


def coerce_currency(
    value: object,
    *,
    null_tokens: frozenset[str],
    codes: frozenset[str],
    aliases: Mapping[str, str],
) -> str | None:
    """Normalize a currency to an uppercase ISO 4217 code."""
    if value is None:
        return None
    text = _require_str(value, "currency")
    if _is_null(text, null_tokens):
        return None
    stripped = text.strip()
    code = aliases.get(stripped, stripped.upper())
    if code not in codes:
        raise CoercionError(
            f"{describe_value(value)} is not a configured ISO 4217 currency code",
            code=ErrorCode.INVALID_CURRENCY,
            raw_value=value,
        )
    return code


def coerce_decimal(
    value: object,
    *,
    null_tokens: frozenset[str],
    precision: int,
    scale: int,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    decimal_separator: str = ".",
    thousands_separator: str | None = None,
) -> Decimal | None:
    """Normalize a fixed-precision decimal without rounding.

    The result is quantized to exactly ``scale`` fractional digits, which
    only adds or removes insignificant zeros. Values with more significant
    fractional digits than ``scale``, more integer digits than
    ``precision - scale``, or outside [minimum, maximum] are rejected.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CoercionError(
            f"cannot interpret boolean {value!r} as a decimal",
            code=ErrorCode.INVALID_TYPE,
            raw_value=value,
        )
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise CoercionError(
                f"non-finite number {value!r}",
                code=ErrorCode.INVALID_DECIMAL,
                raw_value=value,
            )
        number = Decimal(repr(value))
    elif isinstance(value, str):
        if _is_null(value, null_tokens):
            return None
        number = _parse_decimal_text(value, decimal_separator, thousands_separator)
    else:
        raise CoercionError(
            f"cannot interpret {type(value).__name__} {describe_value(value)} as a decimal",
            code=ErrorCode.INVALID_TYPE,
            raw_value=value,
        )

    if not number.is_finite():
        raise CoercionError(
            f"non-finite number {describe_value(value)}",
            code=ErrorCode.INVALID_DECIMAL,
            raw_value=value,
        )
    fractional_digits = _significant_fractional_digits(number)
    if fractional_digits > scale:
        raise CoercionError(
            f"{describe_value(value)} has {fractional_digits} fractional digits; "
            f"canonical scale is {scale} and values are never rounded",
            code=ErrorCode.DECIMAL_SCALE_EXCEEDED,
            raw_value=value,
        )
    if abs(number) >= Decimal(1).scaleb(precision - scale):
        raise CoercionError(
            f"{describe_value(value)} exceeds canonical precision "
            f"({precision}, {scale})",
            code=ErrorCode.DECIMAL_PRECISION_EXCEEDED,
            raw_value=value,
        )
    # Inexact is trapped: quantizing may only add or drop insignificant zeros.
    quantized = number.quantize(
        Decimal(1).scaleb(-scale), context=Context(prec=precision, traps=[Inexact])
    )
    if quantized.is_zero():
        quantized = abs(quantized)
    if (minimum is not None and quantized < minimum) or (
        maximum is not None and quantized > maximum
    ):
        raise CoercionError(
            f"{describe_value(value)} is outside the canonical range "
            f"[{minimum}, {maximum}]",
            code=ErrorCode.DECIMAL_OUT_OF_RANGE,
            raw_value=value,
        )
    return quantized


def _significant_fractional_digits(number: Decimal) -> int:
    """Count fractional digits excluding trailing zeros, without context rounding."""
    if number.is_zero():
        return 0
    _, digits, exponent = number.as_tuple()
    coefficient = "".join(str(digit) for digit in digits)
    trailing_zeros = len(coefficient) - len(coefficient.rstrip("0"))
    return max(0, -(exponent + trailing_zeros))


def _parse_decimal_text(
    text: str,
    decimal_separator: str,
    thousands_separator: str | None,
) -> Decimal:
    stripped = text.strip()
    if thousands_separator is None:
        integer_part = r"[0-9]+"
    else:
        sep = re.escape(thousands_separator)
        integer_part = rf"(?:[0-9]{{1,3}}(?:{sep}[0-9]{{3}})+|[0-9]+)"
    pattern = rf"[+-]?{integer_part}(?:{re.escape(decimal_separator)}[0-9]+)?"
    if not re.fullmatch(pattern, stripped):
        raise CoercionError(
            f"{describe_value(text)} is not a plain decimal number for this source "
            f"(decimal separator {decimal_separator!r}, "
            f"thousands separator {thousands_separator!r})",
            code=ErrorCode.INVALID_DECIMAL,
            raw_value=text,
        )
    if thousands_separator is not None:
        stripped = stripped.replace(thousands_separator, "")
    if decimal_separator != ".":
        stripped = stripped.replace(decimal_separator, ".")
    return Decimal(stripped)


def _parse_candidates(text: str, formats: tuple[str, ...]) -> list[datetime]:
    candidates = []
    for fmt in formats:
        try:
            candidates.append(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return candidates


def coerce_date(
    value: object,
    *,
    null_tokens: frozenset[str],
    formats: tuple[str, ...],
) -> date | None:
    """Parse a calendar date using the source's configured formats.

    A value matching several formats with different results is ambiguous
    and rejected (e.g. 03/04/2026 under both DD/MM and MM/DD).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        raise CoercionError(
            f"expected a date, got datetime {describe_value(value)}",
            code=ErrorCode.INVALID_TYPE,
            raw_value=value,
        )
    if isinstance(value, date):
        return value
    text = _require_str(value, "date")
    if _is_null(text, null_tokens):
        return None
    results = {candidate.date() for candidate in _parse_candidates(text.strip(), formats)}
    if not results:
        raise CoercionError(
            f"{describe_value(value)} does not match configured date formats {list(formats)}",
            code=ErrorCode.INVALID_DATE,
            raw_value=value,
        )
    if len(results) > 1:
        raise CoercionError(
            f"{describe_value(value)} is ambiguous under configured date formats",
            code=ErrorCode.AMBIGUOUS_DATE,
            raw_value=value,
        )
    return results.pop()


def coerce_datetime(
    value: object,
    *,
    null_tokens: frozenset[str],
    formats: tuple[str, ...],
    naive_timezone: tzinfo | None,
) -> datetime | None:
    """Parse a timestamp and return a timezone-aware UTC datetime.

    Aware inputs are converted to UTC. Naive inputs are interpreted in the
    source's configured ``naive_timezone``; if the source policy is to
    reject naive timestamps (``naive_timezone is None``) they raise
    NAIVE_DATETIME_REJECTED.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        candidates = [value]
    elif isinstance(value, date):
        raise CoercionError(
            f"expected a datetime, got date {describe_value(value)}",
            code=ErrorCode.INVALID_TYPE,
            raw_value=value,
        )
    else:
        text = _require_str(value, "datetime")
        if _is_null(text, null_tokens):
            return None
        candidates = _parse_candidates(text.strip(), formats)
        if not candidates:
            raise CoercionError(
                f"{describe_value(value)} does not match configured datetime formats "
                f"{list(formats)}",
                code=ErrorCode.INVALID_DATETIME,
                raw_value=value,
            )

    instants: set[datetime] = set()
    for candidate in candidates:
        if candidate.utcoffset() is None:
            if naive_timezone is None:
                continue
            candidate = candidate.replace(tzinfo=naive_timezone)
        instants.add(candidate.astimezone(UTC))
    if not instants:
        raise CoercionError(
            f"{describe_value(value)} has no UTC offset and this source rejects "
            f"naive timestamps",
            code=ErrorCode.NAIVE_DATETIME_REJECTED,
            raw_value=value,
        )
    if len(instants) > 1:
        raise CoercionError(
            f"{describe_value(value)} is ambiguous under configured datetime formats",
            code=ErrorCode.AMBIGUOUS_DATETIME,
            raw_value=value,
        )
    return instants.pop()


def normalize_identifier(
    value: object,
    *,
    identifier_type: str,
    invalid_code: ErrorCode,
) -> str | None:
    """Normalize a source identifier to its canonical string form.

    string:  str only; trimmed; blank becomes None.
    integer: positive int only (not bool, float, or numeric string).
    None always becomes None; the caller decides whether that is allowed.
    """
    if value is None:
        return None
    if identifier_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise IdentifierError(
                f"expected a positive integer identifier, got {type(value).__name__} "
                f"{describe_value(value)}",
                code=invalid_code,
                raw_value=value,
            )
        return str(value)
    if not isinstance(value, str):
        raise IdentifierError(
            f"expected a string identifier, got {type(value).__name__} "
            f"{describe_value(value)}",
            code=invalid_code,
            raw_value=value,
        )
    return value.strip() or None
