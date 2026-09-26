"""
M8's six risk routes against a real database (§0.7.8, §0.7.9, §0.7.13).

Route 1 runs over the clean full-dataset path at ACCEPTANCE_AS_OF, unpinned,
and must answer exactly what a direct run_assessment answers, in the same
order, with M7's measured payload hashes: 201 when any result was created,
200 when none was. The reads are checked against the stored rows and the
golden narrative, the decision route against an injected clock, and every
failure against §0.7.9's fixed status, code and message, with every table's
row count unchanged, because a failing request owns and rolls back its one
transaction. Last, §A28's demo is replayed end to end through the client.

No test reads the wall clock: the client overrides get_clock, and the one
test of the default clock checks its type and zone, never its value.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.request_id import REQUEST_ID_HEADER
from app.api.v1 import risk
from app.api.v1.risk import get_clock
from app.connectors import CsvConnector, CsvConnectorConfig
from app.core.database import Base
from app.core.logging import FIELDS_ATTRIBUTE
from app.decisions import approval
from app.decisions.approval import (
    DecisionConflict,
    DecisionConflictError,
    HashConflict,
    PayloadHashConflictError,
)
from app.decisions.assessment import run_assessment
from app.decisions.payload import canonical_json, payload_citations
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.main import create_app
from app.persistence.models import Customer, Deal, RiskAssessment, RiskBrief, SupportTicket

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
GOLDEN = REPO / "tests" / "golden" / "vs01_cust007_brief.txt"
ACCEPTANCE_AS_OF = date(2026, 9, 18)
ASSESSMENTS = "/api/v1/risk/assessments"
BRIEFS = "/api/v1/risk/briefs"
DECIDED_AT = datetime(2026, 9, 26, 9, 30, tzinfo=UTC)

#: M7's measured payload hashes (§0.7.13), one per briefed customer, in ranking order.
BRIEF_HASHES = {
    "CUST-007": "e93c29cfb6094284d7ea6fe84bf966ad0b40995fccdc4e2a671b502a7f16c946",
    "CUST-025": "08c99ced40996611c8f7bb4ea48e918fabe0e9cd68390122d0f86faa50738770",
    "CUST-036": "a6240ac1edd4890724568adc7a8bd8f99add305638b9dcb179429ae67d06b637",
}
MERIDIAN_HASH = BRIEF_HASHES["CUST-007"]

#: §0.5.7's ordered positions for CUST-007, as (function, action, object_ref, stance).
MERIDIAN_POSITIONS = [
    ("SALES", "ACCELERATE_DEAL_CLOSE", "DEAL-001", "ADVANCE"),
    ("SUPPORT", "ASSIGN_DEDICATED_SUPPORT_OWNER", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "SCHEDULE_EXECUTIVE_SPONSOR_CALL", "CUST-007", "NEUTRAL"),
    ("SUPPORT", "PAUSE_DEAL_PUSH_UNTIL_TICKETS_RESOLVED", "DEAL-001", "RESTRAIN"),
    ("SUPPORT", "REVIEW_INVOICE_DISPUTE", "TKT-079", "NEUTRAL"),
]

#: Canaries a request carries into a failure: none may come back in an error body.
EMAIL_CANARY = "m8-canary-7f3a@example.invalid"
DOCUMENT_CANARY = "m8-canary-document-text: renewal clause 4.2 waives the SLA credit"


def _connector() -> CsvConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


def counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables}


def client_for(sessions, clock=lambda: DECIDED_AT) -> TestClient:
    app = create_app(sessions=sessions)
    app.dependency_overrides[get_clock] = lambda: clock
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 0 rejected."""
    assert run_ingestion(_connector(), e1_sessions, IngestionRequest()).counts.rejected == 0
    return e1_sessions


@pytest.fixture
def client(e1_sessions) -> TestClient:
    return client_for(e1_sessions)


@pytest.fixture
def assessed(demo, client) -> list[dict[str, Any]]:
    response = client.post(ASSESSMENTS, json={"as_of": ACCEPTANCE_AS_OF.isoformat()})
    assert response.status_code == 201
    return response.json()["items"]


@pytest.fixture
def meridian_brief(assessed) -> str:
    (brief_id,) = [item["brief_id"] for item in assessed if item["payload_hash"] == MERIDIAN_HASH]
    return brief_id


