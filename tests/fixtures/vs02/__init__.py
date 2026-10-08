"""
The VS-02 fixture package (plan A24), in the form of tests/fixtures/vs01/.

The baseline is data/demo/, reused unchanged and built through the clean
full-dataset path. Every entry of manifest.yaml adds to it or takes from it
something the committed dataset does not hold: an unvalued, unowned,
unlinked or undated deal, a deal whose stage and activity disagree, a second
source system, a currency with no rate, the corpus without DOC-004, and a
customer whose id is a reserved bucket key. Nothing here ever modifies data/.

Two forms carry material, and which one an entry takes was measured at
VS02-M2 by whether Layer 1 admits its rows:

    delta   a directory of the seven csv_demo files in the committed column
            layout. A file the fixture does not add to holds its header row
            only. The delta is ingested with run_ingestion over
            build_connector("csv_demo") and an entities filter naming exactly
            the files it adds to, so D1, D2 and E1 treat its rows exactly as
            they treat the demo's. Layer 1 has no deletes, so a delta only
            adds rows.
    loader  an operation Layer 1 cannot express: removing DOC-004, and rows
            of a second source system, which is not a D1 source. Each runs
            in SQLAlchemy Core over a session the caller owns, and never
            commits.

**The guard.** Every entry point refuses a database whose name ends in
neither _test nor _vs02 before it touches the database, so no fixture can
reach the development database. It follows tests/conftest.py's _test guard.

**Stored rows (VS02-M3).** Some named tests and coverage rows of plan A25.2
need rows that none of the ten entries holds and that neither Layer 1 nor
VS-01's frozen writer can produce: an assessment that differs from the
identity in one column, a stored band outside the vocabulary, an assessment
whose customer is gone, an assessment whose customer is a row outside the
scope it is stamped for (another source system's, or one under another
source entity; OD-M3-7), a deal whose stage or currency Layer 1 would have
rejected, and rows of a source system with no demo data. store_customer,
store_deal and store_assessment store exactly such rows, in the loader form:
SQLAlchemy Core over a session the caller owns, behind the same guard, and
never committing. They are not entries: the manifest holds the ten of plan
A24 and no eleventh. A test uses one only where its named test or coverage
row needs a stored row, and reserves the deal ids DEAL-980 to DEAL-999 for
the rows it adds to csv_demo.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.persistence.models import Customer, Deal, Document, Employee, RiskAssessment

PACKAGE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PACKAGE_DIR / "manifest.yaml"

#: The source system VS-02's acceptance figures are stated for, and the
#: connector every delta uses.
SOURCE = "csv_demo"
#: The second source system (VS-01 M2's precedent). It is not a D1 source, so
#: its rows cannot be ingested and are written by a loader.
OTHER_SOURCE = "other_demo"

#: The database names a fixture may be applied to: the suite's isolated test
#: database and the acceptance command's own database (plan A24, A27).
ALLOWED_DATABASE_SUFFIXES = ("_test", "_vs02")

#: The forms that carry material, and so can be applied.
DELTA = "delta"
LOADER = "loader"

#: DOC-004, the document plan A18.4's leave-out test removes.
LEFT_OUT_DOCUMENT = "DOC-004"

#: The second source system's employee. It carries the id that DEAL-964 of
#: the first source system names as its owner, so only the scoping of the
#: join keeps that deal UNRESOLVED (plan A24 entry 7).
OTHER_EMPLOYEE = "EMP-960"
#: The second source system's deal. It carries the id of a committed deal of
#: the first, so a read that lost its scope would count it twice or replace it.
OTHER_DEAL = "DEAL-001"

#: The source entity of every customer Layer 1 stores, and so of every
#: customer of a scope. A stored row may be given another (OD-M3-7).
CUSTOMERS = "customers"

#: Provenance for loader rows: fixed values, so two builds are identical.
_RUN_ID = uuid.UUID("00000000-0000-4000-8000-000000000960")
_INGESTED_AT = datetime(2026, 1, 1, tzinfo=UTC)
_RECORD_HASH = "0" * 64


class FixtureDatabaseRefusedError(Exception):
    """A fixture was pointed at a database that is neither a test nor an acceptance one."""


@dataclass(frozen=True)
class Fixture:
    """One manifest entry, as the loader reads it."""

    name: str
    entry: int
    origin: str
    form: str
    entities: tuple[str, ...]
    rows: Mapping[str, Any]
    fingerprint: str
    effect: str
    proofs: tuple[str, ...]

    @property
    def directory(self) -> Path:
        """Where a delta's seven csv_demo files live."""
        return PACKAGE_DIR / self.name


