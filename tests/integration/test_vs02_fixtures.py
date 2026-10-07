"""
The VS-02 fixture package against a real database (plan A24).

The baseline is data/demo/, ingested by the clean full-dataset path, so every
effect asserted here is measured against the committed 233 rows. Four kinds
of test, as tests/integration/test_vs01_fixtures.py has for VS-01's package:

Manifest: the ten entries of plan A24 appear exactly once, in the plan's
order, each with its origin, form, rows, effect and proof, and every proof it
names is a test function that exists. The origins are restated here from the
plan, not read from the manifest under test.

Layout and hygiene: each delta holds the seven csv_demo files in the
committed column layout, the package holds no test module, every id it adds
is reserved and unused by the committed data, and its text is clean under
the secret scan.

Guard and determinism: the package refuses a database whose name ends in
neither _test nor _vs02 before it connects, and each fixture applied to two
fresh databases gives one fingerprint.

Effects and forms: each entry touches only its declared rows. A delta's rows
are admitted by Layer 1 with nothing rejected, which is what makes it a
delta; what Layer 1 cannot express is a loader (plan A24: the form is
measured at VS02-M2 and recorded in the manifest). What each entry is *for*
is proved in tests/integration/test_vs02_dataset.py.

Stored rows (VS02-M3): the three loaders that store a customer, a deal or an
assessment as written are behind the same guard, never commit, store exactly
what they are given, and add no entry to the manifest (plan A25.2, "Stored").
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.core.database import Base
from app.ingestion.orchestrator import IngestionRequest, run_ingestion
from app.intelligence.config import default_risk_rules
from app.intelligence.scope import layer1_fingerprint
from app.normalization.config import default_config
from app.persistence.models import Customer, Deal, IngestionError, RiskAssessment
from app.persistence.repositories.canonical import ENTITY_MODELS
from app.persistence.repositories.runs import RunStatus
from app.pipeline.aggregation import RESERVED_KEYS
from tests.fixtures.vs02 import (
    ALLOWED_DATABASE_SUFFIXES,
    FIXTURES,
    LOADERS,
    OTHER_DEAL,
    OTHER_EMPLOYEE,
    OTHER_SOURCE,
    PACKAGE_DIR,
    FixtureDatabaseRefusedError,
    add_second_source_system,
    apply,
    check_database,
    ingest_delta,
    load_manifest,
    remove_doc004,
    store_assessment,
    store_customer,
    store_deal,
)

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "data" / "demo"
SECRET_SCAN = REPO / "scripts" / "secret_scan.py"

SOURCE_SYSTEM = "csv_demo"
PINNED = "1d891b0b543f961836b0a33abbe4ac563ee7229154a4caeca63594bd76357b00"

#: Plan A24's ten entries, restated from the plan in its order, with the form
#: VS02-M2 measured for each.
A24 = [
    ("unvalued_deals", "an open deal with a null amount, and one with a null probability",
     "delta"),
    ("negative_amount", "an open deal with a negative amount", "delta"),
    ("owner_keys", "an open deal whose owner_source_id is null, and one naming no employee",
     "delta"),
    ("customer_keys",
     "an open deal with a null customer_source_id, and one with an unresolved one", "delta"),
    ("undated_deal", "an open deal with a null expected_close_date", "delta"),
    ("stage_activity_mismatch",
     "a deal that is active with stage won, and one inactive with stage negotiation", "delta"),
    ("second_source_system",
     "a deal and an employee in a second source system (M2's other_demo precedent), the "
     "employee carrying the source_id that a deal of the first source system names as its "
     "owner, so that only the scoping of the join keeps that deal UNRESOLVED", "loader"),
    ("gbp_deal", "an open valued deal in GBP, a D1 currency the rate set does not hold", "delta"),
    ("no_doc004", "the corpus without DOC-004", "loader"),
    ("reserved_customer",
     "a customer whose source_id is the reserved key UNLINKED, holding one open valued deal",
     "delta"),
]
FORMS = {name: form for name, _, form in A24}
DELTAS = tuple(name for name, form in FORMS.items() if form == "delta")

#: The seven csv_demo files, named as data/demo/ names them.
CSV_FILES = tuple(sorted(path.name for path in DEMO_DIR.glob("*.csv")))
#: The id column of each csv_demo file (config/connectors/csv_demo.yaml).
ID_COLUMNS = {"organizations": "organization_id", "employees": "employee_id",
              "customers": "customer_id", "deals": "deal_id", "projects": "project_id",
              "support_tickets": "ticket_id", "documents": "document_id"}

#: The ids the package reserves.
RESERVED_DEAL = re.compile(r"DEAL-9[67][0-9]")
UNUSED = ("EMP-960", "CUST-960")
#: What Layer 1 itself says of each delta: (rows, warnings). Nothing is rejected.
MEASURED = {"unvalued_deals": (2, 0), "negative_amount": (1, 0), "owner_keys": (2, 0),
            "customer_keys": (2, 1), "undated_deal": (1, 0), "stage_activity_mismatch": (2, 0),
            "gbp_deal": (1, 0), "reserved_customer": (2, 0)}


def _load_scanner():
    spec = importlib.util.spec_from_file_location("secret_scan_vs02", SECRET_SCAN)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their defining module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ingest_demo(sessions: sessionmaker[Session]) -> None:
    summary = run_ingestion(build_connector(SOURCE_SYSTEM), sessions, IngestionRequest())
    assert _run_counts(summary) == (RunStatus.SUCCESS, 233, 233, 0)


@pytest.fixture
def demo(e1_sessions: sessionmaker[Session]) -> sessionmaker[Session]:
    """The clean full-dataset path: 233 rows, 7 entity types, 0 rejected."""
    _ingest_demo(e1_sessions)
    return e1_sessions


def _truncate(sessions: sessionmaker[Session]) -> None:
    """Empty every table, exactly as tests/conftest.py's e1_sessions does."""
    engine = sessions.kw["bind"]
    tables = ", ".join(engine.dialect.identifier_preparer.quote(table.name)
                       for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


def _fingerprint(sessions: sessionmaker[Session], source_system: str = SOURCE_SYSTEM) -> str:
    with sessions() as session:
        fingerprint, _ = layer1_fingerprint(session, source_system)
    return fingerprint


def _snapshot(sessions: sessionmaker[Session]) -> dict[tuple[str, str, str], dict]:
    """Every canonical row, whole, by (entity type, source system, source id)."""
    rows: dict[tuple[str, str, str], dict] = {}
    with sessions() as session:
        for entity_type, model in ENTITY_MODELS.items():
            for row in session.execute(select(model.__table__)).all():
                rows[(entity_type, row.source_system, row.source_id)] = dict(row._mapping)
    return rows


def _table_counts(sessions: sessionmaker[Session]) -> dict[str, int]:
    with sessions() as session:
        return {table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables}


def _added(before: dict, after: dict) -> set[tuple[str, str, str]]:
    assert set(before) <= set(after), "nothing but DOC-004's loader removes a row"
    changed = [key for key in before if after[key] != before[key]]
    assert changed == [], "every existing row is exactly as it was"
    return set(after) - set(before)


def _declared(name: str) -> set[tuple[str, str, str]]:
    return {(entity_type, SOURCE_SYSTEM, source_id)
            for entity_type, ids in FIXTURES[name].rows["added"].items() for source_id in ids}


def _run_counts(summary) -> tuple[RunStatus, int, int, int]:
    return (summary.status,
            sum(entity.counts.fetched for entity in summary.entities),
            sum(entity.counts.inserted for entity in summary.entities),
            sum(entity.counts.rejected for entity in summary.entities))


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_the_manifest_names_every_a24_entry_exactly_once_in_the_plans_order():
    entries = load_manifest()["fixtures"]

    assert [entry["name"] for entry in entries] == [name for name, _, _ in A24]
    assert [entry["entry"] for entry in entries] == list(range(1, 11))
    assert [" ".join(entry["origin"].split()) for entry in entries] == [
        origin for _, origin, _ in A24]
    assert list(FIXTURES) == [name for name, _, _ in A24]


def test_each_entry_carries_its_form_rows_fingerprint_effect_and_proof():
    for name, fixture in FIXTURES.items():
        assert fixture.form == FORMS[name], name
        assert fixture.fingerprint in {"changed", "unchanged"}, name
        assert fixture.effect.strip(), name
        assert fixture.proofs, name
        assert bool(fixture.entities) is (fixture.form == "delta"), name
        assert set(fixture.rows) <= {"added", "removed"} and fixture.rows, name
    assert set(LOADERS) == {name for name, form in FORMS.items() if form == "loader"}
    assert LOADERS == {"second_source_system": add_second_source_system,
                       "no_doc004": remove_doc004}


def test_the_baseline_is_the_committed_demo_dataset_at_its_pinned_fingerprint(demo):
    baseline = load_manifest()["baseline"]
    with demo() as session:
        fingerprint, counts = layer1_fingerprint(session, SOURCE_SYSTEM)

    assert (baseline["form"], baseline["directory"]) == ("baseline", "data/demo")
    assert dict(counts) == baseline["entity_counts"]
    assert sum(counts.values()) == baseline["rows"] == 233
    assert fingerprint == baseline["fingerprint"] == PINNED
    assert default_risk_rules().pinned_fingerprint(SOURCE_SYSTEM) == PINNED


def _proof_node_ids() -> list[str]:
    return sorted({proof for fixture in FIXTURES.values() for proof in fixture.proofs})


def _top_level_functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


@pytest.mark.parametrize("node_id", _proof_node_ids())
def test_each_named_proof_is_an_existing_test_function(node_id):
    path, function = node_id.split("::")

    assert path == "tests/integration/test_vs02_dataset.py"
    assert function.startswith("test_")
    assert function in _top_level_functions(REPO / path), node_id


def test_the_second_source_system_names_the_entry_it_is_built_on():
    """Entry 7's employee carries the id a deal of entry 3 names, so it requires entry 3."""
    [entry] = [entry for entry in load_manifest()["fixtures"]
               if entry["name"] == "second_source_system"]
    with (FIXTURES["owner_keys"].directory / "deals.csv").open(encoding="utf-8",
                                                               newline="") as handle:
        owners = {row["deal_id"]: row["owner_id"] for row in csv.DictReader(handle)}

    assert entry["requires"] == ["owner_keys"]
    assert owners == {"DEAL-963": "", "DEAL-964": OTHER_EMPLOYEE}
    assert entry["rows"] == {"added": {OTHER_SOURCE: {"employees": [OTHER_EMPLOYEE],
                                                      "deals": [OTHER_DEAL]}}}


# ---------------------------------------------------------------------------
# Layout and hygiene
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", DELTAS)
def test_each_delta_holds_the_seven_csv_demo_files_in_the_committed_layout(name):
    directory = FIXTURES[name].directory
    added = FIXTURES[name].rows["added"]

    assert tuple(sorted(path.name for path in directory.iterdir())) == CSV_FILES
    assert set(added) == set(FIXTURES[name].entities)
    for file_name in CSV_FILES:
        entity_type = file_name.removesuffix(".csv")
        committed = (DEMO_DIR / file_name).read_text(encoding="utf-8").splitlines()[0]
        with (directory / file_name).open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header, rows = next(reader), list(reader)
        assert ",".join(header) == committed, file_name
        assert [row[header.index(ID_COLUMNS[entity_type])] for row in rows] == added.get(
            entity_type, []), file_name


def test_the_package_holds_its_manifest_its_module_and_eight_deltas_and_no_test_module():
    files = sorted(path.relative_to(PACKAGE_DIR).as_posix() for path in PACKAGE_DIR.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts)

    assert list(PACKAGE_DIR.rglob("test_*.py")) == []
    assert files == sorted(["__init__.py", "manifest.yaml",
                            *(f"{name}/{file_name}" for name in DELTAS
                              for file_name in CSV_FILES)])
    assert len(files) == 2 + 7 * 8


def test_every_added_id_is_reserved_and_unused_by_the_committed_data():
    added = sorted(source_id for name in DELTAS
                   for ids in FIXTURES[name].rows["added"].values() for source_id in ids)
    committed = "\n".join(path.read_text(encoding="utf-8")
                          for path in sorted((REPO / "data").rglob("*.csv")))

    assert added == [*(f"DEAL-{number}" for number in range(960, 972)), "UNLINKED"]
    assert all(RESERVED_DEAL.fullmatch(source_id) for source_id in added[:-1])
    assert not RESERVED_DEAL.search(committed)
    assert not [unused for unused in (*UNUSED, "UNLINKED") if unused in committed]
    assert "UNLINKED" in RESERVED_KEYS


def test_the_fixture_text_is_clean_under_the_secret_scan():
    scanner = _load_scanner()
    files = sorted(path for path in PACKAGE_DIR.rglob("*")
                   if path.is_file() and "__pycache__" not in path.parts)

    assert len(files) == 2 + 7 * len(DELTAS)
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert scanner.scan_text(path.relative_to(REPO).as_posix(), content) == [], path
        if path.suffix in {".csv", ".yaml"}:
            assert "://" not in content, path


def test_a_fixture_uses_only_what_layer_1_already_has():
    """No fixture widens a vocabulary: every stage and currency it writes is a D1 value."""
    config = default_config()
    stages, currencies = set(), set()
    for name in DELTAS:
        with (FIXTURES[name].directory / "deals.csv").open(encoding="utf-8",
                                                           newline="") as handle:
            for row in csv.DictReader(handle):
                stages.add(row["stage"])
                currencies.add(row["currency"])

    assert stages == config.fields["deals"]["stage"].enum_values
    assert currencies == {"INR", "USD", "EUR", "GBP"} and currencies <= config.currency_codes


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["ai_ceo_layer1", "postgres", "ai_ceo_layer1_test_copy",
                                  "ai_ceo_layer1_vs02_old", "ai_ceo_layer1_vs01", "", None])
