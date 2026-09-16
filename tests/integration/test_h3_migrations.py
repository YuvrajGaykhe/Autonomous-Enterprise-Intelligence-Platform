"""
H3 migration tests (spec Section 15, "Database integration: migrations").

The spec requires that an empty PostgreSQL database reaches the expected
schema through the committed versioned migrations, and Section 21 rejects
"no migrations" as an anti-pattern. The E1 harness migrates its database once
per session, which proves the upgrade runs; it does not prove that the
result matches the ORM, that the history has a single head, or that the
downgrade path works.

These tests own a database of their own (<database>_migrations_test) so the
schema can be built and torn down repeatedly without disturbing the shared
E1 database, and they compare the migrated schema against Base.metadata
column by column, so a model change that never reached a migration fails
here rather than at the first INSERT in production.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url

import app.persistence.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

#: The canonical entity tables (spec Section 6.2) and the operational
#: tables (Section 6.3). An empty database must reach exactly these.
CANONICAL_TABLES = (
    "organizations", "employees", "customers", "deals",
    "projects", "support_tickets", "documents",
)
OPERATIONAL_TABLES = (
    "ingestion_runs", "ingestion_errors", "source_records",
    "connector_configs", "ingestion_cursors",
)
EXPECTED_TABLES = frozenset(CANONICAL_TABLES + OPERATIONAL_TABLES)


def _alembic_config(url: str) -> Config:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _run(url: str, action, *args) -> None:
    """Run an alembic command against url, restoring DATABASE_URL after."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        action(_alembic_config(url), *args)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="module")
def migration_url() -> Iterator[str]:
    """A private, empty database that only this module touches."""
    base = make_url(get_settings().effective_database_url)
    name = f"{base.database}_migrations_test"
    if not name.endswith("_test"):
        raise RuntimeError(f"refusing to use non-test database {name!r}")
    url = base.set(database=name)

    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(name)
    try:
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {quoted}"))
        yield url.render_as_string(hide_password=False)
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
    finally:
        admin.dispose()


@pytest.fixture
def empty_database(migration_url: str) -> Iterator[Engine]:
    """The private database at base (no tables), engine disposed after."""
    _run(migration_url, command.downgrade, "base")
    engine = create_engine(migration_url)
    try:
        yield engine
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Migration history
# ---------------------------------------------------------------------------


def test_the_migration_history_has_exactly_one_head():
    """Two heads would make `alembic upgrade head` ambiguous."""
    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused/unused"))
    assert len(script.get_heads()) == 1


def test_every_revision_is_reachable_from_the_head():
    """The history is a single unbroken chain back to base."""
    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused/unused"))
    head = script.get_heads()[0]
    chain = [revision.revision for revision in script.walk_revisions("base", head)]
    assert len(chain) == len(set(chain))
    assert len(chain) == len(list(script.walk_revisions()))


def test_every_revision_declares_an_upgrade_and_a_downgrade():
    """A migration without a downgrade cannot be rolled back."""
    versions = sorted((REPO / "migrations" / "versions").glob("*.py"))
    assert versions, "no migrations are committed"
    for path in versions:
        source = path.read_text(encoding="utf-8")
        assert "def upgrade()" in source, path.name
        assert "def downgrade()" in source, path.name


# ---------------------------------------------------------------------------
# Empty database -> head
# ---------------------------------------------------------------------------


def test_an_empty_database_reaches_the_expected_schema(empty_database, migration_url):
    """Spec Section 20 D: migrations succeed from an empty database."""
    assert inspect(empty_database).get_table_names() == ["alembic_version"]

    _run(migration_url, command.upgrade, "head")

    tables = set(inspect(empty_database).get_table_names()) - {"alembic_version"}
    assert tables == EXPECTED_TABLES


def test_the_migrated_schema_matches_the_orm_models(empty_database, migration_url):
    """A model column that never reached a migration fails here."""
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(empty_database)

    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        actual = {column["name"]: column for column in inspector.get_columns(table.name)}
        assert set(actual) == {column.name for column in table.columns}, table.name
        for column in table.columns:
            assert actual[column.name]["nullable"] == column.nullable, (
                f"{table.name}.{column.name} nullability"
            )