def load_manifest() -> dict[str, Any]:
    """The manifest exactly as committed."""
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        manifest: dict[str, Any] = yaml.safe_load(handle)
    return manifest


def _registry() -> Mapping[str, Fixture]:
    fixtures = {
        entry["name"]: Fixture(
            name=entry["name"],
            entry=entry["entry"],
            origin=entry["origin"],
            form=entry["form"],
            entities=tuple(entry.get("entities", ())),
            rows=entry["rows"],
            fingerprint=entry["fingerprint"],
            effect=entry["effect"],
            proofs=tuple(entry["proofs"]),
        )
        for entry in load_manifest()["fixtures"]
    }
    return MappingProxyType(fixtures)


#: Every plan A24 entry, by name, in manifest order.
FIXTURES: Mapping[str, Fixture] = _registry()


def check_database(name: str | None) -> None:
    """Refuse any database that is neither the suite's test database nor an acceptance one."""
    if name is None or not name.endswith(ALLOWED_DATABASE_SUFFIXES):
        raise FixtureDatabaseRefusedError(
            f"refusing to apply a VS-02 fixture to database {name!r}: its name must end in "
            f"{' or '.join(ALLOWED_DATABASE_SUFFIXES)}"
        )


def remove_doc004(session: Session) -> None:
    """The corpus without DOC-004. Core, over the caller's session; never commits."""
    check_database(session.get_bind().url.database)
    session.execute(
        delete(Document).where(
            Document.source_system == SOURCE, Document.source_id == LEFT_OUT_DOCUMENT
        )
    )


def add_second_source_system(session: Session) -> None:
    """
    One employee and one open valued deal in a second source system.

    The employee carries the id a deal of the first source system names as
    its owner, and the deal carries the id of a committed deal of the first.
    Core, over the caller's session; never commits.
    """
    check_database(session.get_bind().url.database)
    session.execute(insert(Employee).values(
        **_provenance("employees", OTHER_EMPLOYEE),
        name="Second Source System Employee", is_active=True))
    session.execute(insert(Deal).values(
        **_provenance("deals", OTHER_DEAL),
        name="Second Source System Deal", stage="negotiation", is_active=True,
        amount=Decimal("999999.99"), currency="USD", probability=Decimal("50.00"),
        expected_close_date=date(2026, 10, 15), owner_source_id=OTHER_EMPLOYEE,
        customer_source_id="CUST-001"))


def _provenance(entity_type: str, source_id: str) -> dict[str, object]:
    """The provenance columns a loader row needs. No foreign key constrains them."""
    return {
        "source_system": OTHER_SOURCE,
        "source_entity": entity_type,
        "source_id": source_id,
        "ingestion_run_id": _RUN_ID,
        "record_hash": _RECORD_HASH,
        "ingested_at": _INGESTED_AT,
    }


#: The loader entries, by manifest name.
LOADERS: Mapping[str, Callable[[Session], None]] = MappingProxyType({
    "second_source_system": add_second_source_system,
    "no_doc004": remove_doc004,
})


# ---------------------------------------------------------------------------
# Stored rows for VS02-M3 (plan A25.2, "Stored"): loaders, and not entries
# ---------------------------------------------------------------------------

#: Fixed ids for stored assessments, so that two builds are identical.
_ASSESSMENT_NAMESPACE = uuid.UUID("00000000-0000-4000-8000-000000000980")


def store_customer(session: Session, *, source_system: str, source_id: str,
                   source_entity: str = CUSTOMERS) -> None:
    """
    One row of `customers` in the named source system. Core; never commits.

    Its source entity is `customers` unless another is named. Layer 1 stores
    no other; a row under another entity is in the table and is a customer
    of no scope (plan A16.2, OD-M3-7).
    """
    check_database(session.get_bind().url.database)
    session.execute(insert(Customer).values(
        **_stored_provenance(source_system, source_entity, source_id),
        name=f"Stored customer {source_id}", is_active=True))


