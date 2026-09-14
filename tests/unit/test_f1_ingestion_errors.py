"""
F1 safe presentation of persisted ingestion errors (message catalogue and findings parser).
"""

from __future__ import annotations

import json

import pytest

from app.api.ingestion_errors import (
    FALLBACK_MESSAGE,
    SAFE_MESSAGES,
    TRUSTED_MESSAGE_CODES,
    SafeFinding,
    safe_findings,
    safe_message,
)
from app.ingestion.errors import IngestionCode
from app.normalization import ErrorCode
from app.validation.errors import QualityCode

STORED = "stored message quoting 'private-value'"


def test_the_catalogue_covers_exactly_the_d1_and_d2_finding_codes():
    assert set(SAFE_MESSAGES) == {code.value for code in ErrorCode} | {
        code.value for code in QualityCode}


def test_trusted_codes_are_exactly_the_e1_codes_and_never_catalogued():
    assert TRUSTED_MESSAGE_CODES == {"UNRESOLVED_REFERENCE", "CONNECTOR_UNHEALTHY",
                                     "CONNECTOR_FAILED", "BATCH_FAILED"}
    assert TRUSTED_MESSAGE_CODES == {code.value for code in IngestionCode}
    assert not TRUSTED_MESSAGE_CODES & set(SAFE_MESSAGES)


def test_catalogue_messages_are_fixed_text():
    for code, message in SAFE_MESSAGES.items():
        assert message and message == message.strip(), code
        assert not set(message) & set("'\"{}%"), code
    assert FALLBACK_MESSAGE == "record failed data quality checks"
    assert SAFE_MESSAGES["UNKNOWN_ENUM_VALUE"] == \
        "value is not in the canonical vocabulary for this field"


def test_the_catalogue_cannot_be_modified_at_runtime():
    with pytest.raises(TypeError):
        SAFE_MESSAGES["UNKNOWN_ENUM_VALUE"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize("code", sorted(IngestionCode))
def test_e1_codes_keep_their_stored_message(code):
    assert safe_message(code.value, STORED) == STORED


@pytest.mark.parametrize("code", ["UNKNOWN_ENUM_VALUE", "INVALID_DECIMAL", "INVALID_DATE",
                                  "MISSING_RECOMMENDED_FIELD", "DUPLICATE_SOURCE_RECORD"])
def test_d1_and_d2_codes_never_return_the_stored_message(code):
    assert safe_message(code, STORED) == SAFE_MESSAGES[code]


@pytest.mark.parametrize("code", [None, "", "FUTURE_D1_CODE", "unknown_enum_value"])
def test_unknown_codes_fall_back_to_the_generic_message(code):
    assert safe_message(code, STORED) == FALLBACK_MESSAGE


@pytest.mark.parametrize("detail", [None, "", "not json", "[1, 2]", "\"text\"", "42", "null",
                                    json.dumps({"failure": "unhealthy"}),
                                    json.dumps({"exception": "ConnectorRequestError",
                                                "page_index": 0, "run_stopped": False}),
                                    json.dumps({"page_index": 1, "records": 3,
                                                "database_error": "DataError",
                                                "sqlstate": "22003"})])
def test_details_without_findings_yield_none(detail):
    assert safe_findings(detail, STORED) == []


def test_quarantine_findings_expose_code_field_and_severity_but_no_source_values():
    detail = json.dumps({
        "stage": "normalization", "code": "INVALID_DATE", "message": "'31/12/2026' bad",
        "raw_record": {"deal_id": "DEAL-904", "expected_close_date": "31/12/2026"},
        "findings": [
            {"severity": "ERROR", "code": "INVALID_DATE", "message": "'31/12/2026' bad",
             "field_name": "expected_close_date", "raw_value": "'31/12/2026'"},
            "not a finding",
            {"severity": "ERROR", "code": 7, "field_name": "amount"},
            {"severity": "ERROR", "code": "INVALID_DECIMAL", "message": "'1,0' bad",
             "field_name": "amount", "raw_value": "'1,0'"},
        ],
    })
    findings = safe_findings(detail, "'31/12/2026' bad")
    assert findings == [
        SafeFinding("INVALID_DATE", "expected_close_date", "ERROR", SAFE_MESSAGES["INVALID_DATE"]),
        SafeFinding("INVALID_DECIMAL", "amount", "ERROR", SAFE_MESSAGES["INVALID_DECIMAL"]),
    ]
    assert "31/12/2026" not in repr(findings) and "1,0" not in repr(findings)


def test_a_warning_detail_is_a_single_finding():
    detail = json.dumps({"severity": "WARNING", "code": "MISSING_RECOMMENDED_FIELD",
                         "message": "recommended field has no value", "record_index": 1,
                         "source_id": "CUST-902", "field_name": "email", "raw_value": None})
    assert safe_findings(detail, STORED) == [SafeFinding(
        "MISSING_RECOMMENDED_FIELD", "email", "WARNING", SAFE_MESSAGES["MISSING_RECOMMENDED_FIELD"])]


def test_an_unresolved_reference_finding_uses_the_trusted_stored_message():
    detail = json.dumps({"severity": "WARNING", "code": "UNRESOLVED_REFERENCE",
                         "record_index": 0, "source_id": "DEAL-902", "field_name": "customer_id",
                         "source_key_field": "customer_source_id", "source_key": "CUST-999",
                         "parent_entity": "customers"})
    findings = safe_findings(detail, "customer_source_id does not resolve")
    assert findings == [SafeFinding("UNRESOLVED_REFERENCE", "customer_id", "WARNING",
                                    "customer_source_id does not resolve")]
    assert "CUST-999" not in repr(findings)


def test_a_non_list_findings_key_falls_back_to_the_payload_itself():
    detail = json.dumps({"findings": "oops", "code": "INVALID_DATE", "field_name": "d"})
    assert safe_findings(detail, STORED) == [
        SafeFinding("INVALID_DATE", "d", None, SAFE_MESSAGES["INVALID_DATE"])]


@pytest.mark.parametrize(("entry", "field_name", "severity"), [
    ({"field_name": 5, "severity": "FATAL"}, None, None),
    ({"severity": "INFO"}, None, "INFO"),
    ({"field_name": "status", "severity": ["ERROR"]}, "status", None),
])
def test_malformed_field_names_and_severities_become_null(entry, field_name, severity):
    detail = json.dumps({"findings": [{"code": "FUTURE_CODE", **entry}]})
    assert safe_findings(detail, STORED) == [
        SafeFinding("FUTURE_CODE", field_name, severity, FALLBACK_MESSAGE)]
