"""
M7's two repositories against a real database (§0.6.5, §0.6.6).

risk_assessments.py writes append-or-read: an identity the database already
holds becomes a read of the existing id, never an update and never an error.
That is asserted table by table, with the one property the plan singles out
for briefs -- a colliding brief's narrative and template_version are never
rewritten -- asserted on the stored row itself.

citation_reads.py returns plain values for the three reads the run needs,
constrained to one source system, and writes nothing.

The demo dataset is ingested by the clean full-dataset path, so every row a
read returns is a real Layer 1 row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, sessionmaker

from app.connectors import CsvConnector, CsvConnectorConfig, SourceConnector
from app.core.database import Base
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.persistence.models import (
    Customer,
    RiskAssessment,
    RiskBrief,
    RiskPosition,
    SupportTicket,
)
from app.persistence.repositories.citation_reads import (
    document_texts,
    field_nullness,
    ticket_created_at,
)
from app.persistence.repositories.risk_assessments import (
    AssessmentRow,
    BriefRow,
    PositionRow,
    insert_assessment,
    insert_brief,
    insert_positions,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SOURCE_SYSTEM = "csv_demo"
FINGERPRINT = "a" * 64
OTHER_FINGERPRINT = "b" * 64


def _csv_connector() -> SourceConnector:
    config = CsvConnectorConfig.from_yaml(REPO / "config" / "connectors" / "csv_demo.yaml")
    config.data_directory = str(DEMO_DIR)
    return CsvConnector(config)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 7 entity types, 0 rejected."""
    counts = run_ingestion(_csv_connector(), e1_sessions, IngestionRequest()).counts
    assert counts.rejected == 0
    return e1_sessions


def assessment(**changes) -> AssessmentRow:
    row = AssessmentRow(
        customer_source_id="CUST-007",
        as_of=date(2026, 9, 18),
        source_system=SOURCE_SYSTEM,
        layer1_fingerprint=FINGERPRINT,
        rules_version=1,
        linker_version="1",
        band="CRITICAL",
        executive_worthy=True,
        signals={"open_ticket_count": 4, "contract_document_ids": ["DOC-006"]},
        satisfied_rules=["R1", "R2"],
        ranking_key=[-3, -3, -5, "CUST-007"],
    )
    return row._replace(**changes)


def position(ordinal: int, action: str = "NO_ACTION", **changes) -> PositionRow:
    row = PositionRow(
        ordinal=ordinal,
        function="SUPPORT",
        stance="NEUTRAL",
        proposed_action=action,
        object_ref="CUST-007",
        rationale=f"rationale {ordinal}",
        citations=[{"kind": "CANONICAL_FACT", "citation": {"kind": "record"}}],
    )
    return row._replace(**changes)


def brief(assessment_id, **changes) -> BriefRow:
    row = BriefRow(
        assessment_id=assessment_id,
        policy_version=1,
        template_version="1",
        decision_payload={"payload_version": 1, "band": "CRITICAL"},
        payload_hash="c" * 64,
        narrative="the narrative",
    )
    return row._replace(**changes)


def count(sessions, model) -> int:
    with sessions() as session:
        return session.scalar(select(func.count()).select_from(model))


def all_counts(sessions) -> dict[str, int]:
    with sessions() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


# ---------------------------------------------------------------------------
# insert_assessment
# ---------------------------------------------------------------------------


def test_an_assessment_is_created_once_and_read_back_after(demo):
    with demo.begin() as session:
        first, created = insert_assessment(session, assessment())
    with demo.begin() as session:
        second, again = insert_assessment(session, assessment())

    assert created is True
    assert again is False
    assert second == first
    assert count(demo, RiskAssessment) == 1


