"""
D1 normalization pipeline tests.

Covers:
A. Public API and source-system vocabulary consistency with connectors
B. Invocation contract (ingestion_run_id, ingested_at)
C. Provenance, including per-record source_updated_at
D. Structured errors: exact type, stable code, full context
E. Batch isolation
F. Input immutability
G. Determinism (in-process and across interpreter processes)
H. Purity and dependency boundaries
"""

from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import pytest
from d1_support import (
    ABSENT,
    CASE_KEYS,
    INGESTED_AT,
    RUN_ID,
    assert_error,
    business,
    case_id,
    full_case,
    utc,
    with_value,
)
from pydantic import ValidationError

import app.normalization as normalization
import app.normalization.pipeline as pipeline
from app.connectors.csv import CsvConnectorConfig
from app.connectors.odoo import SUPPORTED_ENTITIES as ODOO_ENTITIES
from app.connectors.odoo import OdooConnectorConfig
from app.connectors.rest import RestConnectorConfig
from app.connectors.types import ConnectorError
from app.normalization import (
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
    canonical_id,
    default_config,
    normalize,
    normalize_batch,
)

REPO = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent
D1_DIR = REPO / "app" / "normalization"


# ---------------------------------------------------------------------------
# A. Public API and vocabulary
# ---------------------------------------------------------------------------


def test_public_api_exports():
    for name in normalization.__all__:
        assert hasattr(normalization, name), name


def test_d1_vocabulary_is_the_canonical_source_systems():
    assert default_config().source_systems == ("csv_demo", "odoo_mock", "rest_mock")


def test_connector_configuration_files_use_canonical_source_names():
    connectors = REPO / "config" / "connectors"
    names = {
        "csv": CsvConnectorConfig.from_yaml(connectors / "csv_demo.yaml").source_name,
        "odoo": OdooConnectorConfig.from_yaml(connectors / "odoo.yaml").source_name,
        "rest": RestConnectorConfig.from_yaml(connectors / "rest.yaml").source_name,
    }
    assert names == {"csv": "csv_demo", "odoo": "odoo_mock", "rest": "rest_mock"}
    assert set(names.values()) == set(default_config().source_systems)


def test_connector_defaults_use_canonical_source_names():
    assert CsvConnectorConfig.from_dict({}).source_name == "csv_demo"
    assert OdooConnectorConfig.from_dict({"base_url": "http://mock"}).source_name == "odoo_mock"
    rest = RestConnectorConfig.from_dict(
        {"base_url": "http://mock", "entities": {"customers": {"path": "/rest/customers"}}}
    )
    assert rest.source_name == "rest_mock"


def test_every_connector_entity_is_mapped_by_d1():
    connectors = REPO / "config" / "connectors"
    sources = default_config().sources
    csv_entities = CsvConnectorConfig.from_yaml(connectors / "csv_demo.yaml").entities
    rest_entities = RestConnectorConfig.from_yaml(connectors / "rest.yaml").entities
    assert set(csv_entities) <= set(sources["csv_demo"].entities)
    assert set(ODOO_ENTITIES) <= set(sources["odoo_mock"].entities)
    assert set(rest_entities) <= set(sources["rest_mock"].entities)


def test_legacy_source_names_do_not_remain_in_code_config_or_connector_tests():
    files = [
        *REPO.glob("app/**/*.py"),
        *REPO.glob("config/**/*.yaml"),
        *REPO.glob("tests/unit/test_c*.py"),
        REPO / "README.md",
    ]
    legacy = ["rest_demo", "odoo_demo", "source_name: odoo\n", '"source_name", "odoo")',
              '"source_name": "odoo"']
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in legacy:
            assert token not in text, f"{token!r} found in {path.relative_to(REPO)}"


@pytest.mark.parametrize("retired", ["odoo", "rest_demo", "odoo_demo", "REST_MOCK"])
def test_retired_source_names_are_rejected(retired):
    with pytest.raises(NormalizationError) as excinfo:
        normalize(retired, "customers", {"id": 1}, RUN_ID, INGESTED_AT)
    assert_error(excinfo.value, UnsupportedSourceError, ErrorCode.UNSUPPORTED_SOURCE,
                 source_system=retired, entity_type="customers", source_id=None, field_name=None)