def test_the_guard_refuses_a_database_that_is_neither_a_test_nor_an_acceptance_one(name):
    with pytest.raises(FixtureDatabaseRefusedError, match="refusing to apply a VS-02 fixture"):
        check_database(name)


@pytest.mark.parametrize("name", ["ai_ceo_layer1_test", "ai_ceo_layer1_vs02"])
def test_the_guard_admits_the_test_and_acceptance_databases(name):
    check_database(name)
    assert ALLOWED_DATABASE_SUFFIXES == ("_test", "_vs02")


@pytest.fixture
def development_engine():
    """An engine naming the development database. Nothing may connect through it."""
    engine = create_engine("postgresql:///ai_ceo_layer1")
    yield engine
    engine.dispose()


@pytest.mark.parametrize("name", list(FORMS))
def test_apply_refuses_the_development_database_before_connecting(development_engine, name):
    with pytest.raises(FixtureDatabaseRefusedError):
        apply(name, sessionmaker(bind=development_engine))


@pytest.mark.parametrize("name", DELTAS)
def test_a_delta_refuses_the_development_database_before_connecting(development_engine, name):
    with pytest.raises(FixtureDatabaseRefusedError):
        ingest_delta(name, sessionmaker(bind=development_engine))


@pytest.mark.parametrize("loader", [remove_doc004, add_second_source_system])
def test_each_loader_refuses_the_development_database_before_executing(development_engine,
                                                                       loader):
    with Session(bind=development_engine) as session, pytest.raises(FixtureDatabaseRefusedError):
        loader(session)