def store_deal(
    session: Session,
    *,
    source_system: str,
    source_id: str,
    stage: str | None,
    is_active: bool = True,
    amount: Decimal | None = None,
    currency: str | None = None,
    probability: Decimal | None = None,
    expected_close_date: date | None = None,
    owner_source_id: str | None = None,
    customer: str | None = None,
) -> None:
    """
    One deal row, as given. Layer 1 is not asked: a stage or a currency it
    would have rejected is stored as written. `customer` is the source id of
    a customer of the same source system, to which the deal's canonical
    foreign key is set. Core; never commits.
    """
    check_database(session.get_bind().url.database)
    session.execute(insert(Deal).values(
        **_stored_provenance(source_system, "deals", source_id),
        name=f"Stored deal {source_id}", stage=stage, is_active=is_active, amount=amount,
        currency=currency, probability=probability, expected_close_date=expected_close_date,
        owner_source_id=owner_source_id, customer_source_id=customer,
        customer_id=None if customer is None else _customer_id(session, source_system, customer)))


def store_assessment(
    session: Session,
    *,
    source_system: str,
    as_of: date,
    layer1_fingerprint: str,
    rules_version: int,
    linker_version: str,
    customer: str | None,
    band: str,
    executive_worthy: bool = False,
    customer_system: str | None = None,
    customer_entity: str = CUSTOMERS,
) -> None:
    """
    One risk_assessments row at exactly the identity given, with the band as
    written: VS-01's writer is not asked, so a band outside its vocabulary
    is stored as it is. `customer` is a customer's source id in
    `customer_system`, which is the assessment's own source system unless it
    is named, under `customer_entity`, which is `customers` unless it is
    named. Naming either stores what VS-01's writer cannot: an assessment
    that points at a row outside the scope it is stamped for (OD-M3-7). None
    stores a row whose customer is gone. Core; never commits.
    """
    check_database(session.get_bind().url.database)
    customer_id = None if customer is None else _customer_id(
        session, customer_system or source_system, customer, customer_entity)
    identity = (f"{source_system}|{as_of.isoformat()}|{layer1_fingerprint}|{rules_version}|"
                f"{linker_version}|{customer_system or source_system}|{customer}")
    if customer_entity != CUSTOMERS:
        identity += f"|{customer_entity}"
    session.execute(insert(RiskAssessment).values(
        id=uuid.uuid5(_ASSESSMENT_NAMESPACE, identity), customer_id=customer_id, as_of=as_of,
        source_system=source_system, layer1_fingerprint=layer1_fingerprint,
        rules_version=rules_version, linker_version=linker_version, band=band,
        executive_worthy=executive_worthy, signals={}, satisfied_rules=[],
        ranking_key=[0, 0, 0, customer or ""]))


def _customer_id(session: Session, source_system: str, source_id: str,
                 source_entity: str = CUSTOMERS) -> uuid.UUID:
    """The id of the one `customers` row with this source id in the source system and entity."""
    return session.execute(
        select(Customer.id).where(Customer.source_system == source_system,
                                  Customer.source_entity == source_entity,
                                  Customer.source_id == source_id)).scalar_one()


def _stored_provenance(source_system: str, entity_type: str, source_id: str) -> dict[str, object]:
    """The provenance columns of a stored row, in any source system. Fixed values."""
    return {**_provenance(entity_type, source_id), "source_system": source_system}


def ingest_delta(name: str, sessions: sessionmaker[Session]) -> RunSummary:
    """Ingest one delta through Layer 1's real path, restricted to the files it adds to."""
    fixture = FIXTURES[name]
    if fixture.form != DELTA:
        raise ValueError(f"{name} is a {fixture.form} entry, not a delta")
    check_database(_database_of(sessions))
    connector = build_connector(SOURCE, data_directory=fixture.directory)
    return run_ingestion(connector, sessions, IngestionRequest(entities=list(fixture.entities)))


def apply(name: str, sessions: sessionmaker[Session]) -> RunSummary | None:
    """
    Apply one entry to a database that already holds the baseline.

    A delta returns its ingestion run's summary. A loader runs in one
    transaction of its own and returns None.
    """
    fixture = FIXTURES[name]
    check_database(_database_of(sessions))
    if fixture.form == DELTA:
        return ingest_delta(name, sessions)
    with sessions.begin() as session:
        LOADERS[name](session)
    return None


def _database_of(sessions: sessionmaker[Session]) -> str | None:
    """The database a session factory is bound to, read without connecting."""
    bind = sessions.kw.get("bind")
    return None if bind is None else bind.url.database