def assert_error(response, status: int, code: str, message: str, details: object = None) -> None:
    assert response.status_code == status, response.text
    assert response.json() == {"error": {
        "code": code, "message": message, "details": details,
        "request_id": response.headers[REQUEST_ID_HEADER]}}


def decide(client, brief_id: str, **changes: object):
    body: dict[str, object] = {"actor": "ceo@example.invalid", "decision": "REJECTED",
                               "payload_hash": MERIDIAN_HASH}
    body.update(changes)
    return client.post(f"{BRIEFS}/{brief_id}/decision", json=body)


# ---------------------------------------------------------------------------
# Route 1: POST /risk/assessments
# ---------------------------------------------------------------------------


def test_the_first_run_answers_201_with_a_direct_runs_results_in_its_order(demo, client):
    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert response.status_code == 201
    items = response.json()["items"]
    with demo.begin() as session:
        direct = run_assessment(session, as_of=ACCEPTANCE_AS_OF)
    assert [(item["assessment_id"], item["brief_id"], item["payload_hash"]) for item in items] == [
        (str(one.assessment_id), None if one.brief_id is None else str(one.brief_id),
         one.payload_hash) for one in direct]
    assert all(item["created"] for item in items)
    assert not any(one.created for one in direct)
    assert [item["payload_hash"] for item in items if item["payload_hash"]] == list(
        BRIEF_HASHES.values())
    assert len(items) == 50


def test_a_repeat_answers_200_with_identical_results_and_writes_nothing(demo, client, assessed):
    before = counts(demo)

    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert response.status_code == 200
    assert response.json()["items"] == [{**item, "created": False} for item in assessed]
    assert counts(demo) == before


def test_one_synthetic_ticket_answers_201_with_new_rows(demo, client, assessed):
    """§A25 test 13 through the route: a new Layer 1 snapshot is a new set of assessments."""
    with demo.begin() as session:
        customer_id = session.scalar(select(Customer.id).where(Customer.source_id == "CUST-001"))
        session.add(SupportTicket(
            source_system="csv_demo", source_entity="support_tickets", source_id="TKT-900",
            record_hash="9" * 64, ingestion_run_id=uuid.uuid4(), subject="synthetic",
            priority="low", status="open", category="onboarding",
            created_at=datetime(2026, 9, 1, 10, tzinfo=UTC), customer_source_id="CUST-001",
            customer_id=customer_id))
    before = counts(demo)

    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert response.status_code == 201
    assert all(item["created"] for item in response.json()["items"])
    assert counts(demo)["risk_assessments"] == before["risk_assessments"] + 50


def test_a_null_as_of_asks_for_the_scopes_fallback_explicitly(demo, client):
    response = client.post(ASSESSMENTS, json={"as_of": None})

    assert response.status_code == 201
    with demo.begin() as session:
        direct = run_assessment(session, as_of=None)
    assert [item["assessment_id"] for item in response.json()["items"]] == [
        str(one.assessment_id) for one in direct]


def test_one_named_customer_is_assessed_alone(demo, client):
    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18",
                                              "customer_source_id": "CUST-007"})

    assert response.status_code == 201
    (item,) = response.json()["items"]
    assert (item["payload_hash"], item["created"]) == (MERIDIAN_HASH, True)


def test_a_run_that_creates_some_results_and_reads_back_others_answers_201(demo, client):
    """X8: 201 iff at least one result was created, not only when every one was."""
    single = client.post(ASSESSMENTS, json={"as_of": "2026-09-18",
                                            "customer_source_id": "CUST-007"})

    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert (single.status_code, response.status_code) == (201, 201)
    created = {item["assessment_id"]: item["created"] for item in response.json()["items"]}
    assert created.pop(single.json()["items"][0]["assessment_id"]) is False
    assert all(created.values()) and len(created) == 49


def test_a_scope_with_no_customer_answers_200_because_nothing_was_created(demo, client):
    """X8: 201 iff some result was created. An empty scope creates nothing."""
    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18",
                                              "source_system": "rest_mock"})

    assert (response.status_code, response.json()) == (200, {"items": []})