@pytest.mark.parametrize("name", ["second_source_system", "no_doc004"])
def test_a_loader_entry_is_not_a_delta(demo, name):
    before = _table_counts(demo)

    with pytest.raises(ValueError, match="is a loader entry, not a delta"):
        ingest_delta(name, demo)

    assert _table_counts(demo) == before


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(FORMS))
def test_each_fixture_applied_to_two_fresh_databases_gives_one_fingerprint(e1_sessions, name):
    fingerprints = []
    for _ in range(2):
        _truncate(e1_sessions)
        _ingest_demo(e1_sessions)
        apply(name, e1_sessions)
        fingerprints.append((_fingerprint(e1_sessions), _fingerprint(e1_sessions, OTHER_SOURCE)))

    assert fingerprints[0] == fingerprints[1]
    assert (fingerprints[0][0] != PINNED) is (FIXTURES[name].fingerprint == "changed")


# ---------------------------------------------------------------------------
# The deltas: what Layer 1 admits, which is what makes each a delta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", DELTAS)
def test_each_delta_is_admitted_by_layer_1_and_adds_exactly_its_declared_rows(demo, name):
    """
    Plan A24: a row D1 and D2 accept is a delta. Every row is fetched and
    inserted, none is rejected, and no existing row is changed.
    """
    rows, warnings = MEASURED[name]
    before, counts = _snapshot(demo), _table_counts(demo)

    summary = apply(name, demo)

    assert _run_counts(summary) == (RunStatus.SUCCESS, rows, rows, 0)
    assert summary.counts.warnings == warnings
    assert _added(before, _snapshot(demo)) == _declared(name)
    after = _table_counts(demo)
    for entity_type, ids in FIXTURES[name].rows["added"].items():
        assert after[entity_type] - counts[entity_type] == len(ids)
    with demo() as session:
        assert [(error.severity, error.error_code, error.source_id)
                for error in session.scalars(select(IngestionError)).all()] == (
            [("WARNING", "UNRESOLVED_REFERENCE", "DEAL-966")] if warnings else [])


