"""
The VS-01 §A26 fixture package (M9, plan §0.8.7).

The baseline is data/demo/, reused unchanged and built through the clean
full-dataset path. Every entry of manifest.yaml adds to it, changes it or
names material that already exists. Nothing here ever modifies data/.

Two forms carry material:

    delta   a directory of the seven csv_demo files in the committed column
            layout. A file the fixture does not add to holds its header row
            only, as data/fixtures/csv_demo_bad/ does. The delta is ingested
            with run_ingestion over build_connector("csv_demo") and an
            entities filter naming exactly the files it adds to, so D1, D2 and
            E1 treat its rows exactly as they treat the demo's. Layer 1 has no
            deletes, so a delta only adds rows.
    loader  an operation Layer 1 cannot express: removing DOC-005 and scaling
            every deal amount. Each runs in SQLAlchemy Core over a session the
            caller owns, and never commits.

The reuse and carried entries add no material and cannot be applied.

**The guard.** Every entry point refuses a database whose name ends in
neither _test nor _vs01 before it touches the database, so no fixture can
reach the development database. It follows tests/conftest.py's _test guard.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml
from sqlalchemy import delete, update
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.registry import build_connector
from app.ingestion.orchestrator import IngestionRequest, RunSummary, run_ingestion
from app.persistence.models import Deal, Document

PACKAGE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = PACKAGE_DIR / "manifest.yaml"

#: The only source system VS-01 assesses, and the connector every delta uses.
SOURCE = "csv_demo"

#: The database names a fixture may be applied to: the suite's isolated test
#: database and the acceptance command's own database (§0.8.4).
ALLOWED_DATABASE_SUFFIXES = ("_test", "_vs01")

#: The forms that carry material, and so can be applied.
DELTA = "delta"
LOADER = "loader"

#: DOC-005, the document §A25 test 4 leaves out.
LEFT_OUT_DOCUMENT = "DOC-005"

#: §A25 test 5's factor. An integer, so PostgreSQL's numeric product is exact.
AMOUNT_FACTOR = 1000


class FixtureDatabaseRefusedError(Exception):
    """A fixture was pointed at a database that is neither a test nor an acceptance one."""


@dataclass(frozen=True)
class Fixture:
    """One manifest entry, as the loader reads it."""

    name: str
    origin: str
    form: str
    entities: tuple[str, ...]
    rows: Mapping[str, Any]
    fingerprint: str
    effect: str
    proofs: tuple[str, ...]
    carried_from: str | None

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
            origin=entry["origin"],
            form=entry["form"],
            entities=tuple(entry.get("entities", ())),
            rows=entry["rows"],
            fingerprint=entry["fingerprint"],
            effect=entry["effect"],
            proofs=tuple(entry["proofs"]),
            carried_from=entry.get("carried_from"),
        )
        for entry in load_manifest()["fixtures"]
    }
    return MappingProxyType(fixtures)


#: Every §A26 entry, by name, in manifest order.
FIXTURES: Mapping[str, Fixture] = _registry()


def check_database(name: str | None) -> None:
    """Refuse any database that is neither the suite's test database nor an acceptance one."""
    if name is None or not name.endswith(ALLOWED_DATABASE_SUFFIXES):
        raise FixtureDatabaseRefusedError(
            f"refusing to apply a VS-01 fixture to database {name!r}: its name must end in "
            f"{' or '.join(ALLOWED_DATABASE_SUFFIXES)}"
        )


def remove_doc005(session: Session) -> None:
    """The corpus without DOC-005. Core, over the caller's session; never commits."""
    check_database(session.get_bind().url.database)
    session.execute(
        delete(Document).where(
            Document.source_system == SOURCE, Document.source_id == LEFT_OUT_DOCUMENT
        )
    )


def scale_deal_amounts(session: Session) -> None:
    """Every csv_demo deal amount times exactly 1000. Core, over the caller's session."""
    check_database(session.get_bind().url.database)
    session.execute(
        update(Deal)
        .where(Deal.source_system == SOURCE)
        .values(amount=Deal.amount * AMOUNT_FACTOR)
    )


#: The loader entries, by manifest name.
LOADERS: Mapping[str, Callable[[Session], None]] = MappingProxyType({
    "no_doc005": remove_doc005,
    "scaled_amounts": scale_deal_amounts,
})


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
    transaction of its own and returns None. An entry that adds no material
    is refused, because there is nothing to apply.
    """
    fixture = FIXTURES[name]
    check_database(_database_of(sessions))
    if fixture.form == DELTA:
        return ingest_delta(name, sessions)
    if fixture.form == LOADER:
        with sessions.begin() as session:
            LOADERS[name](session)
        return None
    raise ValueError(f"{name} is a {fixture.form} entry and adds no material")


def _database_of(sessions: sessionmaker[Session]) -> str | None:
    """The database a session factory is bound to, read without connecting."""
    bind = sessions.kw.get("bind")
    return None if bind is None else bind.url.database