# ---------------------------------------------------------------------------
# B. Invocation contract
# ---------------------------------------------------------------------------

CALLERS = {
    "normalize": lambda run_id, at: normalize("csv_demo", "customers",
                                              full_case("csv_demo", "customers")[0], run_id, at),
    "normalize_batch": lambda run_id, at: normalize_batch("csv_demo", "customers",
                                                          [full_case("csv_demo", "customers")[0]],
                                                          run_id, at),
}


@pytest.mark.parametrize("caller", sorted(CALLERS))
def test_naive_ingested_at_is_rejected(caller):
    with pytest.raises(ValueError, match="timezone-aware"):
        CALLERS[caller](RUN_ID, datetime(2026, 9, 14, 12))


@pytest.mark.parametrize("caller", sorted(CALLERS))
@pytest.mark.parametrize(("run_id", "ingested_at"), [
    (str(RUN_ID), INGESTED_AT), (RUN_ID, "2026-09-14T12:00:00Z"), (None, INGESTED_AT),
])
def test_invalid_run_context_types_are_rejected(caller, run_id, ingested_at):
    with pytest.raises(TypeError):
        CALLERS[caller](run_id, ingested_at)


def test_batch_validates_run_context_before_consuming_records():
    consumed = []

    def records():
        consumed.append(True)
        yield full_case("csv_demo", "customers")[0]

    with pytest.raises(ValueError):
        normalize_batch("csv_demo", "customers", records(), RUN_ID, datetime(2026, 1, 1))
    assert consumed == []


def test_ingested_at_is_normalized_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    obj = normalize("csv_demo", "customers", full_case("csv_demo", "customers")[0], RUN_ID,
                    datetime(2026, 9, 14, 17, 30, tzinfo=ist))
    assert obj.ingested_at == utc(2026, 9, 14, 12)
    assert obj.ingested_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# C. Provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_provenance_fields(source, entity):
    record, expected = full_case(source, entity)
    obj = normalize(source, entity, record, RUN_ID, INGESTED_AT)
    assert obj.id == canonical_id(source, entity, expected["source_id"])
    assert obj.source_system == source
    assert obj.source_entity == entity
    assert obj.source_id == expected["source_id"]
    assert obj.ingestion_run_id == RUN_ID
    assert obj.ingested_at == INGESTED_AT
    assert obj.source_updated_at == expected["source_updated_at"]


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_canonical_datetimes_are_never_naive(source, entity):
    record, _ = full_case(source, entity)
    obj = normalize(source, entity, record, RUN_ID, INGESTED_AT)
    datetimes = {name: value for name, value in obj.model_dump().items()
                 if isinstance(value, datetime)}
    assert "ingested_at" in datetimes
    for name, value in datetimes.items():
        assert value.utcoffset() == timedelta(0), name


@pytest.mark.parametrize(("source", "field", "first", "second"), [
    ("csv_demo", "updated_date", "2026-01-01", "2026-02-02 10:00:00"),
    ("odoo_mock", "write_date", "2026-01-01 00:00:00", "2026-02-02 10:00:00"),
    ("rest_mock", "updatedAt", "2026-01-01T00:00:00Z", "2026-02-02T15:30:00+05:30"),
])
def test_source_updated_at_is_extracted_per_record(source, field, first, second):
    record, _ = full_case(source, "documents")
    id_field = {"csv_demo": "document_id", "odoo_mock": "id", "rest_mock": "id"}[source]
    other_id = 2 if source == "odoo_mock" else "DOC-XYZ"
    records = [with_value(record, field, first),
               with_value(with_value(record, field, second), id_field, other_id)]
    ok, failures = normalize_batch(source, "documents", records, RUN_ID, INGESTED_AT)
    assert failures == []
    assert [obj.source_updated_at for obj in ok] == [utc(2026, 1, 1), utc(2026, 2, 2, 10)]


# ---------------------------------------------------------------------------
# D. Structured errors
# ---------------------------------------------------------------------------

