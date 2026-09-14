"""
E1 batch unit of work: one fetched page is one database transaction.

Transaction policy (spec Section 8): records are processed in bounded
batches, never one giant transaction. Inside a single transaction a batch

    1. takes a transaction-scoped advisory lock on (source_system, entity), so
       concurrent runs of the same source entity reconcile serially,
    2. appends raw payloads for every record with a known source identity,
    3. loads persisted state and same-source parents (one query each),
    4. plans and upserts canonical records (reconciliation module),
    5. records quarantined records, D2 warnings and unresolved references,
    6. adds the batch counts to the run, and
    7. on an entity's final page, advances the checkpoint.

Either all of it commits or none of it does: persisted run counts always
reconcile with committed rows, and a checkpoint never passes a failed batch.
Database and payload errors propagate unchanged after rollback; classifying
them is the orchestrator's job, never this module's.

Quarantine and warning rows carry D2's redacted payloads verbatim; E1 does
not re-validate records.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.errors import IngestionCode
from app.ingestion.reconciliation import (
    Outcome,
    UnresolvedReference,
    parent_keys,
    plan_batch,
)
from app.persistence.repositories import canonical as canonical_repo
from app.persistence.repositories import cursors, errors, raw, runs
from app.schemas.canonical import CanonicalBase
from app.validation import QualityFinding, QualityGateResult, QuarantineRecord


@dataclass(frozen=True)
class Checkpoint:
    """Passed with an entity's final page; the entity completes with that batch."""

    last_cursor: str | None = None


@dataclass(frozen=True)
class BatchResult:
    counts: runs.RunCounts
    raw_persisted: int
    errors_recorded: int
    unresolved_references: int


def lock_key(source_system: str, entity_type: str) -> str:
    return f"e1-batch:{source_system}:{entity_type}"


def acquire_batch_lock(session: Session, source_system: str, entity_type: str) -> None:
    """Block until this transaction holds the advisory lock for the source entity."""
    key = func.hashtextextended(lock_key(source_system, entity_type), 0)
    session.execute(select(func.pg_advisory_xact_lock(key)))


def valid_record_indices(gate: QualityGateResult) -> tuple[int, ...]:
    """Input indices of the gate's valid records, in order."""
    rejected = {record.record_index for record in gate.quarantined}
    indices = tuple(index for index in range(gate.total_records) if index not in rejected)
    if len(indices) != len(gate.valid):
        raise ValueError("quality gate result does not partition its input records")
    return indices


def commit_batch(
    sessions: sessionmaker[Session],
    *,
    run_id: uuid.UUID,
    gate: QualityGateResult,
    raw_records: Sequence[object],
    ingested_at: datetime,
    checkpoint: Checkpoint | None = None,
) -> BatchResult:
    """Persist one quality-gated batch atomically and return its accounting."""
    if gate.ingestion_run_id != run_id:
        raise ValueError("quality gate result belongs to a different ingestion run")
    if len(raw_records) != gate.total_records:
        raise ValueError("raw_records must be the exact records given to the quality gate")

    source_system, entity_type = gate.source_system, gate.entity_type
    indexed = tuple(zip(valid_record_indices(gate), gate.valid, strict=True))
    valid = [record for _, record in indexed]

    with sessions.begin() as session:
        acquire_batch_lock(session, source_system, entity_type)
        raw_persisted = raw.add_source_records(
            session, run_id=run_id, source_system=source_system, source_entity=entity_type,
            records=_raw_records(indexed, gate.quarantined, raw_records), ingested_at=ingested_at,
        )
        existing = canonical_repo.load_states(session, entity_type, source_system,
                                              [record.source_id for record in valid])
        parents = {
            field: {key: state.id for key, state in canonical_repo.load_states(
                session, parent_entity, source_system, keys).items()}
            for field, (parent_entity, keys) in parent_keys(entity_type, valid).items()
        }
        plan = plan_batch(entity_type, indexed, existing, parents)
        canonical_repo.upsert(session, entity_type, [
            canonical_repo.canonical_row(entity_type, record, references)
            for record, references in plan.writes
        ])
        entries = _error_entries(gate, plan.unresolved)
        errors.add_errors(session, run_id, entries, created_at=ingested_at)
        counts = runs.RunCounts(
            fetched=gate.total_records,
            inserted=plan.count(Outcome.INSERTED),
            updated=plan.count(Outcome.UPDATED),
            unchanged=plan.count(Outcome.UNCHANGED),
            rejected=gate.quarantined_count,
            warnings=gate.warning_count + len(plan.unresolved),
        )
        runs.add_run_counts(session, run_id, counts)
        if checkpoint is not None:
            cursors.record_entity_success(
                session, source_system=source_system, source_entity=entity_type, run_id=run_id,
                last_cursor=checkpoint.last_cursor, updated_at=ingested_at,
            )
    return BatchResult(counts=counts, raw_persisted=raw_persisted, errors_recorded=len(entries),
                       unresolved_references=len(plan.unresolved))


