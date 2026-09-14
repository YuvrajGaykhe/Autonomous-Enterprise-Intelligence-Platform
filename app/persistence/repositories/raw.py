"""
source_records raw capture (spec Section 9 step 6, Section 7 "Raw boundary").

source_records is append-only: every run stores the raw payload it received
for each record with a known source identity, so every run's input stays
auditable. The payload is stored exactly as the connector returned it
(spec Section 5: "never overwrite the original raw value").

Connectors return JSON-native records (CSV strings, decoded JSON). A payload
that is not a mapping of JSON values violates the connector contract; it is a
system failure (RawPayloadError), never a record-level data failure.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.persistence.models import SourceRecord


class RawPayloadError(Exception):
    """A connector payload is not a JSON object. Messages never include values."""


@dataclass(frozen=True)
class RawRecord:
    """One raw payload with the source identity D1 extracted for it."""

    source_id: str
    payload: Mapping[str, object]


def _check_json(value: object, path: str) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RawPayloadError(f"non-finite number at {path}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_json(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RawPayloadError(f"non-string key of type {type(key).__name__} at {path}")
            _check_json(item, f"{path}.<key>")
        return
    raise RawPayloadError(f"value of type {type(value).__name__} at {path} is not JSON")


def canonical_json(payload: object) -> str:
    """Deterministic JSON text of a raw payload (sorted keys, compact, UTF-8)."""
    if not isinstance(payload, Mapping):
        raise RawPayloadError(f"raw payload must be a mapping, got {type(payload).__name__}")
    _check_json(payload, "$")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def content_hash(payload: object) -> str:
    """Hex SHA-256 of the canonical JSON text of a raw payload."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def add_source_records(
    session: Session,
    *,
    run_id: uuid.UUID,
    source_system: str,
    source_entity: str,
    records: Sequence[RawRecord],
    ingested_at: datetime,
) -> int:
    """Append raw payloads for one run and return the number of rows written."""
    if ingested_at.utcoffset() is None:
        raise ValueError("ingested_at must be timezone-aware")
    rows = []
    for record in records:
        text = canonical_json(record.payload)
        rows.append({
            "id": uuid.uuid4(),
            "source_system": source_system,
            "source_entity": source_entity,
            "source_id": record.source_id,
            "ingestion_run_id": run_id,
            "raw_payload": json.loads(text),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "ingested_at": ingested_at,
        })
    if rows:
        session.execute(insert(SourceRecord), rows)
    return len(rows)