ERROR_CASES = [
    ("unsupported-source", "sap_mock", "customers", {"id": "C1"},
     UnsupportedSourceError, ErrorCode.UNSUPPORTED_SOURCE, None, None),
    ("unsupported-entity", "csv_demo", "invoices", {"invoice_id": "I1"},
     UnsupportedEntityError, ErrorCode.UNSUPPORTED_ENTITY, None, None),
    ("invalid-record", "rest_mock", "deals", ["DEAL-1"],
     InvalidRecordError, ErrorCode.INVALID_RECORD, None, None),
    ("source-id-missing", "csv_demo", "customers", {"customer_name": "Acme", "status": "active"},
     IdentifierError, ErrorCode.SOURCE_ID_MISSING, None, "source_id"),
    ("source-id-invalid", "odoo_mock", "customers", {"id": "7", "name": "Acme", "active": True},
     IdentifierError, ErrorCode.SOURCE_ID_INVALID, None, "source_id"),
    ("required-field-missing", "csv_demo", "customers", {"customer_id": "C1", "status": "active"},
     FieldMappingError, ErrorCode.REQUIRED_FIELD_MISSING, "C1", "name"),
    ("invalid-decimal", "csv_demo", "deals",
     with_value(full_case("csv_demo", "deals")[0], "amount", "abc"),
     CoercionError, ErrorCode.INVALID_DECIMAL, "DEAL-001", "amount"),
    ("decimal-scale", "csv_demo", "deals",
     with_value(full_case("csv_demo", "deals")[0], "probability", "10.001"),
     CoercionError, ErrorCode.DECIMAL_SCALE_EXCEEDED, "DEAL-001", "probability"),
    ("unknown-enum", "rest_mock", "projects",
     with_value(full_case("rest_mock", "projects")[0], "status", "stalled"),
     CoercionError, ErrorCode.UNKNOWN_ENUM_VALUE, "PROJ-002", "status"),
    ("invalid-currency", "odoo_mock", "deals",
     with_value(full_case("odoo_mock", "deals")[0], "company_currency", "US$"),
     CoercionError, ErrorCode.INVALID_CURRENCY, "1", "currency"),
    ("relationship-key", "odoo_mock", "deals",
     with_value(full_case("odoo_mock", "deals")[0], "partner_id", "1"),
     IdentifierError, ErrorCode.RELATIONSHIP_KEY_INVALID, "1", "customer_source_id"),
    ("naive-datetime", "rest_mock", "customers",
     with_value(full_case("rest_mock", "customers")[0], "createdAt", "2026-01-01T00:00:00"),
     CoercionError, ErrorCode.NAIVE_DATETIME_REJECTED, "CUST-003", "created_at"),
    ("invalid-boolean", "rest_mock", "deals",
     with_value(full_case("rest_mock", "deals")[0], "isActive", "sometimes"),
     CoercionError, ErrorCode.INVALID_BOOLEAN, "DEAL-003", "is_active"),
    ("invalid-date", "odoo_mock", "projects",
     with_value(full_case("odoo_mock", "projects")[0], "date", "31/10/2026"),
     CoercionError, ErrorCode.INVALID_DATE, "2", "end_date"),
]


@pytest.mark.parametrize(
    ("source", "entity", "record", "error_type", "code", "source_id", "field_name"),
    [case[1:] for case in ERROR_CASES], ids=[case[0] for case in ERROR_CASES],
)
def test_errors_carry_type_code_and_full_context(source, entity, record, error_type, code,
                                                 source_id, field_name):
    with pytest.raises(NormalizationError) as excinfo:
        normalize(source, entity, record, RUN_ID, INGESTED_AT)
    assert_error(excinfo.value, error_type, code, source_system=source, entity_type=entity,
                 source_id=source_id, field_name=field_name)
    location = "/".join(p for p in (source, entity, source_id) if p is not None)
    assert location in excinfo.value.message


def test_coercion_error_retains_raw_value():
    record = with_value(full_case("csv_demo", "deals")[0], "amount", "12.345")
    with pytest.raises(CoercionError) as excinfo:
        normalize("csv_demo", "deals", record, RUN_ID, INGESTED_AT)
    assert excinfo.value.raw_value == "12.345"
    assert "12.345" in excinfo.value.reason


