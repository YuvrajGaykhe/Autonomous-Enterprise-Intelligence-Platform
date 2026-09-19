"""
M1 Scope invariants that need no database.

Scope is the complete statement of what an assessment was computed over.
Its identity must depend on the canonical content and on nothing volatile,
so the type refuses a timestamp where a date belongs and refuses to describe
a snapshot it has not counted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.intelligence.errors import ContractViolationError
from app.intelligence.scope import DEFAULT_SOURCE_SYSTEM, AsOfSource, Scope
from app.persistence.repositories.canonical import ENTITY_MODELS

FINGERPRINT = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"
COUNTS = {"organizations": 1, "employees": 24, "customers": 50, "deals": 44,
          "projects": 22, "support_tickets": 80, "documents": 12}


def make_scope(**overrides) -> Scope:
    arguments = {
        "source_system": DEFAULT_SOURCE_SYSTEM,
        "as_of": date(2026, 9, 18),
        "layer1_fingerprint": FINGERPRINT,
        "as_of_source": AsOfSource.EXPLICIT,
        "entity_counts": COUNTS,
    }
    arguments.update(overrides)
    return Scope(**arguments)


def test_a_scope_names_its_source_system_its_date_and_its_snapshot():
    scope = make_scope()

    assert scope.source_system == "csv_demo"
    assert scope.as_of == date(2026, 9, 18)
    assert scope.layer1_fingerprint == FINGERPRINT
    assert scope.as_of_source is AsOfSource.EXPLICIT
    assert scope.record_count == 233


def test_a_scope_needs_a_source_system():
    with pytest.raises(ContractViolationError, match="source_system must be"):
        make_scope(source_system="  ")


def test_a_scope_date_is_a_calendar_date_not_a_timestamp():
    """A time of day would make two runs on the same day disagree."""
    with pytest.raises(ContractViolationError, match="must be a calendar date"):
        make_scope(as_of=datetime(2026, 9, 18, 10, 30, tzinfo=UTC))


def test_a_scope_date_must_be_a_date_at_all():
    with pytest.raises(ContractViolationError, match="must be a calendar date"):
        make_scope(as_of="2026-09-18")


def test_a_scope_must_account_for_every_canonical_entity_type():
    """An entity type left out of the count is one the fingerprint did not cover."""
    partial = dict.fromkeys(list(ENTITY_MODELS)[:-1], 0)

    with pytest.raises(ContractViolationError, match="every canonical entity type"):
        make_scope(entity_counts=partial)


def test_a_scope_payload_carries_no_timestamp_and_no_run_id():
    """Assessment identity must not move because a row was re-ingested."""
    payload = make_scope().to_payload()

    assert payload == {
        "source_system": "csv_demo",
        "as_of": "2026-09-18",
        "layer1_fingerprint": FINGERPRINT,
        "as_of_source": "EXPLICIT",
        "entity_counts": dict(sorted(COUNTS.items())),
    }
    assert not {"ingested_at", "ingestion_run_id", "source_updated_at"} & set(payload)


def test_two_scopes_over_the_same_snapshot_are_the_same_identity():
    assert make_scope().to_payload() == make_scope().to_payload()


def test_a_different_snapshot_is_a_different_identity():
    assert make_scope().to_payload() != make_scope(layer1_fingerprint="0" * 64).to_payload()


def test_a_different_evaluation_date_is_a_different_identity():
    assert make_scope().to_payload() != make_scope(as_of=date(2026, 8, 27)).to_payload()