def test_a_colliding_assessment_is_trusted_and_never_updated(demo):
    """§0.6.6: a key collision is read back, never compared, updated or rejected."""
    with demo.begin() as session:
        first, _ = insert_assessment(session, assessment())
    with demo.begin() as session:
        second, created = insert_assessment(
            session, assessment(band="NONE", executive_worthy=False, signals={"changed": 1})
        )

    assert (second, created) == (first, False)
    with demo() as session:
        row = session.get(RiskAssessment, first)
        assert (row.band, row.executive_worthy) == ("CRITICAL", True)
        assert row.signals == {"open_ticket_count": 4, "contract_document_ids": ["DOC-006"]}


@pytest.mark.parametrize("change", [
    {"as_of": date(2026, 9, 19)},
    {"layer1_fingerprint": OTHER_FINGERPRINT},
    {"rules_version": 2},
    {"linker_version": "2"},
    {"customer_source_id": "CUST-025"},
])
def test_each_identity_column_mints_a_new_assessment(demo, change):
    with demo.begin() as session:
        first, _ = insert_assessment(session, assessment())
    with demo.begin() as session:
        second, created = insert_assessment(session, assessment(**change))

    assert created is True
    assert second != first
    assert count(demo, RiskAssessment) == 2


def test_the_source_system_is_part_of_the_identity(demo):
    """The customer is resolved within the row's source system, and the key holds it."""
    with demo.begin() as session:
        session.add(Customer(
            source_system="other_demo", source_entity="customers", source_id="CUST-007",
            record_hash="d" * 64, ingestion_run_id=uuid.uuid4(), name="Another Meridian",
        ))
    with demo.begin() as session:
        first, _ = insert_assessment(session, assessment())
        second, created = insert_assessment(session, assessment(source_system="other_demo"))

    assert created is True
    assert second != first
    with demo() as session:
        owners = session.execute(
            select(RiskAssessment.source_system, Customer.source_system)
            .join(Customer, RiskAssessment.customer_id == Customer.id)
            .order_by(RiskAssessment.source_system)
        ).all()
    assert [tuple(owner) for owner in owners] == [
        ("csv_demo", "csv_demo"), ("other_demo", "other_demo")]


def test_every_column_is_stored_verbatim(demo):
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())

    with demo() as session:
        row = session.get(RiskAssessment, identifier)
        customer = session.scalar(select(Customer.source_id).where(Customer.id == row.customer_id))
        assert customer == "CUST-007"
        assert (row.as_of, row.source_system, row.layer1_fingerprint, row.rules_version,
                row.linker_version, row.band, row.executive_worthy) == (
            date(2026, 9, 18), SOURCE_SYSTEM, FINGERPRINT, 1, "1", "CRITICAL", True)
        assert row.satisfied_rules == ["R1", "R2"]
        assert row.ranking_key == [-3, -3, -5, "CUST-007"]


def test_an_unknown_customer_propagates_the_database_error(demo):
    """Repository errors propagate unchanged (§0.6.11)."""
    with demo() as session, pytest.raises(NoResultFound):
        insert_assessment(session, assessment(customer_source_id="CUST-999"))


def test_the_repository_owns_no_transaction(demo):
    """The caller's rollback removes everything the repository wrote."""
    with demo() as session:
        identifier, _ = insert_assessment(session, assessment())
        insert_positions(session, identifier, [position(0)])
        insert_brief(session, brief(identifier))
        session.rollback()

    assert count(demo, RiskAssessment) == 0
    assert count(demo, RiskPosition) == 0
    assert count(demo, RiskBrief) == 0


# ---------------------------------------------------------------------------
# insert_positions
# ---------------------------------------------------------------------------


def test_positions_are_written_in_ordinal_order_and_counted(demo):
    rows = [position(2, "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA"), position(0, "NO_ACTION"),
            position(1, "ASSIGN_DEDICATED_SUPPORT_OWNER")]
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        inserted = insert_positions(session, identifier, rows)

    assert inserted == 3
    with demo() as session:
        stored = session.execute(
            select(RiskPosition.ordinal, RiskPosition.proposed_action, RiskPosition.rationale,
                   RiskPosition.citations)
            .where(RiskPosition.assessment_id == identifier)
            .order_by(RiskPosition.ordinal)
        ).all()
    assert [tuple(row[:3]) for row in stored] == [
        (0, "NO_ACTION", "rationale 0"),
        (1, "ASSIGN_DEDICATED_SUPPORT_OWNER", "rationale 1"),
        (2, "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", "rationale 2"),
    ]
    assert stored[0][3] == [{"kind": "CANONICAL_FACT", "citation": {"kind": "record"}}]