def test_schema_validation_error_has_context(monkeypatch):
    real_map_record = pipeline.map_record

    def map_with_wrong_type(config, profile, mapping, record):
        updated_at, fields = real_map_record(config, profile, mapping, record)
        return updated_at, {**fields, "name": 123}

    monkeypatch.setattr(pipeline, "map_record", map_with_wrong_type)
    with pytest.raises(NormalizationError) as excinfo:
        normalize("csv_demo", "customers", full_case("csv_demo", "customers")[0], RUN_ID,
                  INGESTED_AT)
    assert_error(excinfo.value, SchemaValidationError, ErrorCode.SCHEMA_VALIDATION_FAILED,
                 source_system="csv_demo", entity_type="customers", source_id="CUST-001",
                 field_name="name")
    assert isinstance(excinfo.value.__cause__, ValidationError)


def test_unexpected_exceptions_become_structured_errors(monkeypatch):
    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "map_record", explode)
    with pytest.raises(NormalizationError) as excinfo:
        normalize("csv_demo", "customers", full_case("csv_demo", "customers")[0], RUN_ID,
                  INGESTED_AT)
    assert_error(excinfo.value, NormalizationError, ErrorCode.UNEXPECTED_ERROR,
                 source_system="csv_demo", entity_type="customers", source_id="CUST-001",
                 field_name=None)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_exception_hierarchy():
    for cls in (UnsupportedSourceError, UnsupportedEntityError, InvalidRecordError,
                IdentifierError, FieldMappingError, CoercionError, SchemaValidationError):
        assert issubclass(cls, NormalizationError)
    assert not issubclass(NormalizationError, ConnectorError)
    assert not issubclass(NormalizationConfigError, NormalizationError)


def test_error_codes_are_stable_strings():
    assert all(code.value == code.name for code in ErrorCode)
    assert len({code.value for code in ErrorCode}) == len(ErrorCode)


def test_with_context_never_overwrites_known_context():
    error = CoercionError("bad", code=ErrorCode.INVALID_TYPE, source_id="A", field_name="amount")
    error.with_context(source_system="csv_demo", entity_type="deals", source_id="B",
                       field_name="other")
    assert (error.source_system, error.entity_type, error.source_id, error.field_name) == (
        "csv_demo", "deals", "A", "amount")


# ---------------------------------------------------------------------------
# E. Batch isolation
# ---------------------------------------------------------------------------


def test_batch_isolates_malformed_records():
    good, _ = full_case("csv_demo", "customers")
    marker = object()
    records = [
        None, good, ["list"], "string", 42, marker,
        with_value(good, "customer_id", ABSENT),
        with_value(good, "customer_id", "CUST-002"),
        with_value(good, "status", "churned"),
        with_value(good, "customer_id", "CUST-003"),
        {},
    ]
    ok, failures = normalize_batch("csv_demo", "customers", records, RUN_ID, INGESTED_AT)

    assert [obj.source_id for obj in ok] == ["CUST-001", "CUST-002", "CUST-003"]
    expected_failed = [records[i] for i in (0, 2, 3, 4, 5, 6, 8, 10)]
    assert len(failures) == len(expected_failed)
    assert all(actual is expected for (actual, _), expected in zip(failures, expected_failed, strict=True))
    assert [type(error) for _, error in failures] == [
        InvalidRecordError, InvalidRecordError, InvalidRecordError, InvalidRecordError,
        InvalidRecordError, IdentifierError, CoercionError, IdentifierError,
    ]
    assert [error.code for _, error in failures] == [
        ErrorCode.INVALID_RECORD, ErrorCode.INVALID_RECORD, ErrorCode.INVALID_RECORD,
        ErrorCode.INVALID_RECORD, ErrorCode.INVALID_RECORD, ErrorCode.SOURCE_ID_MISSING,
        ErrorCode.UNKNOWN_ENUM_VALUE, ErrorCode.SOURCE_ID_MISSING,
    ]
    for _, error in failures:
        assert (error.source_system, error.entity_type) == ("csv_demo", "customers")
    assert failures[6][1].source_id == "CUST-001"


def test_batch_accepts_any_iterable():
    good, _ = full_case("rest_mock", "deals")
    ok, failures = normalize_batch("rest_mock", "deals", (r for r in [good, None]), RUN_ID,
                                   INGESTED_AT)
    assert len(ok) == 1 and len(failures) == 1


