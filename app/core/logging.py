"""
Structured logging for Layer 1 (spec Section 16).

Application code logs events, not free text:

    log_event(logger, logging.INFO, "run_finished", run_id=run_id, status="SUCCESS")

The record's message is the readable "event key=value ..." line, and the
event name and fields also travel on the record, so the formatter chosen by
LOG_FORMAT can render them as structured data:

    json  one JSON object per line: timestamp, level, logger, event and the
          event's fields as typed JSON values (default)
    text  "<timestamp> <LEVEL> <logger> <event key=value ...>" for reading locally

configure_logging installs a single handler on the "app" logger (stderr, so
command output on stdout stays machine-readable) with the level from
APP_LOG_LEVEL; configured_logging does the same for the lifetime of an
application or command and then restores the previous configuration.
Invalid settings raise ValueError at startup rather than silently logging
nothing. Records still propagate to the root logger.

Callers pass identifiers, counts, statuses, durations and exception class
names only: never source values, payloads, connector messages or
credentials. Neither formatter renders exception messages or tracebacks,
which can quote source values or connection strings; a record carrying
exception info reports only the exception class.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from typing import TextIO

APP_LOGGER = "app"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_FORMATS = ("json", "text")
EVENT_ATTRIBUTE = "event"
FIELDS_ATTRIBUTE = "event_fields"
# Keys every JSON line owns; event fields may not reuse them.
RESERVED_FIELDS = frozenset({"timestamp", "level", "logger", "event", "message", "exception"})
HANDLER_NAME = "layer1"


def log_event(logger: logging.Logger, level: int, event: str, /, **fields: object) -> None:
    """Log one structured event whose message is "event key=value ..." in field order."""
    reserved = RESERVED_FIELDS.intersection(fields)
    if reserved:
        raise ValueError(f"log fields {sorted(reserved)} are reserved")
    if not logger.isEnabledFor(level):
        return
    message = " ".join([event, *(f"{name}={_text(value)}" for name, value in fields.items())])
    logger.log(level, "%s", message, extra={EVENT_ATTRIBUTE: event, FIELDS_ATTRIBUTE: fields})


def _text(value: object) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def _json_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return str(value)


def _timestamp(record: logging.LogRecord) -> str:
    moment = datetime.fromtimestamp(record.created, UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _exception_class(record: logging.LogRecord) -> str | None:
    if record.exc_info and record.exc_info[0] is not None:
        return record.exc_info[0].__name__
    return None


class JsonFormatter(logging.Formatter):
    """One JSON object per line; unstructured records carry event null and their message."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _timestamp(record), "level": record.levelname, "logger": record.name,
        }
        event = getattr(record, EVENT_ATTRIBUTE, None)
        if isinstance(event, str):
            payload["event"] = event
            fields = getattr(record, FIELDS_ATTRIBUTE, {})
            payload.update((name, _json_value(value)) for name, value in fields.items())
        else:
            payload["event"] = None
            payload["message"] = record.getMessage()
        exception = _exception_class(record)
        if exception is not None:
            payload["exception"] = exception
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """"<timestamp> <LEVEL> <logger> <message>", with the exception class if any.

    Carriage returns and newlines in the message are escaped, so a field value
    can never start a forged log line.
    """

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage().replace("\r", "\\r").replace("\n", "\\n")
        line = f"{_timestamp(record)} {record.levelname} {record.name} {message}"
        exception = _exception_class(record)
        return line if exception is None else f"{line} exception={exception}"


def resolve_level(value: str) -> str:
    """The logging level name for APP_LOG_LEVEL (case-insensitive)."""
    level = value.strip().upper()
    if level not in LOG_LEVELS:
        raise ValueError(f"APP_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
    return level


def resolve_format(value: str) -> str:
    """The formatter name for LOG_FORMAT (case-insensitive)."""
    log_format = value.strip().lower()
    if log_format not in LOG_FORMATS:
        raise ValueError(f"LOG_FORMAT must be one of {', '.join(LOG_FORMATS)}")
    return log_format


class StderrHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Writes to whatever sys.stderr is when a record is emitted, never a stale stream."""

    @property  # type: ignore[override]
    def stream(self) -> TextIO:
        return sys.stderr

    @stream.setter
    def stream(self, _: TextIO) -> None:
        pass


def configure_logging(level: str, log_format: str, stream: TextIO | None = None) -> logging.Handler:
    """Install the Layer 1 handler on the "app" logger, replacing any earlier one.

    Logs go to the current sys.stderr unless a stream is given.

    Raises:
        ValueError: level or log_format is not supported.
    """
    level_name = resolve_level(level)
    formatter = JsonFormatter() if resolve_format(log_format) == "json" else TextFormatter()
    logger = logging.getLogger(APP_LOGGER)
    for existing in list(logger.handlers):
        if existing.get_name() == HANDLER_NAME:
            logger.removeHandler(existing)
    handler = StderrHandler() if stream is None else logging.StreamHandler(stream)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level_name)
    return handler


@contextmanager
def configured_logging(
    level: str,
    log_format: str,
    stream: TextIO | None = None,
) -> Iterator[logging.Handler]:
    """configure_logging for the duration of an application or command run.

    On exit the "app" logger gets back the Layer 1 handler and level it had
    before, so repeated in-process runs (tests, embedded apps) do not leak
    configuration into each other.

    Raises:
        ValueError: level or log_format is not supported; nothing is changed.
    """
    logger = logging.getLogger(APP_LOGGER)
    previous_level = logger.level
    previous = [handler for handler in logger.handlers if handler.get_name() == HANDLER_NAME]
    handler = configure_logging(level, log_format, stream)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        for earlier in previous:
            logger.addHandler(earlier)
        logger.setLevel(previous_level)