def test_two_concurrent_identical_requests_converge_on_one_result_set(demo):
    barrier = threading.Barrier(2)
    responses: list[Any] = []

    def post() -> None:
        client = client_for(demo)
        barrier.wait()
        responses.append(client.post(ASSESSMENTS, json={"as_of": "2026-09-18"}))

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(response.status_code for response in responses) == [200, 201]
    first, second = (response.json()["items"] for response in responses)
    assert [item["assessment_id"] for item in first] == [item["assessment_id"] for item in second]
    after = counts(demo)
    assert (after["risk_assessments"], after["risk_positions"], after["risk_briefs"]) == (50, 15, 3)


def test_an_unknown_customer_in_the_body_is_422_and_writes_nothing(demo, client):
    before = counts(demo)

    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18",
                                              "customer_source_id": EMAIL_CANARY})

    assert_error(response, 422, "CUSTOMER_NOT_FOUND", "customer is not in the assessment scope")
    assert counts(demo) == before


def test_a_null_as_of_the_scope_cannot_resolve_is_422_and_writes_nothing(e1_sessions, client):
    before = counts(e1_sessions)

    response = client.post(ASSESSMENTS, json={"as_of": None})

    assert_error(response, 422, "SCOPE_UNRESOLVED",
                 "as_of is null and the scope has no support ticket to resolve it from")
    assert counts(e1_sessions) == before