def test_batch_with_unsupported_source_fails_per_record_without_raising():
    ok, failures = normalize_batch("odoo", "customers", [{"id": 1}, {"id": 2}], RUN_ID, INGESTED_AT)
    assert ok == []
    assert [error.code for _, error in failures] == [ErrorCode.UNSUPPORTED_SOURCE] * 2


def test_batch_continues_after_unexpected_error(monkeypatch):
    real_map_record = pipeline.map_record

    def explode_for_one(config, profile, mapping, record):
        if record.get("customer_id") == "CUST-002":
            raise RuntimeError("boom")
        return real_map_record(config, profile, mapping, record)

    monkeypatch.setattr(pipeline, "map_record", explode_for_one)
    good, _ = full_case("csv_demo", "customers")
    records = [good, with_value(good, "customer_id", "CUST-002"),
               with_value(good, "customer_id", "CUST-003")]
    ok, failures = normalize_batch("csv_demo", "customers", records, RUN_ID, INGESTED_AT)
    assert [obj.source_id for obj in ok] == ["CUST-001", "CUST-003"]
    assert failures[0][1].code == ErrorCode.UNEXPECTED_ERROR
    assert failures[0][1].source_id == "CUST-002"


def test_empty_batch():
    assert normalize_batch("csv_demo", "customers", [], RUN_ID, INGESTED_AT) == ([], [])


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_batch_output_equals_single_record_output(source, entity):
    record, _ = full_case(source, entity)
    ok, failures = normalize_batch(source, entity, [record], RUN_ID, INGESTED_AT)
    assert failures == []
    assert ok[0].model_dump() == normalize(source, entity, record, RUN_ID, INGESTED_AT).model_dump()


# ---------------------------------------------------------------------------
# F. Immutability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_normalize_does_not_mutate_input(source, entity):
    record, expected = full_case(source, entity)
    snapshot = copy.deepcopy(record)
    obj = normalize(source, entity, record, RUN_ID, INGESTED_AT)
    assert record == snapshot
    assert list(record) == list(snapshot)
    record.clear()
    assert business(obj) == expected["fields"]


@pytest.mark.parametrize(("source", "entity"), CASE_KEYS, ids=case_id)
def test_read_only_mapping_input_is_supported(source, entity):
    record, expected = full_case(source, entity)
    obj = normalize(source, entity, MappingProxyType(record), RUN_ID, INGESTED_AT)
    assert business(obj) == expected["fields"]


def test_batch_does_not_mutate_input_list_or_records():
    records = [full_case("odoo_mock", "deals")[0], None, full_case("odoo_mock", "deals")[0]]
    snapshot = copy.deepcopy(records)
    identities = [id(r) for r in records]
    normalize_batch("odoo_mock", "deals", records, RUN_ID, INGESTED_AT)
    assert records == snapshot
    assert [id(r) for r in records] == identities


# ---------------------------------------------------------------------------
# G. Determinism
# ---------------------------------------------------------------------------


def _all_outputs() -> list[list[str]]:
    outputs = []
    for key in CASE_KEYS:
        record, _ = full_case(*key)
        obj = normalize(key[0], key[1], record, RUN_ID, INGESTED_AT)
        outputs.append([key[0], key[1], str(obj.id), obj.record_hash, obj.model_dump_json()])
    return outputs


def test_repeated_normalization_is_identical():
    assert _all_outputs() == _all_outputs()


_SUBPROCESS_OUTPUTS = """
import json, sys
sys.path[:0] = [{repo!r}, {tests!r}]
from d1_support import CASE_KEYS, INGESTED_AT, RUN_ID, full_case
from app.normalization import normalize
outputs = []
for key in CASE_KEYS:
    record, _ = full_case(*key)
    obj = normalize(key[0], key[1], record, RUN_ID, INGESTED_AT)
    outputs.append([key[0], key[1], str(obj.id), obj.record_hash, obj.model_dump_json()])
print(json.dumps(outputs))
"""


def _run_python(code: str, **env: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, check=True, cwd=TESTS_DIR,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **env},
    )
    return result.stdout


@pytest.mark.parametrize("hash_seed", ["0", "4242"])
def test_output_is_identical_across_processes(hash_seed):
    code = _SUBPROCESS_OUTPUTS.format(repo=str(REPO), tests=str(TESTS_DIR))
    assert json.loads(_run_python(code, PYTHONHASHSEED=hash_seed)) == _all_outputs()


