"""
G1 structured logging: log events, the JSON and text formatters, APP_LOG_LEVEL
and LOG_FORMAT, startup configuration, and F1 API events as structured data.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum, StrEnum
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.connectors import ConnectorProvider
from app.api.request_id import REQUEST_ID_HEADER
from app.connectors import registry
from app.core.config import Settings
from app.core.logging import (
    APP_LOGGER,
    HANDLER_NAME,
    RESERVED_FIELDS,
    JsonFormatter,
    StderrHandler,
    TextFormatter,
    configure_logging,
    log_event,
    resolve_format,
    resolve_level,
)
from app.main import create_app

REPO = Path(__file__).resolve().parents[2]
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
RUN_ID = uuid.UUID("5f0c8a52-8f9e-4a53-9d0c-1b2a3c4d5e6f")
# Synthetic credentials for an unreachable server (nothing listens on port 9).
UNREACHABLE_URL = "postgresql://g1_probe:g1-synthetic-password@127.0.0.1:9/g1_unreachable"
LEVELS = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)


class Stage(StrEnum):
    NORMALIZE = "normalize"


class Priority(Enum):
    HIGH = 3


@pytest.fixture(autouse=True)
def app_logger_state():
    """Restore the "app" logger after tests that configure it."""
    logger = logging.getLogger(APP_LOGGER)
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    for handler in handlers:
        if handler.get_name() == HANDLER_NAME:
            logger.removeHandler(handler)
    yield logger
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _emit(level: int, event: str, /, logger_level: int = logging.DEBUG,
          **fields: object) -> list[logging.LogRecord]:
    logger = logging.getLogger("app.g1_test")
    capture = _Capture()
    logger.addHandler(capture)
    logger.setLevel(logger_level)
    try:
        log_event(logger, level, event, **fields)
    finally:
        logger.removeHandler(capture)
        logger.setLevel(logging.NOTSET)
    return capture.records


def _record(level: int = logging.INFO, event: str = "run_finished", /,
            **fields: object) -> logging.LogRecord:
    (record,) = _emit(level, event, **fields)
    return record


def _raised(exc: Exception) -> logging.LogRecord:
    try:
        raise exc
    except type(exc):
        record = logging.LogRecord("app.g1_test", logging.ERROR, __file__, 1, "run_failed", (),
                                   sys.exc_info())
    return record


def _lines(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def _unreachable_sessions() -> sessionmaker:
    return sessionmaker(bind=create_engine(UNREACHABLE_URL, hide_parameters=True,
                                           connect_args={"connect_timeout": 2}))


# --- log_event ------------------------------------------------------------------


def test_the_message_is_the_event_then_its_fields_in_call_order():
    record = _record(logging.WARNING, "batch_committed", run_id=RUN_ID, page=0, has_more=False,
                     stage=Stage.NORMALIZE, error_type=None)
    assert record.getMessage() == (f"batch_committed run_id={RUN_ID} page=0 has_more=False "
                                   "stage=normalize error_type=None")
    assert record.levelno == logging.WARNING
    assert record.event == "batch_committed"
    assert record.event_fields == {"run_id": RUN_ID, "page": 0, "has_more": False,
                                   "stage": Stage.NORMALIZE, "error_type": None}


def test_an_event_without_fields_is_just_its_name():
    record = _record(logging.INFO, "run_started")
    assert (record.getMessage(), record.event_fields) == ("run_started", {})


def test_percent_signs_in_values_are_not_format_directives():
    assert _record(path="/a%s%d").getMessage() == "run_finished path=/a%s%d"


@pytest.mark.parametrize("name", sorted(RESERVED_FIELDS))
def test_reserved_field_names_are_rejected_even_when_the_level_is_disabled(name):
    with pytest.raises(ValueError, match="reserved"):
        _emit(logging.DEBUG, "run_finished", logger_level=logging.CRITICAL, **{name: 1})


def test_a_disabled_level_creates_no_record_and_renders_no_field():
    class Unrenderable:
        def __str__(self) -> str:
            raise AssertionError("fields of a disabled event must not be rendered")

    assert _emit(logging.DEBUG, "record_normalized", logger_level=logging.INFO,
                 value=Unrenderable()) == []
    assert len(_emit(logging.INFO, "run_finished", logger_level=logging.INFO)) == 1


# --- formatters ------------------------------------------------------------------


def test_json_lines_carry_timestamp_level_logger_event_and_typed_fields():
    moment = datetime(2026, 9, 15, 9, 30, tzinfo=UTC)
    record = _record(logging.INFO, "run_finished", run_id=RUN_ID, records=94, ratio=0.25,
                     partial=True, failure=None, stage=Stage.NORMALIZE, at=moment,
                     codes=("A", "B"), note="two\nlines", other=Path("x"))
    line = JsonFormatter().format(record)
    assert "\n" not in line
    payload = json.loads(line)
    assert list(payload)[:4] == ["timestamp", "level", "logger", "event"]
    assert TIMESTAMP.fullmatch(payload.pop("timestamp"))
    assert payload == {
        "level": "INFO", "logger": "app.g1_test", "event": "run_finished",
        "run_id": str(RUN_ID), "records": 94, "ratio": 0.25, "partial": True, "failure": None,
        "stage": "normalize", "at": "2026-09-15T09:30:00+00:00", "codes": ["A", "B"],
        "note": "two\nlines", "other": "x",
    }


def test_json_timestamps_are_the_record_time_in_utc_milliseconds():
    record = _record()
    record.created = datetime(2026, 9, 15, 9, 30, 1, 987654, tzinfo=UTC).timestamp()
    assert json.loads(JsonFormatter().format(record))["timestamp"] == "2026-09-15T09:30:01.987Z"
    record.created = datetime(2026, 9, 15, 15, 0, tzinfo=UTC).astimezone(
        __import__("datetime").timezone(timedelta(hours=5, minutes=30))).timestamp()
    assert TextFormatter().format(record).startswith("2026-09-15T15:00:00.000Z INFO ")


def test_json_renders_records_that_are_not_events_with_their_message():
    record = logging.LogRecord("app.other", logging.WARNING, __file__, 1, "plain %s", ("text",),
                               None)
    payload = json.loads(JsonFormatter().format(record))
    assert TIMESTAMP.fullmatch(payload.pop("timestamp"))
    assert payload == {"level": "WARNING", "logger": "app.other", "event": None,
                       "message": "plain text"}


def test_text_lines_are_timestamp_level_logger_and_message():
    line = TextFormatter().format(_record(logging.ERROR, "run_failed", run_id=RUN_ID,
                                          failure="OperationalError"))
    timestamp, rest = line.split(" ", 1)
    assert TIMESTAMP.fullmatch(timestamp)
    assert rest == f"ERROR app.g1_test run_failed run_id={RUN_ID} failure=OperationalError"


def test_text_lines_escape_line_breaks_so_values_cannot_forge_log_lines():
    forged = "CUST-1\r\n2026-09-15T00:00:00.000Z ERROR app.ingestion run_failed run_id=forged"
    line = TextFormatter().format(_record(logging.WARNING, "record_rejected", source_id=forged))
    assert "\n" not in line and "\r" not in line
    assert line.endswith("record_rejected source_id=CUST-1\\r\\n2026-09-15T00:00:00.000Z ERROR "
                         "app.ingestion run_failed run_id=forged")


@pytest.mark.parametrize("formatter", [JsonFormatter(), TextFormatter()])
def test_formatters_render_only_the_exception_class_never_its_text_or_traceback(formatter):
    record = _raised(RuntimeError("password=hunter2 at postgresql://u:secret@db/x"))
    line = formatter.format(record)
    assert "RuntimeError" in line
    for private in ("hunter2", "secret", "postgresql", "Traceback", __file__):
        assert private not in line
    if isinstance(formatter, JsonFormatter):
        assert json.loads(line)["exception"] == "RuntimeError"
    else:
        assert line.endswith(" run_failed exception=RuntimeError")


def test_records_without_exception_info_have_no_exception_key():
    empty = logging.LogRecord("app.g1_test", logging.ERROR, __file__, 1, "run_failed", (),
                              (None, None, None))
    for record in (_record(), empty):
        assert "exception" not in json.loads(JsonFormatter().format(record))
        assert "exception=" not in TextFormatter().format(record)


def test_enums_that_are_not_strings_render_as_their_values():
    record = _record(logging.INFO, "batch_fetched", priority=Priority.HIGH,
                     levels=[Priority.HIGH, Stage.NORMALIZE])
    assert record.getMessage() == "batch_fetched priority=3 levels=[<Priority.HIGH: 3>, " \
                                  "<Stage.NORMALIZE: 'normalize'>]"
    payload = json.loads(JsonFormatter().format(record))
    assert (payload["priority"], payload["levels"]) == (3, [3, "normalize"])


# --- settings --------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [
    ("DEBUG", "DEBUG"), ("info", "INFO"), (" Warning ", "WARNING"), ("error", "ERROR"),
    ("critical", "CRITICAL"),
])
def test_log_levels_are_case_insensitive(value, expected):
    assert resolve_level(value) == expected


@pytest.mark.parametrize(("value", "expected"), [
    ("json", "json"), ("JSON", "json"), (" text ", "text"), ("Text", "text"),
])
def test_log_formats_are_case_insensitive(value, expected):
    assert resolve_format(value) == expected


@pytest.mark.parametrize("value", ["", "verbose-token-123", "NOTSET", "10", "trace"])
def test_unsupported_levels_are_rejected_without_echoing_the_value(value):
    with pytest.raises(ValueError) as raised:
        resolve_level(value)
    assert str(raised.value) == "APP_LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"


@pytest.mark.parametrize("value", ["", "xml-token-123", "logfmt", "yaml"])
def test_unsupported_formats_are_rejected_without_echoing_the_value(value):
    with pytest.raises(ValueError) as raised:
        resolve_format(value)
    assert str(raised.value) == "LOG_FORMAT must be one of json, text"


def test_settings_default_to_json_at_info_and_read_the_environment(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("APP_LOG_LEVEL", raising=False)
    settings = Settings(_env_file=None)
    assert (settings.log_format, settings.app_log_level) == ("json", "INFO")
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    settings = Settings(_env_file=None)
    assert (settings.log_format, settings.app_log_level) == ("text", "debug")


# --- configure_logging -----------------------------------------------------------


def test_the_default_handler_writes_json_lines_to_the_current_stderr(capsys, app_logger_state):
    handler = configure_logging("INFO", "json")
    assert isinstance(handler, StderrHandler)
    capsys.readouterr()
    log_event(logging.getLogger("app.ingestion.orchestrator"), logging.INFO, "run_started",
              run_id=RUN_ID)
    captured = capsys.readouterr()
    assert captured.out == ""
    (line,) = captured.err.splitlines()
    assert json.loads(line)["event"] == "run_started"
    assert handler.stream is sys.stderr


def test_configuring_twice_keeps_one_layer1_handler_and_other_handlers(app_logger_state):
    other = logging.NullHandler()
    app_logger_state.addHandler(other)
    first = configure_logging("INFO", "json", io.StringIO())
    second = configure_logging("DEBUG", "text", io.StringIO())
    layer1 = [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
    assert layer1 == [second] and first not in app_logger_state.handlers
    assert other in app_logger_state.handlers
    assert isinstance(second.formatter, TextFormatter)
    assert app_logger_state.level == logging.DEBUG


@pytest.mark.parametrize(("setting", "emitted"), [
    ("DEBUG", LEVELS),
    ("INFO", LEVELS[1:]),
    ("WARNING", LEVELS[2:]),
    ("ERROR", LEVELS[3:]),
    ("CRITICAL", LEVELS[4:]),
])
@pytest.mark.parametrize("log_format", ["json", "text"])
def test_app_log_level_filters_events_in_both_formats(setting, emitted, log_format):
    stream = io.StringIO()
    configure_logging(setting, log_format, stream)
    logger = logging.getLogger("app.ingestion.batch")
    for level in LEVELS:
        log_event(logger, level, f"event_{logging.getLevelName(level).lower()}", level_no=level)
    lines = stream.getvalue().splitlines()
    if log_format == "json":
        assert [json.loads(line)["level"] for line in lines] == [
            logging.getLevelName(level) for level in emitted]
    else:
        assert [line.split(" ")[1] for line in lines] == [
            logging.getLevelName(level) for level in emitted]


@pytest.mark.parametrize(("level", "log_format"), [("LOUD", "json"), ("INFO", "xml")])
def test_invalid_settings_leave_the_current_configuration_untouched(level, log_format,
                                                                    app_logger_state):
    installed = configure_logging("WARNING", "json", io.StringIO())
    with pytest.raises(ValueError):
        configure_logging(level, log_format, io.StringIO())
    assert [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME] == [installed]
    assert app_logger_state.level == logging.WARNING


def test_configured_records_still_propagate_to_root_handlers(caplog):
    configure_logging("INFO", "json", io.StringIO())
    with caplog.at_level(logging.INFO):
        log_event(logging.getLogger("app.api.v1.ingestion"), logging.INFO, "ingestion_run_requested",
                  request_id="req-1")
    assert [record.getMessage() for record in caplog.records] == [
        "ingestion_run_requested request_id=req-1"]


# --- application startup ----------------------------------------------------------


def test_startup_configures_logging_from_the_environment(monkeypatch, app_logger_state):
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "text")
    app_logger_state.setLevel(logging.CRITICAL)
    app = create_app(sessions=_unreachable_sessions())
    assert not [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
    with TestClient(app):
        (handler,) = [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
        assert isinstance(handler, StderrHandler)
        assert isinstance(handler.formatter, TextFormatter)
        assert app_logger_state.level == logging.DEBUG
    assert not [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
    assert app_logger_state.level == logging.CRITICAL


def test_shutdown_restores_an_earlier_layer1_handler(monkeypatch, app_logger_state):
    monkeypatch.delenv("APP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    earlier = configure_logging("ERROR", "text", io.StringIO())
    with TestClient(create_app(sessions=_unreachable_sessions())):
        assert earlier not in app_logger_state.handlers
    assert [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME] == [earlier]
    assert app_logger_state.level == logging.ERROR


def test_startup_defaults_to_json_at_info(monkeypatch, app_logger_state):
    monkeypatch.delenv("APP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    with TestClient(create_app(sessions=_unreachable_sessions())):
        (handler,) = [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
        assert isinstance(handler.formatter, JsonFormatter)
        assert app_logger_state.level == logging.INFO


@pytest.mark.parametrize(("variable", "value"), [("LOG_FORMAT", "xml"), ("APP_LOG_LEVEL", "loud")])
def test_invalid_logging_settings_stop_startup(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match=variable), \
            TestClient(create_app(sessions=_unreachable_sessions())):
        pass


# --- F1 API events as structured data ----------------------------------------------


def test_request_failures_are_structured_and_private():
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    app = create_app(sessions=_unreachable_sessions())

    @app.get("/test/crash")
    def crash() -> None:
        raise RuntimeError("crash text that must stay private")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/test/crash", headers={REQUEST_ID_HEADER: "req-g1"})
    assert response.status_code == 500
    (payload,) = _lines(stream)
    payload.pop("timestamp")
    assert payload == {"level": "ERROR", "logger": "app.api.errors", "event": "request_failed",
                       "request_id": "req-g1", "method": "GET", "path": "/test/crash",
                       "failure": "RuntimeError"}
    assert "private" not in stream.getvalue()


def test_readiness_failures_are_structured_without_credentials():
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    response = TestClient(create_app(sessions=_unreachable_sessions())).get("/api/v1/health")
    assert response.status_code == 503
    (payload,) = _lines(stream)
    assert {key: payload[key] for key in ("level", "logger", "event", "dependency", "failure")} \
        == {"level": "WARNING", "logger": "app.api.v1.health", "event": "readiness_check_failed",
            "dependency": "database", "failure": "OperationalError"}
    for private in ("g1-synthetic-password", "g1_probe", "127.0.0.1", "postgresql"):
        assert private not in stream.getvalue()


def test_connector_health_checks_are_structured():
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    provider = ConnectorProvider(registry.build_connector, ("csv_demo",))
    client = TestClient(create_app(sessions=sessionmaker(), connectors=provider))
    assert client.get("/api/v1/sources/csv_demo/health").status_code == 200
    (payload,) = _lines(stream)
    assert {key: payload[key] for key in ("level", "event", "source", "status", "error_type")} \
        == {"level": "INFO", "event": "connector_health_check", "source": "csv_demo",
            "status": "healthy", "error_type": None}


def test_misconfigured_sources_are_structured():
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)

    def broken(source: str):
        raise registry.ConnectorConfigurationError("bad base_url http://internal-host")

    client = TestClient(create_app(sessions=sessionmaker(),
                                   connectors=ConnectorProvider(broken, ("odoo_mock",))),
                        raise_server_exceptions=False)
    assert client.get("/api/v1/sources/odoo_mock/health").status_code == 500
    (payload,) = _lines(stream)
    assert {key: payload[key] for key in ("level", "event", "source", "failure")} == {
        "level": "ERROR", "event": "source_misconfigured", "source": "odoo_mock",
        "failure": "ConnectorConfigurationError"}
    assert "internal-host" not in stream.getvalue()


# --- ingest_demo command ------------------------------------------------------------


def _ingest_demo():
    spec = importlib.util.spec_from_file_location("ingest_demo_g1", REPO / "scripts" / "ingest_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("variable", "value"), [("LOG_FORMAT", "xml"), ("APP_LOG_LEVEL", "loud")])
def test_ingest_demo_rejects_invalid_logging_settings_before_touching_the_database(
        monkeypatch, capsys, variable, value):
    script = _ingest_demo()

    def refuse(*args, **kwargs):
        raise AssertionError("no engine may be created")

    monkeypatch.setattr(script, "create_engine", refuse)
    monkeypatch.setenv(variable, value)
    assert script.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"ingest_demo: invalid logging settings: {variable} must be one of " + (
        "json, text\n" if variable == "LOG_FORMAT" else "DEBUG, INFO, WARNING, ERROR, CRITICAL\n")


def test_ingest_demo_configures_logging_for_the_run_and_restores_it(monkeypatch,
                                                                    app_logger_state):
    script = _ingest_demo()
    observed = []

    class Stop(Exception):
        pass

    def stop(*args, **kwargs):
        observed.extend([h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME])
        observed.append(app_logger_state.level)
        raise Stop

    app_logger_state.setLevel(logging.CRITICAL)
    monkeypatch.setattr(script, "create_engine", stop)
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("APP_LOG_LEVEL", "warning")
    with pytest.raises(Stop):
        script.main([])
    handler, level = observed
    assert isinstance(handler, StderrHandler) and isinstance(handler.formatter, TextFormatter)
    assert level == logging.WARNING
    assert not [h for h in app_logger_state.handlers if h.get_name() == HANDLER_NAME]
    assert app_logger_state.level == logging.CRITICAL