@pytest.mark.parametrize("body", [
    {}, {"as_of": "2026-09-18", "expected_fingerprint": "a" * 64},
    {"as_of": "2026-09-18", "source_system": ""}, {"as_of": "not a date"},
])
def test_an_invalid_assessment_body_is_422_invalid_request(e1_sessions, client, body):
    before = counts(e1_sessions)

    response = client.post(ASSESSMENTS, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert counts(e1_sessions) == before


def test_an_unresolvable_conflict_is_500_and_nothing_the_run_wrote_is_durable(demo, client):
    """M6's DEAL-037 edit: M4's links are derived first, and the rollback removes them too."""
    with demo.begin() as session:
        session.execute(update(Deal).where(Deal.source_id == "DEAL-037")
                        .values(stage="negotiation", probability=90))
    before = counts(demo)

    response = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert_error(response, 500, "INTERNAL_ERROR", "internal server error")
    assert counts(demo) == before


# ---------------------------------------------------------------------------
# Route 2: GET /risk/assessments
# ---------------------------------------------------------------------------


def listing(client, **params: object) -> dict[str, Any]:
    response = client.get(ASSESSMENTS, params={"limit": 500, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_executive_worthy_at_acceptance_is_exactly_meridian_with_its_brief(
        client, assessed, meridian_brief):
    body = listing(client, as_of="2026-09-18", executive_worthy="true")

    assert body["total"] == 1
    (item,) = body["items"]
    assert (item["customer_source_id"], item["band"], item["executive_worthy"]) == (
        "CUST-007", "CRITICAL", True)
    assert item["brief_ids"] == [meridian_brief]
    assert item["ranking_key"] == [-3, -3, -5, "CUST-007"]


def test_the_listing_is_the_runs_order_with_every_briefs_id(client, assessed):
    body = listing(client, as_of="2026-09-18")

    assert [item["id"] for item in body["items"]] == [one["assessment_id"] for one in assessed]
    assert [item["brief_ids"] for item in body["items"]] == [
        [] if one["brief_id"] is None else [one["brief_id"]] for one in assessed]
    assert body["total"] == 50


@pytest.mark.parametrize(("params", "expected"), [
    ({"band": "CRITICAL"}, lambda item: item["band"] == "CRITICAL"),
    ({"band": "WATCH"}, lambda item: item["band"] == "WATCH"),
    ({"band": "ELEVATED"}, lambda item: False),
    ({"executive_worthy": "false"}, lambda item: not item["executive_worthy"]),
    ({"as_of": "2026-09-17"}, lambda item: False),
    ({"as_of": "2026-09-18", "band": "NONE", "executive_worthy": "false"},
     lambda item: item["band"] == "NONE"),
])
def test_each_filter_is_an_exact_match_combined_with_and(client, assessed, params, expected):
    everything = listing(client)["items"]

    body = listing(client, **params)

    assert body["items"] == [item for item in everything if expected(item)]
    assert body["total"] == len(body["items"])


@pytest.mark.parametrize("params", [{"band": "HIGH"}, {"band": "critical"},
                                    {"as_of": "18/09/2026"}, {"executive_worthy": "sometimes"}])
def test_a_filter_outside_its_vocabulary_is_422(client, params):
    response = client.get(ASSESSMENTS, params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_pages_slice_the_one_order_and_echo_their_window(client, assessed):
    whole = [item["id"] for item in listing(client)["items"]]

    page = client.get(ASSESSMENTS, params={"limit": 7, "offset": 10}).json()
    default = client.get(ASSESSMENTS).json()

    assert [item["id"] for item in page["items"]] == whole[10:17]
    assert (page["total"], page["limit"], page["offset"]) == (50, 7, 10)
    assert (default["limit"], default["offset"], len(default["items"])) == (50, 0, 50)


def test_code_point_order_decides_the_source_id_where_a_locale_would_not(e1_sessions, client):
    """§0.7.8: the source_id key is compared by code point, as order_reconciliations() compares it."""
    rows = [{"id": uuid.UUID(int=index), "customer_id": None, "as_of": ACCEPTANCE_AS_OF,
             "source_system": "csv_demo", "layer1_fingerprint": "a" * 64, "rules_version": 1,
             "linker_version": "1", "band": "WATCH", "executive_worthy": False, "signals": {},
             "satisfied_rules": [], "ranking_key": [-1, 0, 0, source_id]}
            for index, source_id in enumerate(["cust-a", "CUST-B", "Cust-c"], start=1)]
    with e1_sessions.begin() as session:
        session.execute(insert(RiskAssessment), rows)

    keys = [item["ranking_key"][3] for item in listing(client)["items"]]

    assert keys == sorted(["cust-a", "CUST-B", "Cust-c"]) == ["CUST-B", "Cust-c", "cust-a"]
    assert keys != sorted(keys, key=str.casefold)


# ---------------------------------------------------------------------------
# Route 3: GET /risk/assessments/{assessment_id}
# ---------------------------------------------------------------------------


def test_meridians_detail_has_its_six_positions_by_ordinal_and_its_brief(
        client, assessed, meridian_brief):
    (item,) = listing(client, executive_worthy="true")["items"]

    response = client.get(f"{ASSESSMENTS}/{item['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert {key: detail[key] for key in item if key != "brief_ids"} == {
        key: value for key, value in item.items() if key != "brief_ids"}
    assert [position["ordinal"] for position in detail["positions"]] == list(range(6))
    assert [(position["function"], position["proposed_action"], position["object_ref"],
             position["stance"]) for position in detail["positions"]] == MERIDIAN_POSITIONS
    assert all(position["citations"] and position["rationale"]
               for position in detail["positions"])
    assert detail["briefs"] == [{"id": meridian_brief, "policy_version": 1,
                                 "template_version": "1", "payload_hash": MERIDIAN_HASH}]
    assert detail["satisfied_rules"] and isinstance(detail["signals"], dict)


def test_an_unbriefed_assessment_lists_no_brief(client, assessed):
    (unbriefed,) = [one for one in assessed if one["brief_id"] is None][:1]

    detail = client.get(f"{ASSESSMENTS}/{unbriefed['assessment_id']}").json()

    assert detail["briefs"] == [] and detail["positions"] == []


def test_a_missing_assessment_is_404(client):
    assert_error(client.get(f"{ASSESSMENTS}/{uuid.uuid4()}"), 404, "ASSESSMENT_NOT_FOUND",
                 "risk assessment does not exist")


def test_a_malformed_assessment_id_is_422(client):
    response = client.get(f"{ASSESSMENTS}/not-a-uuid")

    assert (response.status_code, response.json()["error"]["code"]) == (422, "INVALID_REQUEST")


# ---------------------------------------------------------------------------
# Route 4: GET /risk/briefs/{brief_id}
# ---------------------------------------------------------------------------


def test_the_brief_is_read_back_exactly_as_stored(demo, client, meridian_brief):
    with demo() as session:
        stored = session.get(RiskBrief, uuid.UUID(meridian_brief))
        assert stored is not None

    body = client.get(f"{BRIEFS}/{meridian_brief}").json()

    assert canonical_json(body["payload"]) == canonical_json(stored.decision_payload)
    assert hashlib.sha256(canonical_json(body["payload"]).encode()).hexdigest() == MERIDIAN_HASH
    assert body["payload_hash"] == MERIDIAN_HASH
    assert body["narrative"].encode("utf-8") == GOLDEN.read_bytes()
    assert body["citations"] == [citation.to_payload()
                                 for citation in payload_citations(stored.decision_payload)]
    assert len(body["citations"]) == 36
    assert (body["id"], body["assessment_id"]) == (meridian_brief, str(stored.assessment_id))
    assert (body["status"], body["decision_status"]) == ("DRAFT", "PENDING")
    assert (body["policy_version"], body["template_version"]) == (1, "1")


def test_decision_status_follows_the_head_and_status_never_moves(demo, client, meridian_brief):
    def state() -> tuple[str, str]:
        body = client.get(f"{BRIEFS}/{meridian_brief}").json()
        return body["status"], body["decision_status"]

    assert state() == ("DRAFT", "PENDING")
    first = decide(client, meridian_brief, decision="REJECTED").json()
    assert state() == ("DRAFT", "REJECTED")
    decide(client, meridian_brief, decision="APPROVED", supersedes_id=first["id"])
    assert state() == ("DRAFT", "APPROVED")
    with demo() as session:
        assert session.scalars(select(RiskBrief.status)).all() == ["DRAFT"] * 3


def test_a_missing_brief_is_404(client):
    assert_error(client.get(f"{BRIEFS}/{uuid.uuid4()}"), 404, "BRIEF_NOT_FOUND",
                 "risk brief does not exist")


# ---------------------------------------------------------------------------
# Route 5: POST /risk/briefs/{brief_id}/decision
# ---------------------------------------------------------------------------


def test_a_rejection_is_recorded_at_the_injected_time_and_writes_one_row(
        demo, client, meridian_brief):
    before = counts(demo)

    response = decide(client, meridian_brief, actor=EMAIL_CANARY, note=DOCUMENT_CANARY)

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "brief_id": meridian_brief, "payload_hash": MERIDIAN_HASH,
                    "actor": EMAIL_CANARY, "decision": "REJECTED", "note": DOCUMENT_CANARY,
                    "decided_at": "2026-09-26T09:30:00Z", "supersedes_id": None}
    after = counts(demo)
    assert after.pop("brief_decisions") == before.pop("brief_decisions") + 1
    assert after == before


def test_the_clock_is_read_once_per_decision_before_it_is_recorded(demo, meridian_brief):
    reads: list[datetime] = []

    def clock() -> datetime:
        reads.append(DECIDED_AT + timedelta(minutes=len(reads)))
        return reads[-1]

    client = client_for(demo, clock)
    first = decide(client, meridian_brief).json()
    second = decide(client, meridian_brief, supersedes_id=first["id"], decision="APPROVED").json()
    refused = decide(client, meridian_brief)

    assert refused.status_code == 409
    assert [first["decided_at"], second["decided_at"]] == [
        "2026-09-26T09:30:00Z", "2026-09-26T09:31:00Z"]
    assert len(reads) == 3


def test_the_default_clock_is_the_routes_one_utc_clock():
    now = risk.get_clock()()

    assert risk.get_clock() is risk._utc_now
    assert isinstance(now, datetime) and now.tzinfo is UTC


def test_a_successor_naming_the_head_extends_the_history(client, meridian_brief):
    first = decide(client, meridian_brief).json()

    response = decide(client, meridian_brief, decision="APPROVED", supersedes_id=first["id"])

    assert response.status_code == 201
    assert (response.json()["supersedes_id"], response.json()["decision"]) == (
        first["id"], "APPROVED")


def test_a_missing_brief_is_404_and_writes_nothing(demo, client, assessed):
    before = counts(demo)

    assert_error(decide(client, str(uuid.uuid4())), 404, "BRIEF_NOT_FOUND",
                 "risk brief does not exist")
    assert counts(demo) == before


def test_another_briefs_hash_is_409_request_hash_mismatch(demo, client, meridian_brief):
    before = counts(demo)

    response = decide(client, meridian_brief, payload_hash=BRIEF_HASHES["CUST-025"],
                      actor=EMAIL_CANARY, note=DOCUMENT_CANARY)

    assert_error(response, 409, "PAYLOAD_HASH_CONFLICT",
                 "payload_hash does not match the brief's decision payload",
                 {"reason": "REQUEST_HASH_MISMATCH"})
    assert counts(demo) == before


def test_a_stored_payload_that_no_longer_re_hashes_is_409(demo, client, meridian_brief):
    with demo.begin() as session:
        session.execute(update(RiskBrief).where(RiskBrief.id == uuid.UUID(meridian_brief))
                        .values(decision_payload={"altered": True}))
    before = counts(demo)

    response = decide(client, meridian_brief)

    assert_error(response, 409, "PAYLOAD_HASH_CONFLICT",
                 "payload_hash does not match the brief's decision payload",
                 {"reason": "STORED_PAYLOAD_MISMATCH"})
    assert counts(demo) == before


def assert_history_conflict(demo, client, brief_id: str, reason: str, **changes: object) -> None:
    before = counts(demo)

    response = decide(client, brief_id, actor=EMAIL_CANARY, note=DOCUMENT_CANARY, **changes)

    assert_error(response, 409, "DECISION_CONFLICT",
                 "the decision does not extend the brief's decision history", {"reason": reason})
    assert counts(demo) == before


def test_a_later_decision_that_supersedes_nothing_is_409(demo, client, meridian_brief):
    decide(client, meridian_brief)

    assert_history_conflict(demo, client, meridian_brief, "SUPERSEDES_REQUIRED")


def test_a_first_decision_that_supersedes_something_is_409(demo, client, meridian_brief):
    assert_history_conflict(demo, client, meridian_brief, "PREDECESSOR_NOT_ON_BRIEF",
                            supersedes_id=str(uuid.UUID(int=1)))


def test_superseding_another_briefs_decision_is_409(demo, client, assessed, meridian_brief):
    (other_brief,) = [item["brief_id"] for item in assessed
                      if item["payload_hash"] == BRIEF_HASHES["CUST-025"]]
    other = decide(client, other_brief, payload_hash=BRIEF_HASHES["CUST-025"]).json()
    decide(client, meridian_brief)

    assert_history_conflict(demo, client, meridian_brief, "PREDECESSOR_NOT_ON_BRIEF",
                            supersedes_id=other["id"])


def test_superseding_a_decision_that_is_no_longer_the_head_is_409(demo, client, meridian_brief):
    """A fork: the first decision already has a successor."""
    first = decide(client, meridian_brief).json()
    decide(client, meridian_brief, supersedes_id=first["id"])

    assert_history_conflict(demo, client, meridian_brief, "PREDECESSOR_NOT_HEAD",
                            supersedes_id=first["id"])


@pytest.mark.parametrize("error", [
    *(PayloadHashConflictError(reason) for reason in HashConflict),
    *(DecisionConflictError(reason) for reason in DecisionConflict),
], ids=lambda error: error.reason.value)
def test_every_conflict_reason_reaches_the_client_as_its_fixed_code(
        client, monkeypatch, error):
    """CONCURRENT_DECISION's real race is Phase 2's; here each reason's mapping is pinned."""
    def refuse(session, **_: object):
        raise error

    monkeypatch.setattr(risk, "record_decision", refuse)
    code, message = (
        ("PAYLOAD_HASH_CONFLICT", "payload_hash does not match the brief's decision payload")
        if isinstance(error, PayloadHashConflictError) else
        ("DECISION_CONFLICT", "the decision does not extend the brief's decision history"))

    assert_error(decide(client, str(uuid.uuid4())), 409, code, message,
                 {"reason": error.reason.value})


def test_a_failure_after_the_insert_rolls_the_decision_back(
        demo, client, meridian_brief, monkeypatch):
    """The route owns the transaction: an exception after the row is written leaves no row."""
    def fail(*_: object, **__: object) -> None:
        raise RuntimeError("the event could not be written")

    monkeypatch.setattr(approval, "log_event", fail)
    before = counts(demo)

    response = decide(client, meridian_brief)

    assert_error(response, 500, "INTERNAL_ERROR", "internal server error")
    assert counts(demo) == before


@pytest.mark.parametrize("changes", [
    {"decision": "PENDING"}, {"payload_hash": MERIDIAN_HASH.upper()}, {"actor": ""},
    {"decided_at": "2026-09-26T09:30:00Z"}, {"status": "APPROVED"},
    {"note": "n" * 2001}, {"supersedes_id": "not-a-uuid"},
])
def test_an_invalid_decision_body_is_422_and_writes_nothing(demo, client, meridian_brief,
                                                            changes):
    before = counts(demo)

    response = decide(client, meridian_brief, **changes)

    assert (response.status_code, response.json()["error"]["code"]) == (422, "INVALID_REQUEST")
    assert counts(demo) == before


def test_one_decision_emits_one_event_and_the_routes_emit_nothing_of_their_own(
        client, meridian_brief, caplog):
    caplog.set_level(logging.DEBUG)

    decide(client, meridian_brief, actor=EMAIL_CANARY, note=DOCUMENT_CANARY)
    client.get(f"{BRIEFS}/{meridian_brief}/decisions")
    client.get(f"{BRIEFS}/{meridian_brief}")

    emitted = [(record.name, record.getMessage().split(" ", 1)[0],
                getattr(record, FIELDS_ATTRIBUTE, None))
               for record in caplog.records if record.name.startswith("app.")]
    assert emitted == [("app.decisions.approval", "vs01.decision_recorded",
                        {"payload_hash": MERIDIAN_HASH, "decision": "REJECTED",
                         "supersedes": False})]
    assert all(EMAIL_CANARY not in line and DOCUMENT_CANARY not in line
               for line in caplog.messages)


# ---------------------------------------------------------------------------
# Route 6: GET /risk/briefs/{brief_id}/decisions
# ---------------------------------------------------------------------------


def test_the_history_is_empty_until_decided_then_first_to_head(client, meridian_brief):
    assert client.get(f"{BRIEFS}/{meridian_brief}/decisions").json() == {"items": []}
    first = decide(client, meridian_brief).json()
    second = decide(client, meridian_brief, decision="APPROVED", supersedes_id=first["id"]).json()

    response = client.get(f"{BRIEFS}/{meridian_brief}/decisions")

    assert response.status_code == 200
    assert response.json() == {"items": [first, second]}


def test_the_history_follows_the_chain_even_when_the_clock_runs_backwards(demo, meridian_brief):
    """§0.7.7: the chain, not decided_at, is the authoritative order."""
    times = iter([DECIDED_AT, DECIDED_AT - timedelta(days=1), DECIDED_AT - timedelta(days=2)])
    client = client_for(demo, lambda: next(times))
    first = decide(client, meridian_brief).json()
    second = decide(client, meridian_brief, decision="APPROVED", supersedes_id=first["id"]).json()
    third = decide(client, meridian_brief, supersedes_id=second["id"]).json()

    history = client.get(f"{BRIEFS}/{meridian_brief}/decisions").json()["items"]

    assert [item["id"] for item in history] == [first["id"], second["id"], third["id"]]
    assert [item["decided_at"] for item in history] == sorted(
        (item["decided_at"] for item in history), reverse=True)
    assert client.get(f"{BRIEFS}/{meridian_brief}").json()["decision_status"] == "REJECTED"


def test_the_history_of_a_missing_brief_is_404(client):
    assert_error(client.get(f"{BRIEFS}/{uuid.uuid4()}/decisions"), 404, "BRIEF_NOT_FOUND",
                 "risk brief does not exist")


# ---------------------------------------------------------------------------
# Every risk route: correlation, and nothing submitted in an error body
# ---------------------------------------------------------------------------


def test_every_risk_route_answers_with_the_callers_request_id(client, meridian_brief):
    headers = {REQUEST_ID_HEADER: "m8-correlation-id"}
    responses = [
        client.post(ASSESSMENTS, json={"as_of": "2026-09-18"}, headers=headers),
        client.get(ASSESSMENTS, headers=headers),
        client.get(f"{ASSESSMENTS}/{uuid.uuid4()}", headers=headers),
        client.get(f"{BRIEFS}/{meridian_brief}", headers=headers),
        client.post(f"{BRIEFS}/{meridian_brief}/decision", headers=headers,
                    json={"actor": "a", "decision": "APPROVED", "payload_hash": "0" * 64}),
        client.get(f"{BRIEFS}/{uuid.uuid4()}/decisions", headers=headers),
    ]

    assert [response.status_code for response in responses] == [200, 200, 404, 200, 409, 404]
    for response in responses:
        assert response.headers[REQUEST_ID_HEADER] == "m8-correlation-id"
        if response.status_code >= 400:
            assert response.json()["error"]["request_id"] == "m8-correlation-id"


class CountingSessions:
    """A session factory that counts the sessions a request opens."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions, self.opened = sessions, 0

    def __call__(self) -> Session:
        self.opened += 1
        return self.sessions()


@pytest.mark.parametrize(("label", "snapshots"), [
    ("run", 0), ("list", 1), ("detail", 1), ("brief", 1), ("decide", 0), ("history", 1),
])
def test_each_request_opens_one_session_and_every_get_reads_one_snapshot(
        demo, assessed, meridian_brief, monkeypatch, label, snapshots):
    """§0.7.8: a POST owns one write transaction; a GET reads one read-only snapshot."""
    levels: list[str] = []
    real_snapshot = risk.read_snapshot

    @contextmanager
    def snapshot(sessions):
        with real_snapshot(sessions) as session:
            levels.append(session.connection().get_isolation_level())
            yield session

    monkeypatch.setattr(risk, "read_snapshot", snapshot)
    counting = CountingSessions(demo)
    client = client_for(counting)
    (meridian,) = [one["assessment_id"] for one in assessed if one["payload_hash"] == MERIDIAN_HASH]
    request = {
        "run": lambda: client.post(ASSESSMENTS, json={"as_of": "2026-09-18"}),
        "list": lambda: client.get(ASSESSMENTS),
        "detail": lambda: client.get(f"{ASSESSMENTS}/{meridian}"),
        "brief": lambda: client.get(f"{BRIEFS}/{meridian_brief}"),
        "decide": lambda: decide(client, meridian_brief),
        "history": lambda: client.get(f"{BRIEFS}/{meridian_brief}/decisions"),
    }[label]

    assert request().status_code in (200, 201)
    assert counting.opened == 1
    assert levels == ["REPEATABLE READ"] * snapshots


def test_no_error_body_carries_a_submitted_email_or_document_text(demo, client, meridian_brief):
    responses = [
        client.post(ASSESSMENTS, json={"as_of": "2026-09-18", "customer_source_id": EMAIL_CANARY}),
        client.post(ASSESSMENTS, json={"as_of": "2026-09-18", "note": DOCUMENT_CANARY}),
        decide(client, meridian_brief, actor=EMAIL_CANARY, note=DOCUMENT_CANARY,
               payload_hash=BRIEF_HASHES["CUST-036"]),
        decide(client, meridian_brief, actor=EMAIL_CANARY + "x" * 255, note=DOCUMENT_CANARY),
        decide(client, str(uuid.uuid4()), actor=EMAIL_CANARY, note=DOCUMENT_CANARY),
    ]

    assert [response.status_code for response in responses] == [422, 422, 409, 422, 404]
    for response in responses:
        assert EMAIL_CANARY not in response.text and DOCUMENT_CANARY not in response.text


# ---------------------------------------------------------------------------
# §A28's flow, replayed through TestClient (§0.7.13, OPEN-M8-20)
# ---------------------------------------------------------------------------


def test_the_demo_flow_assess_list_brief_reject_history_and_re_run(demo, client):
    """
    §A28 over HTTP: assess; list the one executive-worthy assessment; read its
    brief's conflict and dissent; reject it; read the history; re-run the
    assessment, which answers the same hash and writes nothing.
    """
    assessed = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})
    assert assessed.status_code == 201

    listed = client.get(ASSESSMENTS, params={"executive_worthy": "true"}).json()
    (item,) = listed["items"]
    (brief_id,) = item["brief_ids"]
    assert (listed["total"], item["customer_source_id"]) == (1, "CUST-007")

    brief = client.get(f"{BRIEFS}/{brief_id}").json()
    reconciliation = brief["payload"]["reconciliation"]
    (resolution,) = reconciliation["resolutions"]
    assert len(reconciliation["conflicts"]) == 1 and resolution["dissent"]
    assert (brief["payload_hash"], brief["decision_status"]) == (MERIDIAN_HASH, "PENDING")

    rejected = client.post(f"{BRIEFS}/{brief_id}/decision", json={
        "actor": "ceo@example.invalid", "decision": "REJECTED",
        "note": "not while the service tickets are open", "payload_hash": brief["payload_hash"]})
    assert rejected.status_code == 201

    history = client.get(f"{BRIEFS}/{brief_id}/decisions")
    assert history.json() == {"items": [rejected.json()]}
    before = counts(demo)

    rerun = client.post(ASSESSMENTS, json={"as_of": "2026-09-18"})

    assert rerun.status_code == 200
    assert rerun.json()["items"] == [{**one, "created": False} for one in assessed.json()["items"]]
    assert MERIDIAN_HASH in [one["payload_hash"] for one in rerun.json()["items"]]
    assert counts(demo) == before
    assert client.get(f"{BRIEFS}/{brief_id}").json()["decision_status"] == "REJECTED"