# ---------------------------------------------------------------------------
# H. Purity and boundaries
# ---------------------------------------------------------------------------

FORBIDDEN_MODULE_PREFIXES = (
    "sqlalchemy", "psycopg2", "alembic", "httpx", "requests", "urllib3", "aiohttp",
    "fastapi", "starlette", "uvicorn", "pydantic_settings", "dotenv", "openai", "anthropic",
    "langchain", "neo4j", "app.persistence", "app.connectors", "app.core", "app.api",
    "app.ingestion", "app.validation",
)

_SUBPROCESS_IMPORTS = """
import json, sys
sys.path.insert(0, {repo!r})
import app.normalization as normalization
loaded_at_import = normalization.default_config.cache_info().currsize
import uuid
from datetime import datetime, timezone
normalization.normalize("csv_demo", "customers",
    {{"customer_id": "C1", "customer_name": "Acme", "status": "active"}},
    uuid.UUID(int=1), datetime(2026, 1, 1, tzinfo=timezone.utc))
print(json.dumps({{"loaded_at_import": loaded_at_import, "modules": sorted(sys.modules)}}))
"""


def test_runtime_import_closure_has_no_database_http_or_connector_dependencies():
    result = json.loads(_run_python(_SUBPROCESS_IMPORTS.format(repo=str(REPO))))
    leaked = [m for m in result["modules"]
              if m.startswith(FORBIDDEN_MODULE_PREFIXES)]
    assert leaked == []
    assert result["loaded_at_import"] == 0, "configuration must load lazily, not at import"
    app_modules = {m for m in result["modules"] if m.startswith("app.")}
    assert all(m.startswith(("app.normalization", "app.schemas")) for m in app_modules)


ALLOWED_STDLIB_AND_THIRD_PARTY = {
    "__future__", "collections", "dataclasses", "datetime", "decimal", "enum", "functools",
    "hashlib", "json", "math", "pathlib", "re", "types", "typing", "uuid", "yaml", "pydantic",
}
FORBIDDEN_NAMES = {"open", "print", "input", "eval", "exec", "__import__"}
FORBIDDEN_ATTRIBUTES = {"environ", "getenv", "now", "utcnow", "today", "uuid1", "uuid4",
                        "random", "urandom", "system", "popen", "sleep"}


def _d1_trees():
    for path in sorted(D1_DIR.glob("*.py")):
        yield path.name, ast.parse(path.read_text(encoding="utf-8"))


def test_d1_imports_are_allowlisted():
    for name, tree in _d1_trees():
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"{name}: relative import"
                modules = [node.module]
            for module in modules:
                if module.split(".")[0] == "app":
                    assert module.startswith(("app.normalization", "app.schemas.canonical")), (
                        f"{name} imports {module}")
                else:
                    assert module.split(".")[0] in ALLOWED_STDLIB_AND_THIRD_PARTY, (
                        f"{name} imports {module}")


def test_d1_has_no_side_effecting_or_nondeterministic_calls():
    for name, tree in _d1_trees():
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.Global, ast.Nonlocal)), f"{name}: global state"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{name}: {node.id}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_ATTRIBUTES, f"{name}: .{node.attr}"


def test_only_memoization_is_the_immutable_default_config():
    cached = []
    for name, tree in _d1_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    label = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                    if label in {"lru_cache", "cache", "cached_property"}:
                        cached.append((name, node.name))
    assert cached == [("config.py", "default_config")]


def test_filesystem_access_is_confined_to_the_config_loader():
    for name, tree in _d1_trees():
        if name == "config.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"read_text", "read_bytes", "open", "glob"}, name


def test_normalization_runs_with_explicit_config_and_no_default_config(monkeypatch):
    config = normalization.load_config(REPO / "config" / "mappings")

    def forbidden():
        raise AssertionError("default_config must not be used when config is explicit")

    monkeypatch.setattr(pipeline, "default_config", forbidden)
    obj = normalize("rest_mock", "customers", full_case("rest_mock", "customers")[0], RUN_ID,
                    INGESTED_AT, config=config)
    assert obj.source_id == "CUST-003"
    assert obj.ingested_at.tzinfo is UTC