def test_set_of_measured_deltas_is_the_set_of_deltas():
    assert sorted(MEASURED) == sorted(DELTAS) and len(DELTAS) == 8


def _deals(sessions: sessionmaker[Session], *source_ids: str) -> list[tuple]:
    with sessions() as session:
        return [tuple(row) for row in session.execute(
            select(Deal.source_id, Deal.stage, Deal.is_active, Deal.amount, Deal.currency,
                   Deal.probability, Deal.expected_close_date, Deal.owner_source_id,
                   Deal.customer_source_id, Deal.customer_id.is_not(None))
            .where(Deal.source_system == SOURCE_SYSTEM, Deal.source_id.in_(source_ids))
            .order_by(Deal.source_id)).all()]


def test_the_deltas_store_what_their_entries_say(demo):
    """The stored values of each added deal, as Layer 1 left them: nulls kept as nulls."""
    for name in DELTAS:
        apply(name, demo)

    stored = {row[0]: row[1:] for row in _deals(
        demo, *(f"DEAL-{number}" for number in range(960, 972)))}

    def text_of(values: tuple) -> tuple:
        return tuple(str(value) if value is not None and not isinstance(value, bool | str)
                     else value for value in values)

    assert {source_id: text_of(values) for source_id, values in stored.items()} == {
        "DEAL-960": ("qualification", True, None, "INR", "40.00", "2026-12-01", "EMP-008",
                     "CUST-003", True),
        "DEAL-961": ("qualification", True, "1250.00", "INR", None, "2026-12-01", "EMP-008",
                     "CUST-003", True),
        "DEAL-962": ("negotiation", True, "-1500.00", "USD", "60.00", "2026-11-15", "EMP-009",
                     "CUST-005", True),
        "DEAL-963": ("qualification", True, "2000.00", "INR", "25.00", "2027-01-10", None,
                     "CUST-010", True),
        "DEAL-964": ("qualification", True, "3000.00", "INR", "50.00", "2027-02-10", "EMP-960",
                     "CUST-010", True),
        "DEAL-965": ("negotiation", True, "4000.00", "INR", "10.00", "2026-10-20", "EMP-007",
                     None, False),
        "DEAL-966": ("negotiation", True, "5000.00", "EUR", "20.00", "2026-10-21", "EMP-007",
                     "CUST-960", False),
        "DEAL-967": ("qualification", True, "6000.00", "USD", "75.00", None, "EMP-010",
                     "CUST-012", True),
        "DEAL-968": ("won", True, "7000.00", "INR", "100.00", "2026-10-30", "EMP-008",
                     "CUST-014", True),
        "DEAL-969": ("negotiation", False, "8000.00", "INR", "60.00", "2026-10-31", "EMP-008",
                     "CUST-014", True),
        "DEAL-970": ("negotiation", True, "9000.00", "GBP", "30.00", "2026-11-30", "EMP-009",
                     "CUST-016", True),
        "DEAL-971": ("qualification", True, "10000.00", "INR", "50.00", "2026-12-15", "EMP-010",
                     "UNLINKED", True),
    }
    with demo() as session:
        assert session.scalar(select(func.count()).select_from(Customer).where(
            Customer.source_system == SOURCE_SYSTEM, Customer.source_id == "UNLINKED")) == 1


