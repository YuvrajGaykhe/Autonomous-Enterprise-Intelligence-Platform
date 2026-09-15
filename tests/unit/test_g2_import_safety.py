"""
G2 imported-file safety (spec Section 14: "Validate file types and size limits
for uploaded/imported files").

app.core.security accepts only plain file names with an allowed suffix, a
positive byte limit, and files that resolve inside their data directory, are
regular files and are within the limit. The CSV connector checks names and the
limit when its configuration is parsed and checks the file again every time it
reads one, so symlinks, oversized files and directly constructed
configurations are refused too.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.connectors import registry
from app.connectors.csv import CsvConnector, CsvConnectorConfig, CsvEntityConfig
from app.connectors.types import ConnectorConfigurationError, ConnectorRequestError
from app.core.security import (
    CSV_SUFFIXES,
    DEFAULT_MAX_IMPORT_BYTES,
    ImportFileRejected,
    SecurityConstraintError,
    UnsafeConfigurationError,
    check_import_file,
    validate_import_file_name,
    validate_max_file_bytes,
)

REPO = Path(__file__).resolve().parents[2]
HEADER = "customer_id,name\n"
ROW = "CUST-001,Acme\n"

EMPTY = "must be a non-empty string"
CONTROL = "must not contain control characters"
PLAIN = "must be a plain file name without directory components"
SUFFIX = "must have one of the suffixes .csv"
LIMIT = "must be a positive integer number of bytes"
OUTSIDE = "resolves outside the data directory"
NOT_FILE = "is not a regular file"


def _write(path: Path, text: str = HEADER + ROW) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _connector(directory: Path, file_name: str = "customers.csv", **config: object) -> CsvConnector:
    return CsvConnector(CsvConnectorConfig.from_dict({
        "source_name": "csv_demo", "data_directory": str(directory),
        "entities": {"customers": {"file": file_name, "id_column": "customer_id"}}, **config,
    }))


# --- file names -----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["customers.csv", "Customers.CSV", "support tickets.csv",
                                  "deals.2026.csv", "a.csv", "..customers.csv", "x..csv"])
def test_plain_csv_file_names_are_returned_unchanged(name):
    assert validate_import_file_name(name) == name


@pytest.mark.parametrize(("value", "message"), [
    (None, EMPTY), ("", EMPTY), (5, EMPTY), (Path("customers.csv"), EMPTY),
    ("customers\x00.csv", CONTROL), ("customers\n.csv", CONTROL), ("cust\tomers.csv", CONTROL),
    ("../customers.csv", PLAIN), ("sub/customers.csv", PLAIN), ("/etc/customers.csv", PLAIN),
    ("..\\customers.csv", PLAIN), ("sub\\customers.csv", PLAIN), (".", PLAIN), ("..", PLAIN),
    ("customers.txt", SUFFIX), ("customers.xlsx", SUFFIX), ("customers", SUFFIX), (".csv", SUFFIX),
    ("customers.csv.exe", SUFFIX), ("customers.csv ", SUFFIX),
])
def test_unsafe_file_names_are_rejected_by_rule(value, message):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_import_file_name(value)
    assert str(caught.value) == message


def test_suffixes_can_be_widened_and_are_listed_in_order():
    assert validate_import_file_name("book.xlsx", {".xlsx", ".csv"}) == "book.xlsx"
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_import_file_name("book.txt", {".xlsx", ".csv"})
    assert str(caught.value) == "must have one of the suffixes .csv, .xlsx"


def test_the_default_suffixes_are_csv_only():
    assert CSV_SUFFIXES == frozenset({".csv"})


# --- size limits ----------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 1024, DEFAULT_MAX_IMPORT_BYTES])
def test_positive_integer_limits_are_accepted(value):
    assert validate_max_file_bytes(value) == value


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, 10.0, "10", None, [10]])
def test_other_limits_are_rejected(value):
    with pytest.raises(UnsafeConfigurationError) as caught:
        validate_max_file_bytes(value)
    assert str(caught.value) == LIMIT


def test_the_default_import_limit_is_50_mebibytes():
    assert DEFAULT_MAX_IMPORT_BYTES == 52_428_800


def test_import_rejections_are_security_errors_but_not_value_errors():
    assert issubclass(ImportFileRejected, SecurityConstraintError)
    assert not issubclass(ImportFileRejected, ValueError)


# --- checking a file ------------------------------------------------------------------


def test_a_file_inside_the_directory_is_returned_resolved(tmp_path):
    path = _write(tmp_path / "customers.csv")
    assert check_import_file(tmp_path, "customers.csv", 1024) == path.resolve()


def test_the_size_limit_is_inclusive(tmp_path):
    path = _write(tmp_path / "customers.csv")
    size = path.stat().st_size
    assert check_import_file(tmp_path, "customers.csv", size) == path.resolve()
    with pytest.raises(ImportFileRejected) as caught:
        check_import_file(tmp_path, "customers.csv", size - 1)
    assert str(caught.value) == f"is larger than the {size - 1}-byte import limit"


def test_a_symlink_leaving_the_directory_is_rejected(tmp_path):
    outside = _write(tmp_path / "outside.csv")
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "customers.csv").symlink_to(outside)
    with pytest.raises(ImportFileRejected) as caught:
        check_import_file(directory, "customers.csv", 1024)
    assert str(caught.value) == OUTSIDE


def test_a_symlink_to_a_file_in_the_same_directory_is_allowed(tmp_path):
    target = _write(tmp_path / "real.csv")
    (tmp_path / "customers.csv").symlink_to(target)
    assert check_import_file(tmp_path, "customers.csv", 1024) == target.resolve()


def test_a_symlinked_data_directory_is_resolved_before_containment(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _write(real / "customers.csv")
    (tmp_path / "linked").symlink_to(real, target_is_directory=True)
    assert check_import_file(tmp_path / "linked", "customers.csv", 1024) == \
        (real / "customers.csv").resolve()


def test_directories_and_missing_files_are_not_regular_files(tmp_path):
    (tmp_path / "folder.csv").mkdir()
    for name in ("folder.csv", "missing.csv"):
        with pytest.raises(ImportFileRejected) as caught:
            check_import_file(tmp_path, name, 1024)
        assert str(caught.value) == NOT_FILE


def test_the_check_validates_its_name_and_limit(tmp_path):
    _write(tmp_path / "customers.csv")
    with pytest.raises(UnsafeConfigurationError, match=PLAIN):
        check_import_file(tmp_path, "../customers.csv", 1024)
    with pytest.raises(UnsafeConfigurationError, match=LIMIT):
        check_import_file(tmp_path, "customers.csv", 0)
    with pytest.raises(UnsafeConfigurationError, match=SUFFIX):
        check_import_file(tmp_path, "customers.txt", 1024)
    assert check_import_file(tmp_path, "customers.csv", 1024, {".csv"}).name == "customers.csv"
    _write(tmp_path / "book.xlsx")
    assert check_import_file(tmp_path, "book.xlsx", 1024, {".xlsx"}).name == "book.xlsx"
    with pytest.raises(UnsafeConfigurationError, match="must have one of the suffixes .xlsx"):
        check_import_file(tmp_path, "customers.csv", 1024, {".xlsx"})


def test_directly_constructed_configurations_default_to_the_import_limit():
    config = CsvConnectorConfig(source_name="csv_demo", source_type="csv", data_directory="data")
    assert config.max_file_bytes == DEFAULT_MAX_IMPORT_BYTES


# --- CSV connector configuration ------------------------------------------------------


@pytest.mark.parametrize(("name", "message"), [
    ("../secrets.csv", PLAIN), ("sub/customers.csv", PLAIN), ("/etc/passwd", PLAIN),
    ("customers.txt", SUFFIX), (7, EMPTY),
])
def test_from_dict_rejects_unsafe_entity_files(tmp_path, name, message):
    with pytest.raises(ConnectorConfigurationError) as caught:
        _connector(tmp_path, name)
    assert str(caught.value) == f"Entity 'customers' has an invalid file: {message}"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize(("name", "message"), [("../secrets.csv", PLAIN), ("customers.txt", SUFFIX)])
def test_from_yaml_rejects_unsafe_entity_files(tmp_path, name, message):
    path = tmp_path / "csv.yaml"
    path.write_text(f"source_name: csv_demo\ndata_directory: {tmp_path}\nentities:\n"
                    f"  customers:\n    file: '{name}'\n    id_column: customer_id\n", encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError) as caught:
        CsvConnectorConfig.from_yaml(path)
    assert str(caught.value) == f"Entity 'customers' has an invalid file: {message}"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


@pytest.mark.parametrize("value", [0, -5, True, "big", 1.5])
def test_both_parsers_reject_invalid_size_limits(tmp_path, value):
    with pytest.raises(ConnectorConfigurationError) as caught:
        _connector(tmp_path, max_file_bytes=value)
    assert str(caught.value) == f"Invalid max_file_bytes: {LIMIT}"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    path = tmp_path / "csv.yaml"
    path.write_text(f"data_directory: {tmp_path}\nmax_file_bytes: {value!r}\nentities: {{}}\n",
                    encoding="utf-8")
    with pytest.raises(ConnectorConfigurationError) as from_yaml:
        CsvConnectorConfig.from_yaml(path)
    assert str(from_yaml.value) == f"Invalid max_file_bytes: {LIMIT}"
    assert from_yaml.value.__cause__ is None and from_yaml.value.__suppress_context__


def test_both_parsers_default_and_accept_size_limits(tmp_path):
    assert _connector(tmp_path)._config.max_file_bytes == DEFAULT_MAX_IMPORT_BYTES
    assert _connector(tmp_path, max_file_bytes=2048)._config.max_file_bytes == 2048
    path = tmp_path / "csv.yaml"
    path.write_text(f"data_directory: {tmp_path}\nentities: {{}}\n", encoding="utf-8")
    assert CsvConnectorConfig.from_yaml(path).max_file_bytes == DEFAULT_MAX_IMPORT_BYTES
    path.write_text(f"data_directory: {tmp_path}\nmax_file_bytes: 4096\nentities: {{}}\n",
                    encoding="utf-8")
    assert CsvConnectorConfig.from_yaml(path).max_file_bytes == 4096


# --- CSV connector reads ---------------------------------------------------------------


def test_files_within_the_limit_are_read_unchanged(tmp_path):
    _write(tmp_path / "customers.csv")
    connector = _connector(tmp_path, max_file_bytes=len(HEADER + ROW))
    assert connector.fetch_entities("customers").items == [{"customer_id": "CUST-001", "name": "Acme"}]
    assert connector.get_entity("customers", "CUST-001") == {"customer_id": "CUST-001", "name": "Acme"}


def test_oversized_files_are_refused_on_every_read(tmp_path):
    _write(tmp_path / "customers.csv", HEADER + ROW * 10)
    connector = _connector(tmp_path, max_file_bytes=len(HEADER))
    for read in (lambda: connector.fetch_entities("customers"),
                 lambda: connector.get_entity("customers", "CUST-001")):
        with pytest.raises(ConnectorRequestError) as caught:
            read()
        assert str(caught.value) == ("Source file for entity 'customers' was refused: "
                                     f"is larger than the {len(HEADER)}-byte import limit")
        assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_symlinks_out_of_the_data_directory_are_refused(tmp_path):
    secret = _write(tmp_path / "private.csv", "customer_id,name\nCUST-001,private-row-value\n")
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "customers.csv").symlink_to(secret)
    with pytest.raises(ConnectorRequestError) as caught:
        _connector(directory).fetch_entities("customers")
    assert str(caught.value) == f"Source file for entity 'customers' was refused: {OUTSIDE}"
    assert "private-row-value" not in str(caught.value)


def test_directly_constructed_configurations_are_checked_when_read(tmp_path):
    directory = tmp_path / "data"
    directory.mkdir()
    _write(tmp_path / "customers.csv")
    config = CsvConnectorConfig(source_name="csv_demo", source_type="csv",
                                data_directory=str(directory),
                                entities={"customers": CsvEntityConfig("customers", "../customers.csv",
                                                                       "customer_id")})
    with pytest.raises(ConnectorRequestError) as caught:
        CsvConnector(config).fetch_entities("customers")
    assert str(caught.value) == f"Source file for entity 'customers' was refused: {PLAIN}"


def test_missing_files_keep_their_existing_error(tmp_path):
    with pytest.raises(ConnectorRequestError, match="^Source file not found: "):
        _connector(tmp_path).fetch_entities("customers")


def test_the_committed_csv_configuration_and_demo_files_pass(tmp_path):
    connector = registry.build_connector("csv_demo")
    assert connector._config.max_file_bytes == DEFAULT_MAX_IMPORT_BYTES
    for entity in connector.capabilities().supported_entity_types:
        assert connector.fetch_entities(entity, page_size=1).total_count > 0
    for directory in (REPO / "data" / "demo", REPO / "data" / "fixtures" / "csv_demo_bad"):
        for path in directory.glob("*.csv"):
            assert os.path.getsize(path) < DEFAULT_MAX_IMPORT_BYTES
            assert check_import_file(directory, path.name, DEFAULT_MAX_IMPORT_BYTES) == path.resolve()