def _raw_records(
    valid: Sequence[tuple[int, CanonicalBase]],
    quarantined: Sequence[QuarantineRecord],
    raw_records: Sequence[object],
) -> list[raw.RawRecord]:
    """Raw payloads of every record whose source identity is known, in input order."""
    identified = [(index, record.source_id) for index, record in valid]
    identified += [(record.record_index, record.source_id) for record in quarantined
                   if record.source_id is not None]
    return [
        raw.RawRecord(source_id, cast(Mapping[str, object], raw_records[index]))
        for index, source_id in sorted(identified)
    ]


def _detail(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _error_entries(
    gate: QualityGateResult,
    unresolved: Sequence[UnresolvedReference],
) -> list[errors.ErrorEntry]:
    """ERROR rows for quarantined records, then WARNING rows, ordered by record index."""
    ranked: list[tuple[int, int, errors.ErrorEntry]] = []
    for record in gate.quarantined:
        ranked.append((record.record_index, 0, _quarantine_entry(record)))
    for finding in gate.warnings:
        ranked.append((finding.record_index, 1, _warning_entry(gate, finding)))
    for reference in unresolved:
        ranked.append((reference.record_index, 2, _unresolved_entry(gate, reference)))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in ranked]


def _quarantine_entry(record: QuarantineRecord) -> errors.ErrorEntry:
    return errors.ErrorEntry(
        severity="ERROR", error_code=record.code, message=record.message,
        source_system=record.source_system, source_entity=record.entity_type,
        source_id=record.source_id, detail=_detail(record.to_dict()),
    )


def _warning_entry(gate: QualityGateResult, finding: QualityFinding) -> errors.ErrorEntry:
    return errors.ErrorEntry(
        severity="WARNING", error_code=finding.code, message=finding.message,
        source_system=gate.source_system, source_entity=gate.entity_type,
        source_id=finding.source_id, detail=_detail(finding.to_dict()),
    )


def _unresolved_entry(gate: QualityGateResult, reference: UnresolvedReference) -> errors.ErrorEntry:
    rule = reference.rule
    return errors.ErrorEntry(
        severity="WARNING", error_code=IngestionCode.UNRESOLVED_REFERENCE.value,
        message=(f"{rule.source_key_field} does not resolve to a {rule.parent_entity} record "
                 f"from this source system; {rule.field} left null"),
        source_system=gate.source_system, source_entity=gate.entity_type,
        source_id=reference.source_id,
        detail=_detail({
            "severity": "WARNING",
            "code": IngestionCode.UNRESOLVED_REFERENCE.value,
            "record_index": reference.record_index,
            "source_id": reference.source_id,
            "field_name": rule.field,
            "source_key_field": rule.source_key_field,
            "source_key": reference.source_key,
            "parent_entity": rule.parent_entity,
        }),
    )