# ---------------------------------------------------------------------------
# The loaders: what Layer 1 cannot express
# ---------------------------------------------------------------------------


def test_no_doc004_removes_doc_004_and_touches_no_other_row(demo):
    before, counts = _snapshot(demo), _table_counts(demo)

    assert apply("no_doc004", demo) is None

    after = _snapshot(demo)
    assert set(before) - set(after) == {("documents", SOURCE_SYSTEM, "DOC-004")}
    assert all(after[key] == before[key] for key in after) and set(after) < set(before)
    assert _table_counts(demo) == {**counts, "documents": 11}
    assert FIXTURES["no_doc004"].rows == {"removed": {"documents": ["DOC-004"]}}


def test_the_second_source_system_adds_two_rows_of_its_own_and_changes_none_of_csv_demos(demo):
    """
    other_demo is not a D1 source system, so Layer 1 cannot ingest it and
    the entry is a loader. The csv_demo snapshot keeps its pinned fingerprint.
    """
    before, counts = _snapshot(demo), _table_counts(demo)

    assert apply("second_source_system", demo) is None

    assert OTHER_SOURCE not in default_config().source_systems
    assert _added(before, _snapshot(demo)) == {
        ("employees", OTHER_SOURCE, OTHER_EMPLOYEE), ("deals", OTHER_SOURCE, OTHER_DEAL)}
    assert _table_counts(demo) == {**counts, "employees": 25, "deals": 45}
    assert _fingerprint(demo) == PINNED
    assert ("deals", SOURCE_SYSTEM, OTHER_DEAL) in before, "the id is one csv_demo already holds"