def test_a_repeated_position_is_skipped_by_the_database(demo):
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        assert insert_positions(session, identifier, [position(0)]) == 1
    with demo.begin() as session:
        again = insert_positions(session, identifier, [position(0), position(1, "SALES_ONLY")])

    assert again == 1
    assert count(demo, RiskPosition) == 2


def test_the_identity_bounds_identical_positions_only(demo):
    """Several positions per function per assessment are normal (§0.6.5)."""
    rows = [position(0, "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA"),
            position(1, "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", object_ref="DEAL-001"),
            position(2, "ESCALATE_TO_ACCOUNT_OWNER_PER_SLA", function="SALES")]
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())

        assert insert_positions(session, identifier, rows) == 3


def test_no_positions_insert_nothing(demo):
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        assert insert_positions(session, identifier, []) == 0

    assert count(demo, RiskPosition) == 0


# ---------------------------------------------------------------------------
# insert_brief
# ---------------------------------------------------------------------------


def test_a_brief_is_created_as_a_draft_and_read_back_after(demo):
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        first, created = insert_brief(session, brief(identifier))
    with demo.begin() as session:
        second, again = insert_brief(session, brief(identifier))

    assert (created, again) == (True, False)
    assert second == first
    with demo() as session:
        row = session.get(RiskBrief, first)
        assert row.status == "DRAFT"
        assert row.decision_payload == {"payload_version": 1, "band": "CRITICAL"}
        assert (row.policy_version, row.template_version, row.payload_hash, row.narrative) == (
            1, "1", "c" * 64, "the narrative")


def test_a_colliding_brief_keeps_its_first_narrative_and_template_version(demo):
    """§0.6.6's template-only row: the hash is unchanged, so nothing is updated."""
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        first, _ = insert_brief(session, brief(identifier))
    with demo.begin() as session:
        second, created = insert_brief(
            session, brief(identifier, narrative="a new template", template_version="2"))

    assert (second, created) == (first, False)
    with demo() as session:
        row = session.get(RiskBrief, first)
        assert (row.narrative, row.template_version) == ("the narrative", "1")
    assert count(demo, RiskBrief) == 1


def test_a_different_payload_is_a_second_brief_under_the_same_assessment(demo):
    """Several briefs per assessment are normal, one per distinct payload."""
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        first, _ = insert_brief(session, brief(identifier))
        second, created = insert_brief(
            session, brief(identifier, payload_hash="e" * 64, policy_version=2))

    assert created is True
    assert second != first
    with demo() as session:
        statuses = session.scalars(select(RiskBrief.status)).all()
    assert statuses == ["DRAFT", "DRAFT"]


def test_the_database_default_makes_a_draft_without_the_orm(demo):
    """The server default holds for a row written with no status and no ORM default."""
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        session.execute(
            text(
                "INSERT INTO risk_briefs (id, assessment_id, policy_version, template_version,"
                " decision_payload, payload_hash, narrative) VALUES (:id, :assessment, 1, '1',"
                " '{}'::jsonb, :digest, 'n')"
            ),
            {"id": uuid.uuid4(), "assessment": identifier, "digest": "f" * 64},
        )
    with demo() as session:
        assert session.scalar(select(RiskBrief.status)) == "DRAFT"


