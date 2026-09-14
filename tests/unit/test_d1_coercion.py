"""
D1 coercion primitive tests.

Each primitive is exercised directly with explicit rule parameters, so these
tests are independent of the repository configuration.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.normalization.coercion import (
    coerce_boolean,
    coerce_currency,
    coerce_date,
    coerce_datetime,
    coerce_decimal,
    coerce_email,
    coerce_enum,
    coerce_string,
    coerce_text,
    normalize_enum_token,
    normalize_identifier,
)
from app.normalization.errors import CoercionError, ErrorCode, IdentifierError

NULL = frozenset({"null", "n/a", "-"})
TRUE = frozenset({"true", "yes", "1"})
FALSE = frozenset({"false", "no", "0"})
REST_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d",
)
NAIVE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def _assert_coercion_error(excinfo, code, raw_value):
    assert type(excinfo.value) is CoercionError
    assert excinfo.value.code == code
    assert excinfo.value.raw_value == raw_value


# ---------------------------------------------------------------------------
# Strings, text, email
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), (" Acme ", "Acme"), ("", None), ("   ", None), ("N/A", None),
    ("null", None), ("NULL", None), (" - ", None), ("NA", "NA"), ("None", "None"),
    ("nil", "nil"), ("0", "0"), ("false", "false"),
])
def test_coerce_string(value, expected):
    assert coerce_string(value, null_tokens=NULL) == expected


@pytest.mark.parametrize("value", [123, 1.5, True, ["x"], {"a": 1}])
def test_coerce_string_rejects_non_strings(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_string(value, null_tokens=NULL)
    _assert_coercion_error(excinfo, ErrorCode.INVALID_TYPE, value)


@pytest.mark.parametrize(("value", "expected"), [
    (None, None), ("", None), (" \n\t", None), ("N/A", "N/A"), ("  keep \n", "  keep \n"),
])
def test_coerce_text_preserves_content(value, expected):
    assert coerce_text(value) == expected


def test_coerce_text_rejects_non_strings():
    with pytest.raises(CoercionError) as excinfo:
        coerce_text(5)
    _assert_coercion_error(excinfo, ErrorCode.INVALID_TYPE, 5)


@pytest.mark.parametrize(("value", "expected"), [
    (" Alice@Example.COM ", "alice@example.com"), ("N/A", None), ("", None), (None, None),
])
def test_coerce_email(value, expected):
    assert coerce_email(value, null_tokens=NULL) == expected


# ---------------------------------------------------------------------------
# Booleans
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [True, 1, "true", "TRUE", " Yes ", "1"])
def test_coerce_boolean_true(value):
    assert coerce_boolean(value, null_tokens=NULL, true_tokens=TRUE, false_tokens=FALSE) is True


@pytest.mark.parametrize("value", [False, 0, "false", "No", " 0 "])
def test_coerce_boolean_false(value):
    assert coerce_boolean(value, null_tokens=NULL, true_tokens=TRUE, false_tokens=FALSE) is False


@pytest.mark.parametrize("value", [None, "", "  ", "N/A", "null"])
def test_coerce_boolean_null(value):
    assert coerce_boolean(value, null_tokens=NULL, true_tokens=TRUE, false_tokens=FALSE) is None


@pytest.mark.parametrize("value", [2, -1, 1.0, 0.0, "maybe", "t", "y", "active", [], {}])
def test_coerce_boolean_rejects_unknown_representations(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_boolean(value, null_tokens=NULL, true_tokens=TRUE, false_tokens=FALSE)
    _assert_coercion_error(excinfo, ErrorCode.INVALID_BOOLEAN, value)


# ---------------------------------------------------------------------------
# Enums and currency
# ---------------------------------------------------------------------------


def test_normalize_enum_token():
    assert normalize_enum_token("  In  Progress-Now ") == "in_progress_now"


@pytest.mark.parametrize(("value", "expected"), [
    ("Open", "open"), (" RESOLVED ", "resolved"), ("done", "resolved"), ("N/A", None), (None, None),
])
def test_coerce_enum(value, expected):
    result = coerce_enum(value, null_tokens=NULL, allowed=frozenset({"open", "resolved"}),
                         aliases={"done": "resolved"})
    assert result == expected


def test_coerce_enum_rejects_unknown_labels():
    with pytest.raises(CoercionError) as excinfo:
        coerce_enum("closed", null_tokens=NULL, allowed=frozenset({"open"}), aliases={})
    _assert_coercion_error(excinfo, ErrorCode.UNKNOWN_ENUM_VALUE, "closed")


def test_coerce_enum_rejects_non_strings():
    with pytest.raises(CoercionError) as excinfo:
        coerce_enum(1, null_tokens=NULL, allowed=frozenset({"open"}), aliases={})
    _assert_coercion_error(excinfo, ErrorCode.INVALID_TYPE, 1)


CODES = frozenset({"USD", "INR", "EUR"})


@pytest.mark.parametrize(("value", "expected"), [
    ("usd", "USD"), (" Inr ", "INR"), ("₹", "INR"), ("N/A", None), (None, None),
])
def test_coerce_currency(value, expected):
    assert coerce_currency(value, null_tokens=NULL, codes=CODES, aliases={"₹": "INR"}) == expected


@pytest.mark.parametrize("value", ["GBP", "US$", "U SD", "usdollar", "$"])
def test_coerce_currency_rejects_unconfigured_codes(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_currency(value, null_tokens=NULL, codes=CODES, aliases={"₹": "INR"})
    _assert_coercion_error(excinfo, ErrorCode.INVALID_CURRENCY, value)


# ---------------------------------------------------------------------------
# Decimals
# ---------------------------------------------------------------------------


def _decimal(value, **overrides):
    params = {"null_tokens": NULL, "precision": 15, "scale": 2}
    params.update(overrides)
    return coerce_decimal(value, **params)


@pytest.mark.parametrize(("value", "expected"), [
    ("100.5", "100.50"), ("100.50", "100.50"), ("100.500", "100.50"), ("+100.5", "100.50"),
    (" 12.5 ", "12.50"), (100.5, "100.50"), (100, "100.00"), (Decimal("100.5000"), "100.50"),
    ("-0.00", "0.00"), (-0.0, "0.00"), ("0", "0.00"),
    ("9999999999999.99", "9999999999999.99"), ("-9999999999999.99", "-9999999999999.99"),
])
def test_coerce_decimal_quantizes_without_rounding(value, expected):
    result = _decimal(value)
    assert isinstance(result, Decimal)
    assert str(result) == expected


@pytest.mark.parametrize("value", [None, "", "  ", "N/A", "null"])
def test_coerce_decimal_null(value):
    assert _decimal(value) is None


@pytest.mark.parametrize(("value", "code"), [
    ("100.505", ErrorCode.DECIMAL_SCALE_EXCEEDED),
    ("0.001", ErrorCode.DECIMAL_SCALE_EXCEEDED),
    (0.1 + 0.2, ErrorCode.DECIMAL_SCALE_EXCEEDED),
    (Decimal("1.001"), ErrorCode.DECIMAL_SCALE_EXCEEDED),
    ("10000000000000", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("10000000000000.00", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("-10000000000000", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    (1e20, ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("1" * 40, ErrorCode.DECIMAL_PRECISION_EXCEEDED),
    ("NaN", ErrorCode.INVALID_DECIMAL), ("Infinity", ErrorCode.INVALID_DECIMAL),
    ("-inf", ErrorCode.INVALID_DECIMAL), (float("nan"), ErrorCode.INVALID_DECIMAL),
    (float("inf"), ErrorCode.INVALID_DECIMAL), (Decimal("NaN"), ErrorCode.INVALID_DECIMAL),
    ("1e3", ErrorCode.INVALID_DECIMAL), ("1_000", ErrorCode.INVALID_DECIMAL),
    ("1,000", ErrorCode.INVALID_DECIMAL), (".5", ErrorCode.INVALID_DECIMAL),
    ("5.", ErrorCode.INVALID_DECIMAL), ("12 . 5", ErrorCode.INVALID_DECIMAL),
    ("₹50000", ErrorCode.INVALID_DECIMAL), ("١٢", ErrorCode.INVALID_DECIMAL),
    (True, ErrorCode.INVALID_TYPE), ([1], ErrorCode.INVALID_TYPE),
])
def test_coerce_decimal_rejections(value, code):
    with pytest.raises(CoercionError) as excinfo:
        _decimal(value)
    assert type(excinfo.value) is CoercionError
    assert excinfo.value.code == code


@pytest.mark.parametrize(("value", "code"), [
    ("100.01", ErrorCode.DECIMAL_OUT_OF_RANGE), ("-0.01", ErrorCode.DECIMAL_OUT_OF_RANGE),
    ("999.99", ErrorCode.DECIMAL_OUT_OF_RANGE), ("1000", ErrorCode.DECIMAL_PRECISION_EXCEEDED),
])
def test_coerce_decimal_range_limits(value, code):
    with pytest.raises(CoercionError) as excinfo:
        _decimal(value, precision=5, scale=2, minimum=Decimal(0), maximum=Decimal(100))
    assert excinfo.value.code == code


@pytest.mark.parametrize("value", ["0", "100", "100.00", "0.01"])
def test_coerce_decimal_range_inclusive_bounds(value):
    assert _decimal(value, precision=5, scale=2, minimum=Decimal(0), maximum=Decimal(100)) is not None


@pytest.mark.parametrize("value", [
    "1.0000000000000000000000000000001",
    "12345678901.2300000000000000000000000001",
])
def test_coerce_decimal_never_rounds_beyond_context_precision(value):
    with pytest.raises(CoercionError) as excinfo:
        _decimal(value)
    assert excinfo.value.code == ErrorCode.DECIMAL_SCALE_EXCEEDED


def test_coerce_decimal_ignores_long_insignificant_trailing_zeros():
    assert str(_decimal("1.50000000000000000000000000000000000")) == "1.50"


def test_coerce_decimal_scale_zero():
    assert str(_decimal("42", precision=5, scale=0)) == "42"
    with pytest.raises(CoercionError) as excinfo:
        _decimal("42.5", precision=5, scale=0)
    assert excinfo.value.code == ErrorCode.DECIMAL_SCALE_EXCEEDED


@pytest.mark.parametrize(("value", "expected"), [
    ("1,234,567.89", "1234567.89"), ("1234.5", "1234.50"), ("-12,345", "-12345.00"),
])
def test_coerce_decimal_configured_thousands_separator(value, expected):
    assert str(_decimal(value, thousands_separator=",")) == expected


@pytest.mark.parametrize("value", ["1,23,456", "12,34", ",123", "1.234,5"])
def test_coerce_decimal_rejects_malformed_grouping(value):
    with pytest.raises(CoercionError) as excinfo:
        _decimal(value, thousands_separator=",")
    assert excinfo.value.code == ErrorCode.INVALID_DECIMAL


def test_coerce_decimal_configured_decimal_comma():
    assert str(_decimal("1.234,5", decimal_separator=",", thousands_separator=".")) == "1234.50"


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-01-15", date(2026, 1, 15)), (" 2026-01-15 ", date(2026, 1, 15)),
    (date(2026, 1, 15), date(2026, 1, 15)), (None, None), ("", None), ("N/A", None),
])
def test_coerce_date(value, expected):
    assert coerce_date(value, null_tokens=NULL, formats=("%Y-%m-%d",)) == expected


@pytest.mark.parametrize("value", ["15/01/2026", "2026-02-30", "2026-01-15T00:00:00", "garbage"])
def test_coerce_date_rejects_unmatched_values(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_date(value, null_tokens=NULL, formats=("%Y-%m-%d",))
    _assert_coercion_error(excinfo, ErrorCode.INVALID_DATE, value)


def test_coerce_date_rejects_datetime_objects():
    with pytest.raises(CoercionError) as excinfo:
        coerce_date(datetime(2026, 1, 15), null_tokens=NULL, formats=("%Y-%m-%d",))
    assert excinfo.value.code == ErrorCode.INVALID_TYPE


DAY_MONTH_FORMATS = ("%d/%m/%Y", "%m/%d/%Y")


def test_coerce_date_rejects_ambiguous_values():
    with pytest.raises(CoercionError) as excinfo:
        coerce_date("03/04/2026", null_tokens=NULL, formats=DAY_MONTH_FORMATS)
    _assert_coercion_error(excinfo, ErrorCode.AMBIGUOUS_DATE, "03/04/2026")


@pytest.mark.parametrize(("value", "expected"), [
    ("25/12/2026", date(2026, 12, 25)), ("05/05/2026", date(2026, 5, 5)),
])
def test_coerce_date_accepts_unambiguous_values(value, expected):
    assert coerce_date(value, null_tokens=NULL, formats=DAY_MONTH_FORMATS) == expected


# ---------------------------------------------------------------------------
# Datetimes and timezone policy
# ---------------------------------------------------------------------------


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", [
    "2026-01-01T12:00:00Z",
    "2026-01-01T12:00:00+00:00",
    "2026-01-01T17:30:00+05:30",
    "2026-01-01T07:00:00-05:00",
    "2025-12-31T23:00:00-13:00",
    "2026-01-01T12:00:00.000000Z",
])
def test_equivalent_timestamps_normalize_to_same_utc_instant(value):
    result = coerce_datetime(value, null_tokens=NULL, formats=REST_DATETIME_FORMATS,
                             naive_timezone=None)
    assert result == datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert _is_utc(result)
    assert result.isoformat() == "2026-01-01T12:00:00+00:00"


def test_positive_offset_is_converted_to_utc():
    result = coerce_datetime("2026-03-10T09:15:00+05:30", null_tokens=NULL,
                             formats=REST_DATETIME_FORMATS, naive_timezone=None)
    assert result == datetime(2026, 3, 10, 3, 45, tzinfo=UTC)
    assert _is_utc(result)


def test_negative_offset_is_converted_to_utc_across_midnight():
    result = coerce_datetime("2026-03-10T21:30:00-04:00", null_tokens=NULL,
                             formats=REST_DATETIME_FORMATS, naive_timezone=None)
    assert result == datetime(2026, 3, 11, 1, 30, tzinfo=UTC)
    assert _is_utc(result)


def test_microseconds_are_preserved():
    result = coerce_datetime("2026-03-10T21:30:00.123456+01:00", null_tokens=NULL,
                             formats=REST_DATETIME_FORMATS, naive_timezone=None)
    assert result == datetime(2026, 3, 10, 20, 30, 0, 123456, tzinfo=UTC)


@pytest.mark.parametrize(("naive_timezone", "expected"), [
    (UTC, datetime(2026, 1, 1, 12, tzinfo=UTC)),
    (timezone(timedelta(hours=5, minutes=30)), datetime(2026, 1, 1, 6, 30, tzinfo=UTC)),
    (timezone(timedelta(hours=-4)), datetime(2026, 1, 1, 16, tzinfo=UTC)),
])
def test_naive_timestamp_uses_configured_policy(naive_timezone, expected):
    result = coerce_datetime("2026-01-01 12:00:00", null_tokens=NULL, formats=NAIVE_FORMATS,
                             naive_timezone=naive_timezone)
    assert result == expected
    assert _is_utc(result)


def test_naive_date_only_value_is_midnight_under_policy():
    result = coerce_datetime("2026-01-01", null_tokens=NULL, formats=NAIVE_FORMATS,
                             naive_timezone=UTC)
    assert result == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("value", ["2026-01-01T12:00:00", "2026-01-01", datetime(2026, 1, 1, 12)])
def test_naive_timestamp_rejected_when_policy_rejects(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_datetime(value, null_tokens=NULL, formats=REST_DATETIME_FORMATS, naive_timezone=None)
    _assert_coercion_error(excinfo, ErrorCode.NAIVE_DATETIME_REJECTED, value)


def test_aware_datetime_objects_are_converted():
    ist = timezone(timedelta(hours=5, minutes=30))
    value = datetime(2026, 1, 1, 17, 30, tzinfo=ist)
    result = coerce_datetime(value, null_tokens=NULL, formats=NAIVE_FORMATS, naive_timezone=None)
    assert result == datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert _is_utc(result)


def test_naive_datetime_object_uses_policy():
    result = coerce_datetime(datetime(2026, 1, 1, 12), null_tokens=NULL, formats=NAIVE_FORMATS,
                             naive_timezone=UTC)
    assert result == datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert _is_utc(result)


@pytest.mark.parametrize("value", [None, "", "N/A"])
def test_coerce_datetime_null(value):
    assert coerce_datetime(value, null_tokens=NULL, formats=NAIVE_FORMATS, naive_timezone=UTC) is None


@pytest.mark.parametrize("value", ["2026-13-01 00:00:00", "not a date", "2026/01/01 12:00:00"])
def test_coerce_datetime_rejects_unmatched_values(value):
    with pytest.raises(CoercionError) as excinfo:
        coerce_datetime(value, null_tokens=NULL, formats=NAIVE_FORMATS, naive_timezone=UTC)
    _assert_coercion_error(excinfo, ErrorCode.INVALID_DATETIME, value)


def test_coerce_datetime_rejects_date_objects():
    with pytest.raises(CoercionError) as excinfo:
        coerce_datetime(date(2026, 1, 1), null_tokens=NULL, formats=NAIVE_FORMATS, naive_timezone=UTC)
    assert excinfo.value.code == ErrorCode.INVALID_TYPE


def test_coerce_datetime_rejects_ambiguous_values():
    formats = ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S")
    with pytest.raises(CoercionError) as excinfo:
        coerce_datetime("03/04/2026 10:00:00", null_tokens=NULL, formats=formats, naive_timezone=UTC)
    _assert_coercion_error(excinfo, ErrorCode.AMBIGUOUS_DATETIME, "03/04/2026 10:00:00")
    result = coerce_datetime("13/04/2026 10:00:00", null_tokens=NULL, formats=formats,
                             naive_timezone=UTC)
    assert result == datetime(2026, 4, 13, 10, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [
    ("CUST-1", "CUST-1"), ("  CUST-1 ", "CUST-1"), ("", None), ("   ", None), (None, None),
    ("N/A", "N/A"),
])
def test_string_identifiers(value, expected):
    result = normalize_identifier(value, identifier_type="string",
                                  invalid_code=ErrorCode.SOURCE_ID_INVALID)
    assert result == expected


@pytest.mark.parametrize(("value", "expected"), [(1, "1"), (907, "907"), (None, None)])
def test_integer_identifiers(value, expected):
    result = normalize_identifier(value, identifier_type="integer",
                                  invalid_code=ErrorCode.SOURCE_ID_INVALID)
    assert result == expected


@pytest.mark.parametrize(("identifier_type", "value"), [
    ("integer", ""), ("integer", "1"), ("integer", 1.0), ("integer", True), ("integer", False),
    ("integer", 0), ("integer", -1), ("integer", "abc"), ("string", 1), ("string", 1.0),
    ("string", True), ("string", ["x"]),
])
def test_invalid_identifiers_raise_with_requested_code(identifier_type, value):
    with pytest.raises(IdentifierError) as excinfo:
        normalize_identifier(value, identifier_type=identifier_type,
                             invalid_code=ErrorCode.RELATIONSHIP_KEY_INVALID)
    assert type(excinfo.value) is IdentifierError
    assert excinfo.value.code == ErrorCode.RELATIONSHIP_KEY_INVALID
    assert excinfo.value.raw_value == value