def test_every_declared_unique_constraint_exists_in_the_database(empty_database, migration_url):
    """Source identity uniqueness is what makes re-ingestion idempotent."""
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(empty_database)

    for table in Base.metadata.tables.values():
        declared = {
            constraint.name: sorted(column.name for column in constraint.columns)
            for constraint in table.constraints
            if type(constraint).__name__ == "UniqueConstraint"
        }
        if not declared:
            continue
        actual = {
            constraint["name"]: sorted(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(table.name)
        }
        for name, columns in declared.items():
            assert actual.get(name) == columns, f"{table.name}.{name}"


def test_every_declared_index_exists_in_the_database(empty_database, migration_url):
    """Spec Section 20: indexes where specified."""
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(empty_database)

    for table in Base.metadata.tables.values():
        actual = {index["name"] for index in inspector.get_indexes(table.name)}
        for index in table.indexes:
            assert index.name in actual, f"{table.name}.{index.name}"


def test_every_declared_foreign_key_exists_with_its_delete_rule(empty_database, migration_url):
    """Unresolved-FK behaviour depends on the ON DELETE rule being present."""
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(empty_database)

    for table in Base.metadata.tables.values():
        actual = {
            key["name"]: (key["referred_table"], key.get("options", {}).get("ondelete"))
            for key in inspector.get_foreign_keys(table.name)
        }
        for constraint in table.foreign_key_constraints:
            referred = list(constraint.elements)[0].column.table.name
            expected_ondelete = constraint.ondelete
            observed_table, observed_ondelete = actual[constraint.name]
            assert observed_table == referred, f"{table.name}.{constraint.name}"
            if expected_ondelete is not None:
                assert (observed_ondelete or "").upper() == expected_ondelete.upper(), (
                    f"{table.name}.{constraint.name} ondelete"
                )


def test_every_canonical_table_carries_the_full_provenance_contract(
    empty_database, migration_url
):
    """Spec Section 6.1: every canonical entity keeps its provenance."""
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(empty_database)
    required = {
        "id", "source_system", "source_entity", "source_id",
        "source_updated_at", "ingested_at", "ingestion_run_id", "record_hash",
    }
    for table in CANONICAL_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert required <= columns, table


# ---------------------------------------------------------------------------
# Reversibility
# ---------------------------------------------------------------------------


def test_the_migrations_downgrade_back_to_an_empty_database(empty_database, migration_url):
    """Every table the upgrade created is dropped again."""
    _run(migration_url, command.upgrade, "head")
    assert set(inspect(empty_database).get_table_names()) > EXPECTED_TABLES

    _run(migration_url, command.downgrade, "base")
    assert set(inspect(empty_database).get_table_names()) - {"alembic_version"} == set()


def test_upgrade_downgrade_upgrade_reproduces_the_same_schema(empty_database, migration_url):
    """The pipeline is repeatable, not one-way (A3's stated purpose)."""
    _run(migration_url, command.upgrade, "head")
    first = _schema_fingerprint(empty_database)

    _run(migration_url, command.downgrade, "base")
    _run(migration_url, command.upgrade, "head")
    assert _schema_fingerprint(empty_database) == first


def test_upgrading_an_already_migrated_database_is_a_no_op(empty_database, migration_url):
    """Running `make migrate` twice must not fail or change the schema."""
    _run(migration_url, command.upgrade, "head")
    before = _schema_fingerprint(empty_database)
    _run(migration_url, command.upgrade, "head")
    assert _schema_fingerprint(empty_database) == before


def test_the_stamped_revision_is_the_single_head(empty_database, migration_url):
    """A migrated database reports the revision the repository declares."""
    _run(migration_url, command.upgrade, "head")
    script = ScriptDirectory.from_config(_alembic_config(migration_url))
    with empty_database.connect() as connection:
        stamped = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert stamped == script.get_heads()[0]


def _schema_fingerprint(engine: Engine) -> dict[str, object]:
    """Tables, columns, nullability, indexes and constraints, order-independent."""
    inspector = inspect(engine)
    fingerprint: dict[str, object] = {}
    for table in sorted(set(inspector.get_table_names()) - {"alembic_version"}):
        fingerprint[table] = {
            "columns": sorted(
                (column["name"], str(column["type"]), column["nullable"])
                for column in inspector.get_columns(table)
            ),
            "indexes": sorted(
                (index["name"], tuple(index["column_names"]))
                for index in inspector.get_indexes(table)
            ),
            "unique": sorted(
                (constraint["name"], tuple(sorted(constraint["column_names"])))
                for constraint in inspector.get_unique_constraints(table)
            ),
            "foreign_keys": sorted(
                (key["name"], key["referred_table"],
                 (key.get("options", {}).get("ondelete") or "").upper())
                for key in inspector.get_foreign_keys(table)
            ),
        }
    return fingerprint