def test_deleting_an_assessment_cascades_to_its_positions_and_briefs(demo):
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment())
        insert_positions(session, identifier, [position(0), position(1, "SALES_ONLY")])
        insert_brief(session, brief(identifier))
    with demo.begin() as session:
        session.execute(delete(RiskAssessment).where(RiskAssessment.id == identifier))

    assert count(demo, RiskPosition) == 0
    assert count(demo, RiskBrief) == 0


def test_deleting_a_customer_leaves_its_assessment_with_no_customer(demo):
    """§0.6.5's recorded consequence of SET NULL; unreachable on the pipeline."""
    with demo.begin() as session:
        identifier, _ = insert_assessment(session, assessment(customer_source_id="CUST-050"))
    with demo.begin() as session:
        session.execute(delete(Customer).where(Customer.source_id == "CUST-050"))

    with demo() as session:
        row = session.get(RiskAssessment, identifier)
        assert row is not None
        assert row.customer_id is None


# ---------------------------------------------------------------------------
# citation_reads
# ---------------------------------------------------------------------------


def test_document_texts_returns_title_and_body_in_the_source_system(demo):
    with demo() as session:
        texts = document_texts(session, SOURCE_SYSTEM, ["DOC-009", "DOC-003", "DOC-999"])

    assert sorted(texts) == ["DOC-003", "DOC-009"]
    title, body = texts["DOC-009"]
    assert isinstance(title, str) and title
    assert isinstance(body, str) and "DEAL-001" in body


def test_document_texts_is_constrained_to_one_source_system(demo):
    with demo() as session:
        assert document_texts(session, "other_demo", ["DOC-009"]) == {}
        assert document_texts(session, SOURCE_SYSTEM, []) == {}


def test_field_nullness_distinguishes_absent_null_and_present(demo):
    with demo() as session:
        assert field_nullness(session, SOURCE_SYSTEM, "support_tickets", "TKT-075",
                              "resolved_at") is True
        assert field_nullness(session, SOURCE_SYSTEM, "support_tickets", "TKT-073",
                              "resolved_at") is False
        assert field_nullness(session, SOURCE_SYSTEM, "deals", "DEAL-001", "amount") is False
        assert field_nullness(session, SOURCE_SYSTEM, "documents", "DOC-003",
                              "body_text") is False
        assert field_nullness(session, SOURCE_SYSTEM, "deals", "DEAL-999", "amount") is None
        assert field_nullness(session, "other_demo", "deals", "DEAL-001", "amount") is None


def test_field_nullness_reads_the_entitys_own_rows_only(demo):
    """A ticket id asked of the deals table is not a deal."""
    with demo() as session:
        assert field_nullness(session, SOURCE_SYSTEM, "deals", "TKT-075", "stage") is None


def test_ticket_created_at_returns_timestamps_and_tells_null_from_absent(demo):
    with demo.begin() as session:
        session.execute(
            update(SupportTicket)
            .where(SupportTicket.source_id == "TKT-076")
            .values(created_at=None)
        )
    with demo() as session:
        created = ticket_created_at(session, SOURCE_SYSTEM, ["TKT-075", "TKT-076", "TKT-999"])

    assert sorted(created) == ["TKT-075", "TKT-076"]
    assert created["TKT-076"] is None
    moment = created["TKT-075"]
    assert isinstance(moment, datetime)
    assert moment.utcoffset() is not None
    assert moment.astimezone(UTC).date() == date(2026, 8, 20)


def test_ticket_created_at_is_constrained_to_one_source_system(demo):
    with demo() as session:
        assert ticket_created_at(session, "other_demo", ["TKT-075"]) == {}
        assert ticket_created_at(session, SOURCE_SYSTEM, []) == {}


def test_the_reads_write_nothing(demo):
    before = all_counts(demo)
    with demo() as session:
        document_texts(session, SOURCE_SYSTEM, ["DOC-003"])
        field_nullness(session, SOURCE_SYSTEM, "customers", "CUST-007", "email")
        ticket_created_at(session, SOURCE_SYSTEM, ["TKT-073"])
        session.commit()

    assert all_counts(demo) == before