def test_a_loader_does_not_commit(demo):
    """Plan A24: Core over the caller's session, never committing. A rollback undoes it."""
    counts = _table_counts(demo)

    for loader in (remove_doc004, add_second_source_system):
        with demo() as session:
            loader(session)
            session.rollback()

    assert _table_counts(demo) == counts
    assert _fingerprint(demo) == PINNED


# ---------------------------------------------------------------------------
# Stored rows (VS02-M3): loaders that are not entries (plan A25.2, "Stored")
# ---------------------------------------------------------------------------

STORED_SYSTEM = "stored_demo"
#: One call of each stored-row loader, with nothing left to a default that matters.
STORED_CALLS = {
    "store_customer": lambda session: store_customer(
        session, source_system=STORED_SYSTEM, source_id="CUST-980"),
    "store_deal": lambda session: store_deal(
        session, source_system=STORED_SYSTEM, source_id="DEAL-980", stage="prospect",
        amount=Decimal("12.50"), currency="XXX", probability=Decimal("40.00")),
    "store_assessment": lambda session: store_assessment(
        session, source_system=STORED_SYSTEM, as_of=date(2026, 9, 18),
        layer1_fingerprint="f" * 64, rules_version=1, linker_version="1", customer=None,
        band="SEVERE"),
}


def test_the_stored_row_loaders_add_no_entry_to_the_manifest():
    """Plan A24 names ten entries, and the package still holds ten and two entry loaders."""
    assert len(load_manifest()["fixtures"]) == len(A24) == 10
    assert sorted(LOADERS) == ["no_doc004", "second_source_system"]
    assert not {store_customer, store_deal, store_assessment} & set(LOADERS.values())
    assert sorted(STORED_CALLS) == ["store_assessment", "store_customer", "store_deal"]


@pytest.mark.parametrize("name", sorted(STORED_CALLS))
def test_each_stored_row_loader_refuses_the_development_database_before_executing(
        development_engine, name):
    with Session(bind=development_engine) as session, pytest.raises(FixtureDatabaseRefusedError):
        STORED_CALLS[name](session)


