"""
D2 quarantine contract tests: record structure, safe payloads, redaction.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from d1_support import INGESTED_AT, RUN_ID, full_case, with_value
from d2_support import SECRET_TOKEN, canonical, tamper

import app.normalization.pipeline as d1_pipeline
from app.validation import (
    QualityFinding,
    QualityGateSystemError,
    QuarantineRecord,
    Severity,
    Stage,
    default_validation_config,
    validate_canonical_batch,
    validate_source_batch,
)
from app.validation.quarantine import (
    MAX_DEPTH_MARKER,
    is_sensitive_key,
    safe_message,
    safe_payload,
    safe_repr,
)

POLICY = default_validation_config().quarantine
REDACTED = POLICY.redaction


def _finding(**overrides):
    values = {"severity": Severity.ERROR, "code": "INVALID_DECIMAL", "message": "bad",
              "record_index": 0, "source_id": "D1", "field_name": "amount", "raw_value": "'x'"}
    values.update(overrides)
    return QualityFinding(**values)


def _record(**overrides):
    values = {"ingestion_run_id": RUN_ID, "source_system": "csv_demo", "entity_type": "deals",
              "record_index": 0, "stage": Stage.NORMALIZATION, "source_id": "D1",
              "canonical_id": uuid.UUID(int=5), "findings": (_finding(),),
              "raw_record": {"deal_id": "D1"}}
    values.update(overrides)
    return QuarantineRecord(**values)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_quarantine_record_to_dict_contract():
    record = _record(findings=(_finding(), _finding(code="UNKNOWN_ENUM_VALUE", field_name="stage")))
    data = record.to_dict()
    assert data == {
        "ingestion_run_id": str(RUN_ID), "source_system": "csv_demo", "entity_type": "deals",
        "record_index": 0, "stage": "normalization", "source_id": "D1",
        "canonical_id": str(uuid.UUID(int=5)), "severity": "ERROR", "code": "INVALID_DECIMAL",
        "field_name": "amount", "message": "bad",
        "findings": [f.to_dict() for f in record.findings], "raw_record": {"deal_id": "D1"},
    }
    assert json.loads(json.dumps(data)) == data
    assert (record.code, record.field_name, record.message) == ("INVALID_DECIMAL", "amount", "bad")


@pytest.mark.parametrize("findings", [(), (QualityFinding(Severity.WARNING, "X", "m", 0),)])
def test_quarantine_record_requires_error_findings(findings):
    with pytest.raises(ValueError):
        _record(findings=findings)


def test_findings_and_records_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _finding().code = "OTHER"
    with pytest.raises(dataclasses.FrozenInstanceError):
        _record().source_id = "OTHER"


def test_source_path_quarantine_has_canonical_identity_when_source_id_is_known():
    record = with_value(full_case("rest_mock", "deals")[0], "stage", "lost")
    quarantined = validate_source_batch("rest_mock", "deals", [record], RUN_ID,
                                        INGESTED_AT).quarantined[0]
    from app.normalization import canonical_id

    assert quarantined.canonical_id == canonical_id("rest_mock", "deals", "DEAL-003")
    assert quarantined.to_dict()["canonical_id"] == str(quarantined.canonical_id)


# ---------------------------------------------------------------------------
# Safe payloads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", [
    "password", "Password", "api_key", "X-Api-Key", "Authorization", "client_secret",
    "refresh_token", "sessionId", "cookie", "privateKey", "AWS_ACCESS_KEY_ID", "db_passwd",
    "credentials",
])
def test_sensitive_keys_are_redacted(key):
    assert is_sensitive_key(key, POLICY)
    assert safe_payload({key: "value", "customer_id": "CUST-1"}, POLICY) == {
        key: REDACTED, "customer_id": "CUST-1"}


@pytest.mark.parametrize("key", ["customer_id", "name", "status", "amount", "owner_id", "body_text"])
def test_business_keys_are_not_redacted(key):
    assert not is_sensitive_key(key, POLICY)


def test_nested_structures_are_redacted():
    payload = {"meta": {"headers": {"Authorization": "Basic dXNlcjpwYXNz"}},
               "items": [{"token": "t1"}, {"name": "ok"}]}
    assert safe_payload(payload, POLICY) == {
        "meta": {"headers": {"Authorization": REDACTED}},
        "items": [{"token": REDACTED}, {"name": "ok"}]}


@pytest.mark.parametrize(("value", "redacted"), [
    (f"Bearer {SECRET_TOKEN}", True),
    (f"see https://api.example/x?token={SECRET_TOKEN}", True),
    ("https://api.example/x?api_key=abc123&page=2", True),
    ("password=hunter2", True),
    ("Bearer of bad news", False),
    ("Basic support plan", False),
    ("Token-based pricing tier", False),
])
def test_sensitive_value_patterns(value, redacted):
    assert (safe_payload({"note": value}, POLICY)["note"] == REDACTED) is redacted


def test_messages_are_scrubbed():
    message = safe_message(f"'Bearer {SECRET_TOKEN}' is not a decimal", POLICY)
    assert SECRET_TOKEN not in message
    assert REDACTED in message


def test_long_strings_are_truncated_deterministically():
    text = "x" * (POLICY.max_string_length + 500)
    assert safe_payload(text, POLICY) == "x" * POLICY.max_string_length + "...[truncated 500 chars]"
    assert safe_payload("y" * POLICY.max_string_length, POLICY) == "y" * POLICY.max_string_length


def test_depth_limit_handles_cycles():
    cyclic: dict = {}
    cyclic["self"] = cyclic
    payload = safe_payload(cyclic, POLICY)
    json.dumps(payload)
    node = payload
    for _ in range(POLICY.max_depth):
        node = node["self"]
    assert node == MAX_DEPTH_MARKER


def test_non_json_types_become_stable_values():
    class Custom:
        pass

    payload = safe_payload({
        "decimal": Decimal("1.50"), "datetime": datetime(2026, 1, 1, tzinfo=UTC),
        "date": date(2026, 1, 1), "uuid": uuid.UUID(int=1), "bytes": b"abc",
        "set": {"b", "a"}, "tuple": (1, 2), "nan": float("nan"), "custom": Custom(), 7: "int-key",
    }, POLICY)
    assert payload == {
        "decimal": "1.50", "datetime": "2026-01-01T00:00:00+00:00", "date": "2026-01-01",
        "uuid": str(uuid.UUID(int=1)), "bytes": "<3 bytes>", "set": ["a", "b"], "tuple": [1, 2],
        "nan": "nan", "custom": "<Custom>", "7": "int-key",
    }
    json.dumps(payload)


def test_safe_repr():
    assert safe_repr(None, POLICY) is None
    assert safe_repr(f"Bearer {SECRET_TOKEN}", POLICY) == f"'{REDACTED}'"
    assert len(safe_repr("z" * 10_000, POLICY)) <= 80
    assert safe_repr(Decimal("1.005"), POLICY) == "'1.005'"


# ---------------------------------------------------------------------------
# End-to-end leak checks
# ---------------------------------------------------------------------------

SECRETS = [SECRET_TOKEN, "hunter2-password", "s3cr3t-client", "cookie-value-123", "api-key-value"]


def test_source_path_quarantine_never_leaks_secrets():
    record = with_value(full_case("csv_demo", "deals")[0], "amount", f"Bearer {SECRET_TOKEN}")
    record.update({
        "password": "hunter2-password", "client_secret": "s3cr3t-client",
        "Cookie": "cookie-value-123", "notes": "rotate https://h/x?api_key=api-key-value",
    })
    result = validate_source_batch("csv_demo", "deals", [record], RUN_ID, INGESTED_AT)
    dump = json.dumps([q.to_dict() for q in result.quarantined])
    assert result.quarantined[0].code == "INVALID_DECIMAL"
    for secret in SECRETS:
        assert secret not in dump


def test_canonical_path_quarantine_never_leaks_secrets():
    document = tamper(canonical("rest_mock", "documents"),
                      body_text=f"Authorization: Bearer {SECRET_TOKEN}", source_uri=" padded")
    result = validate_canonical_batch("rest_mock", "documents", [document], RUN_ID)
    dump = json.dumps([q.to_dict() for q in result.quarantined])
    assert result.quarantined[0].code == "NON_CANONICAL_VALUE"
    assert SECRET_TOKEN not in dump


def test_system_failure_message_does_not_leak_secrets(monkeypatch):
    def explode(*args):
        raise RuntimeError(f"auth failed with Bearer {SECRET_TOKEN}")

    monkeypatch.setattr(d1_pipeline, "map_record", explode)
    with pytest.raises(QualityGateSystemError) as excinfo:
        validate_source_batch("csv_demo", "deals", [full_case("csv_demo", "deals")[0]], RUN_ID,
                              INGESTED_AT)
    assert SECRET_TOKEN not in str(excinfo.value)
