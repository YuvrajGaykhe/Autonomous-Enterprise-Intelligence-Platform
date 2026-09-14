"""
E1 reconciliation planner tests (pure: no database access).

Classification, duplicate resolution, FK resolution, determinism, and
input immutability of plan_batch.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from e1_support import NOW, csv_canonical

from app.ingestion.reconciliation import (
    REFERENCE_RULES,
    Outcome,
    ReferenceRule,
    parent_keys,
    plan_batch,
)
from app.normalization import default_config
from app.normalization.contract import CANONICAL_SCHEMAS, E1_RESOLVED_FIELDS
from app.persistence.repositories.canonical import PersistedState

pytestmark = pytest.mark.unit

RUN = uuid.UUID("00000000-0000-4000-8000-000000000001")


def _state(record, *, references=None, record_hash=None, source_updated_at="same", id_=None):
    return PersistedState(
        id=id_ or record.id,
        record_hash=record.record_hash if record_hash is None else record_hash,
        source_updated_at=(record.source_updated_at if source_updated_at == "same"
                           else source_updated_at),
        references=references if references is not None else {},
    )


def _outcomes(plan):
    return [(d.record_index, d.source_id, d.outcome) for d in plan.decisions]


# ---------------------------------------------------------------------------
# Reference rules
# ---------------------------------------------------------------------------


def test_reference_rules_cover_exactly_the_e1_resolved_fields():
    assert set(REFERENCE_RULES) == set(CANONICAL_SCHEMAS)
    for entity, rules in REFERENCE_RULES.items():
        assert {rule.field for rule in rules} == E1_RESOLVED_FIELDS[entity]
        for rule in rules:
            assert rule.parent_entity in CANONICAL_SCHEMAS
            if rule.source_key_field is not None:
                assert default_config().fields[entity][rule.source_key_field].kind == "source_key"


def test_employee_organization_has_no_source_key_in_the_canonical_contract():
    assert REFERENCE_RULES["employees"] == (
        ReferenceRule("organization_id", "organizations", None),)
    assert "organization_source_id" not in CANONICAL_SCHEMAS["employees"].model_fields


def test_parent_keys_are_sorted_distinct_and_skip_null_keys():
    deals = [csv_canonical("deals", RUN, deal_id=f"DEAL-{n}", customer_id=key)
             for n, key in enumerate(["CUST-9", "CUST-1", "", "CUST-9"])]
    assert parent_keys("deals", deals) == {"customer_id": ("customers", ("CUST-1", "CUST-9"))}
    assert parent_keys("employees", [csv_canonical("employees", RUN)]) == {}
    assert parent_keys("customers", []) == {}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_new_identity_is_inserted_with_its_canonical_id():
    record = csv_canonical("customers", RUN)
    plan = plan_batch("customers", [(0, record)], {}, {})
    assert _outcomes(plan) == [(0, "CUST-001", Outcome.INSERTED)]
    assert plan.writes == ((record, {}),)
    assert plan.count(Outcome.INSERTED) == 1 and plan.unresolved == ()


def test_identical_persisted_state_is_unchanged_and_not_written():
    record = csv_canonical("customers", RUN)
    plan = plan_batch("customers", [(0, record)], {"CUST-001": _state(record)}, {})
    assert _outcomes(plan) == [(0, "CUST-001", Outcome.UNCHANGED)]
    assert plan.writes == ()


@pytest.mark.parametrize("change", ["record_hash", "source_updated_at"])
def test_changed_hash_or_source_timestamp_is_updated(change):
    record = csv_canonical("documents", RUN)
    state = (_state(record, record_hash="0" * 64) if change == "record_hash"
             else _state(record, source_updated_at=record.source_updated_at - timedelta(days=1)))
    plan = plan_batch("documents", [(0, record)], {"DOC-001": state}, {})
    assert _outcomes(plan) == [(0, "DOC-001", Outcome.UPDATED)]
    assert plan.writes == ((record, {}),)


def test_newly_resolved_reference_updates_an_otherwise_unchanged_child():
    deal = csv_canonical("deals", RUN)
    parent = uuid.uuid4()
    plan = plan_batch("deals", [(0, deal)],
                      {"DEAL-001": _state(deal, references={"customer_id": None})},
                      {"customer_id": {"CUST-001": parent}})
    assert _outcomes(plan) == [(0, "DEAL-001", Outcome.UPDATED)]
    assert plan.writes == ((deal, {"customer_id": parent}),)


def test_same_reference_is_unchanged():
    deal = csv_canonical("deals", RUN)
    parent = uuid.uuid4()
    plan = plan_batch("deals", [(0, deal)],
                      {"DEAL-001": _state(deal, references={"customer_id": parent})},
                      {"customer_id": {"CUST-001": parent}})
    assert _outcomes(plan) == [(0, "DEAL-001", Outcome.UNCHANGED)]


# ---------------------------------------------------------------------------
# Duplicates in one batch
# ---------------------------------------------------------------------------


def test_identical_duplicates_insert_once_then_are_unchanged():
    first = csv_canonical("customers", RUN)
    second = csv_canonical("customers", RUN)
    plan = plan_batch("customers", [(0, first), (3, second)], {}, {})
    assert _outcomes(plan) == [(0, "CUST-001", Outcome.INSERTED), (3, "CUST-001", Outcome.UNCHANGED)]
    assert len(plan.writes) == 1


def test_conflicting_duplicates_resolve_to_the_last_occurrence():
    first = csv_canonical("customers", RUN)
    last = csv_canonical("customers", RUN, customer_name="Acme Renamed")
    plan = plan_batch("customers", [(1, first), (2, last)], {}, {})
    assert _outcomes(plan) == [(1, "CUST-001", Outcome.INSERTED), (2, "CUST-001", Outcome.UPDATED)]
    assert plan.writes == ((last, {}),)


def test_duplicate_reverting_to_persisted_content_still_writes_the_last_occurrence():
    original = csv_canonical("customers", RUN)
    changed = csv_canonical("customers", RUN, customer_name="Acme Renamed")
    reverted = csv_canonical("customers", RUN)
    plan = plan_batch("customers", [(0, changed), (1, reverted)],
                      {"CUST-001": _state(original)}, {})
    assert [d.outcome for d in plan.decisions] == [Outcome.UPDATED, Outcome.UPDATED]
    assert plan.writes == ((reverted, {}),)


def test_later_duplicates_compare_against_the_state_left_by_earlier_ones():
    legacy = uuid.uuid4()
    record = csv_canonical("customers", RUN)
    changed = csv_canonical("customers", RUN, customer_name="Acme Renamed")
    plan = plan_batch("customers", [(0, changed), (1, changed)],
                      {"CUST-001": _state(record, id_=legacy)}, {})
    assert [d.outcome for d in plan.decisions] == [Outcome.UPDATED, Outcome.UNCHANGED]
    assert plan.writes == ((changed, {}),)


# ---------------------------------------------------------------------------
# Foreign-key resolution
# ---------------------------------------------------------------------------


def test_references_resolve_or_are_reported_and_null_keys_are_skipped():
    resolved = csv_canonical("support_tickets", RUN, ticket_id="TKT-1", customer_id="CUST-001")
    missing = csv_canonical("support_tickets", RUN, ticket_id="TKT-2", customer_id="CUST-404")
    keyless = csv_canonical("support_tickets", RUN, ticket_id="TKT-3", customer_id="")
    parent = uuid.uuid4()
    plan = plan_batch("support_tickets", [(0, resolved), (1, missing), (4, keyless)], {},
                      {"customer_id": {"CUST-001": parent}})
    assert plan.writes == ((resolved, {"customer_id": parent}),
                           (missing, {"customer_id": None}),
                           (keyless, {"customer_id": None}))
    assert [(u.record_index, u.source_id, u.source_key, u.rule.field) for u in plan.unresolved] == [
        (1, "TKT-2", "CUST-404", "customer_id")]
    assert missing.customer_source_id == "CUST-404"


def test_employee_organization_stays_null_without_a_finding():
    employee = csv_canonical("employees", RUN)
    plan = plan_batch("employees", [(0, employee)], {}, {})
    assert plan.writes == ((employee, {"organization_id": None}),)
    assert plan.unresolved == ()


# ---------------------------------------------------------------------------
# Guards, determinism, immutability
# ---------------------------------------------------------------------------


def test_invalid_planner_inputs_are_rejected():
    deal = csv_canonical("deals", RUN)
    customer = csv_canonical("customers", RUN)
    with pytest.raises(ValueError):
        plan_batch("deals", [(0, deal)], {}, {})
    with pytest.raises(ValueError):
        plan_batch("customers", [(0, customer)], {}, {"customer_id": {}})
    with pytest.raises(ValueError):
        plan_batch("deals", [(0, customer)], {}, {"customer_id": {}})
    with pytest.raises(ValueError):
        plan_batch("customers", [(1, customer), (1, customer)], {}, {})
    with pytest.raises(ValueError):
        plan_batch("invoices", [], {}, {})


def test_writes_are_ordered_by_source_id_and_planning_is_repeatable():
    records = [(i, csv_canonical("customers", RUN, customer_id=cid))
               for i, cid in enumerate(["CUST-003", "CUST-001", "CUST-002"])]
    first = plan_batch("customers", records, {}, {})
    second = plan_batch("customers", records, {}, {})
    assert [record.source_id for record, _ in first.writes] == ["CUST-001", "CUST-002", "CUST-003"]
    assert first == second


def test_planning_does_not_mutate_inputs():
    deal = csv_canonical("deals", RUN, ingested_at=NOW)
    before = deal.model_dump()
    existing = {"DEAL-001": _state(deal, references={"customer_id": None})}
    parents = {"customer_id": {"CUST-001": uuid.uuid4()}}
    snapshot = (dict(existing), {k: dict(v) for k, v in parents.items()})
    plan_batch("deals", [(0, deal)], existing, parents)
    assert deal.model_dump() == before and deal.customer_id is None
    assert (dict(existing), {k: dict(v) for k, v in parents.items()}) == snapshot
    assert dict(existing["DEAL-001"].references) == {"customer_id": None}