def test_a_stored_row_loader_does_not_commit(demo):
    """Core over the caller's session, never committing. A rollback undoes all three."""
    counts = _table_counts(demo)

    with demo() as session:
        for name in sorted(STORED_CALLS):
            STORED_CALLS[name](session)
        held = {table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables}
        session.rollback()

    assert held == {**counts, "customers": counts["customers"] + 1,
                    "deals": counts["deals"] + 1, "risk_assessments": 1}
    assert _table_counts(demo) == counts
    assert _fingerprint(demo) == PINNED


def test_the_stored_row_loaders_store_exactly_what_they_are_given(demo):
    """
    What Layer 1 and VS-01's writer would have refused is stored as written:
    a stage and a currency outside the D1 vocabularies, and a band outside
    RiskBand. A deal's canonical customer key is set from the customer named,
    and an assessment with no customer is stored with a NULL key.
    """
    config = default_config()
    assert "prospect" not in config.fields["deals"]["stage"].enum_values
    assert "XXX" not in config.currency_codes

    with demo() as session:
        store_customer(session, source_system=STORED_SYSTEM, source_id="CUST-980")
        store_deal(session, source_system=STORED_SYSTEM, source_id="DEAL-980", stage="prospect",
                   is_active=False, amount=Decimal("12.50"), currency="XXX",
                   probability=Decimal("40.00"), expected_close_date=date(2026, 12, 1),
                   owner_source_id="EMP-980", customer="CUST-980")
        store_deal(session, source_system=STORED_SYSTEM, source_id="DEAL-981", stage=None)
        for customer, band, worthy in (("CUST-980", "SEVERE", True), (None, "WATCH", False)):
            store_assessment(session, source_system=STORED_SYSTEM, as_of=date(2026, 9, 18),
                             layer1_fingerprint="f" * 64, rules_version=7, linker_version="9",
                             customer=customer, band=band, executive_worthy=worthy)
        store_assessment(session, source_system="elsewhere", as_of=date(2026, 9, 18),
                         layer1_fingerprint="f" * 64, rules_version=7, linker_version="9",
                         customer="CUST-980", band="NONE", customer_system=STORED_SYSTEM)

        [customer_id] = session.scalars(select(Customer.id).where(
            Customer.source_system == STORED_SYSTEM)).all()
        deals = [tuple(row) for row in session.execute(
            select(Deal.source_id, Deal.source_entity, Deal.stage, Deal.is_active, Deal.amount,
                   Deal.currency, Deal.probability, Deal.expected_close_date,
                   Deal.owner_source_id, Deal.customer_source_id, Deal.customer_id)
            .where(Deal.source_system == STORED_SYSTEM).order_by(Deal.source_id)).all()]
        assessments = sorted(tuple(row) for row in session.execute(
            select(RiskAssessment.source_system, RiskAssessment.customer_id.is_(None),
                   RiskAssessment.band, RiskAssessment.executive_worthy,
                   RiskAssessment.rules_version, RiskAssessment.linker_version,
                   RiskAssessment.as_of, RiskAssessment.layer1_fingerprint)).all())
        session.rollback()

    assert deals == [
        ("DEAL-980", "deals", "prospect", False, Decimal("12.50"), "XXX", Decimal("40.00"),
         date(2026, 12, 1), "EMP-980", "CUST-980", customer_id),
        ("DEAL-981", "deals", None, True, None, None, None, None, None, None, None)]
    assert assessments == [
        ("elsewhere", False, "NONE", False, 7, "9", date(2026, 9, 18), "f" * 64),
        (STORED_SYSTEM, False, "SEVERE", True, 7, "9", date(2026, 9, 18), "f" * 64),
        (STORED_SYSTEM, True, "WATCH", False, 7, "9", date(2026, 9, 18), "f" * 64)]


def test_a_stored_assessment_has_one_id_however_often_it_is_built(demo):
    """Fixed values, so two builds are identical: the id is derived from the identity."""
    ids = []
    for _ in range(2):
        with demo() as session:
            STORED_CALLS["store_assessment"](session)
            ids.append(session.scalars(select(RiskAssessment.id)).one())
            session.rollback()

    assert ids[0] == ids[1]
