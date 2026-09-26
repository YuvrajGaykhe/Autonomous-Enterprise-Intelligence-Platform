"""
The M8 migration as an additive step, tested at its own boundary (§0.7.5).

M7's migration test is the pattern: test_h3_migrations.py proves the whole
chain reaches the expected schema and unwinds to empty, and cannot show that
THIS revision is additive. So the assertions here are differences between two
adjacent revisions: stopping at M7's head gives no brief_decisions table, no
function and no trigger; one step forward adds exactly those three objects
and touches nothing else; one step back removes exactly them.

The column, nullability, foreign-key, index and trigger contract is §0.7.5's,
asserted against the database and, where the ORM declares it, against the
model too, so a test that only inspected the database cannot pass while the
model declares something weaker.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.url import make_url
from sqlalchemy.schema import CreateIndex

import app.persistence.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

PREVIOUS_HEAD = "66eddc6b7136"
M8_REVISION = "070e4968a497"
M8_MIGRATION = REPO / "migrations" / "versions" / "070e4968a497_m8_brief_decisions.py"
TABLE = "brief_decisions"
#: §0.7.5: the trigger and its function share one name.
APPEND_ONLY = "brief_decisions_append_only"

#: §0.7.5, column for column, as PostgreSQL reports each type.
EXPECTED_TYPES = {
    "id": "UUID",
    "brief_id": "UUID",
    "payload_hash": "VARCHAR(64)",
    "actor": "VARCHAR(255)",
    "decision": "VARCHAR(50)",
    "note": "VARCHAR(2000)",
    "decided_at": "TIMESTAMP",
    "supersedes_id": "UUID",
}
#: §0.7.5: only the note and the predecessor may be NULL.
NULLABLE = {"note", "supersedes_id"}
#: OPEN-M8-5: both foreign keys RESTRICT, named by NAMING_CONVENTION.
FOREIGN_KEYS = {
    ("fk_brief_decisions_brief_id_risk_briefs", "brief_id", "risk_briefs", "id", "RESTRICT"),
    ("fk_brief_decisions_supersedes_id_brief_decisions", "supersedes_id", "brief_decisions",
     "id", "RESTRICT"),
}
#: §0.7.5's three indexes, exactly as pg_indexes.indexdef prints them, and the key's.
INDEX_DEFINITIONS = {
    "pk_brief_decisions":
        "CREATE UNIQUE INDEX pk_brief_decisions ON public.brief_decisions USING btree (id)",
    "ix_brief_decisions_brief_id":
        "CREATE INDEX ix_brief_decisions_brief_id ON public.brief_decisions USING btree (brief_id)",
    "uq_brief_decisions_first_decision":
        "CREATE UNIQUE INDEX uq_brief_decisions_first_decision ON public.brief_decisions "
        "USING btree (brief_id) WHERE (supersedes_id IS NULL)",
    "uq_brief_decisions_one_successor":
        "CREATE UNIQUE INDEX uq_brief_decisions_one_successor ON public.brief_decisions "
        "USING btree (supersedes_id) WHERE (supersedes_id IS NOT NULL)",
}
#: The ORM declares the three; the primary key's index is the key's own.
DECLARED_INDEXES = {
    "ix_brief_decisions_brief_id": (["brief_id"], False, None),
    "uq_brief_decisions_first_decision": (["brief_id"], True, "supersedes_id IS NULL"),
    "uq_brief_decisions_one_successor": (["supersedes_id"], True, "supersedes_id IS NOT NULL"),
}

#: pg_trigger.tgtype bits (PostgreSQL's pg_trigger.h).
TRIGGER_ROW, TRIGGER_BEFORE, TRIGGER_INSERT = 1 << 0, 1 << 1, 1 << 2
TRIGGER_DELETE, TRIGGER_UPDATE, TRIGGER_TRUNCATE = 1 << 3, 1 << 4, 1 << 5


def _alembic_config(url: str) -> Config:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _run(url: str, action, *args) -> None:
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
    name = f"{base.database}_m8_migration_test"
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
def at_previous_head(migration_url: str) -> Iterator[Engine]:
    """A database migrated to M7's head and no further."""
    _run(migration_url, command.downgrade, "base")
    _run(migration_url, command.upgrade, PREVIOUS_HEAD)
    engine = create_engine(migration_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def at_m8(at_previous_head: Engine, migration_url: str) -> Engine:
    """The same database, one step forward."""
    _run(migration_url, command.upgrade, M8_REVISION)
    return at_previous_head


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def _functions(engine: Engine) -> set[str]:
    """Every function in the public schema: the database starts with none."""
    with engine.connect() as connection:
        return set(connection.execute(text(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public'")).scalars())


def _triggers(engine: Engine) -> set[str]:
    """Every user trigger; the internal ones that implement foreign keys are excluded."""
    with engine.connect() as connection:
        return set(connection.execute(text(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())


def _index_definitions(engine: Engine, table: str) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes"
            " WHERE schemaname = 'public' AND tablename = :table"), {"table": table}).all()
    return dict(rows)


def _fingerprint(engine: Engine, tables) -> dict[str, object]:
    """Columns, types, nullability, defaults, keys and index definitions, per table."""
    inspector = inspect(engine)
    return {
        table: {
            "columns": sorted(
                (column["name"], str(column["type"]), column["nullable"], column["default"])
                for column in inspector.get_columns(table)),
            "unique": sorted(
                (constraint["name"], tuple(constraint["column_names"]))
                for constraint in inspector.get_unique_constraints(table)),
            "foreign_keys": sorted(
                (key["name"], tuple(key["constrained_columns"]), key["referred_table"],
                 (key.get("options", {}).get("ondelete") or "").upper())
                for key in inspector.get_foreign_keys(table)),
            "indexes": sorted(_index_definitions(engine, table).items()),
        }
        for table in sorted(tables)
    }


def _objects(engine: Engine) -> tuple[set[str], set[str], set[str]]:
    return _tables(engine), _functions(engine), _triggers(engine)


def _normalised(predicate: str) -> str:
    return predicate.replace("(", "").replace(")", "").strip()


# ---------------------------------------------------------------------------
# The revision chains where the plan says it does
# ---------------------------------------------------------------------------


def test_the_m8_revision_chains_after_m7_and_is_the_single_head():
    """§0.7.5 and X4: the third additive revision, down_revision 66eddc6b7136, one head."""
    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused/unused"))

    assert script.get_revision(M8_REVISION).down_revision == PREVIOUS_HEAD
    assert list(script.get_heads()) == [M8_REVISION]
    assert Path(script.get_revision(M8_REVISION).path) == M8_MIGRATION


def test_m7s_head_has_no_brief_decisions(at_previous_head):
    """The control: without this revision the table, function and trigger do not exist."""
    tables, functions, triggers = _objects(at_previous_head)

    assert TABLE not in tables
    assert APPEND_ONLY not in functions
    assert APPEND_ONLY not in triggers


def test_the_migration_imports_nothing_from_the_application():
    """§0.7.5: hand-written DDL, like M4's and M7's: alembic, SQLAlchemy and typing only."""
    tree = ast.parse(M8_MIGRATION.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])

    assert roots <= {"__future__", "typing", "alembic", "sqlalchemy"}, roots


# ---------------------------------------------------------------------------
# Upgrade adds exactly one table, one function and one trigger
# ---------------------------------------------------------------------------


def test_upgrading_adds_exactly_the_table_its_function_and_its_trigger(
        at_previous_head, migration_url):
    tables, functions, triggers = _objects(at_previous_head)

    _run(migration_url, command.upgrade, M8_REVISION)

    after_tables, after_functions, after_triggers = _objects(at_previous_head)
    assert after_tables - tables == {TABLE}
    assert after_functions - functions == {APPEND_ONLY}
    assert after_triggers - triggers == {APPEND_ONLY}
    assert tables <= after_tables and functions <= after_functions and triggers <= after_triggers


def test_the_table_has_exactly_its_columns_in_model_and_database(at_m8):
    actual = {column["name"] for column in inspect(at_m8).get_columns(TABLE)}
    declared = {column.name for column in Base.metadata.tables[TABLE].columns}

    assert actual == declared == set(EXPECTED_TYPES)


def test_the_column_types_are_the_directed_ones(at_m8):
    columns = {column["name"]: column for column in inspect(at_m8).get_columns(TABLE)}

    assert {name: str(column["type"]) for name, column in columns.items()} == EXPECTED_TYPES
    assert columns["decided_at"]["type"].timezone is True
    assert Base.metadata.tables[TABLE].columns["decided_at"].type.timezone is True


def test_only_the_note_and_the_predecessor_are_nullable(at_m8):
    nullable = {column["name"] for column in inspect(at_m8).get_columns(TABLE)
                if column["nullable"]}
    declared = {column.name for column in Base.metadata.tables[TABLE].columns if column.nullable}

    assert nullable == declared == NULLABLE


def test_no_column_has_a_default_so_decided_at_is_always_supplied(at_m8):
    """X7: no server default anywhere, and no ORM default but the key's, as every model's is."""
    for column in inspect(at_m8).get_columns(TABLE):
        assert column["default"] is None, column["name"]
    for column in Base.metadata.tables[TABLE].columns:
        assert column.server_default is None, column.name
        assert column.default is None or column.name == "id", column.name
        assert column.onupdate is None and column.server_onupdate is None, column.name


def test_the_primary_key_is_the_id(at_m8):
    key = inspect(at_m8).get_pk_constraint(TABLE)

    assert (key["name"], key["constrained_columns"]) == ("pk_brief_decisions", ["id"])


def test_both_foreign_keys_restrict_in_model_and_database(at_m8):
    """OPEN-M8-5: a decided brief, or a superseded decision, cannot disappear by cascade."""
    observed = {
        (key["name"], key["constrained_columns"][0], key["referred_table"],
         key["referred_columns"][0], key.get("options", {}).get("ondelete"))
        for key in inspect(at_m8).get_foreign_keys(TABLE)
    }
    declared = {
        (constraint.name, constraint.column_keys[0],
         list(constraint.elements)[0].column.table.name,
         list(constraint.elements)[0].column.name, constraint.ondelete)
        for constraint in Base.metadata.tables[TABLE].foreign_key_constraints
    }

    assert observed == declared == FOREIGN_KEYS


def test_the_self_reference_is_a_plain_single_column_key(at_m8):
    """§0.7.18 Q-M8-2: no composite (supersedes_id, brief_id) key."""
    for key in inspect(at_m8).get_foreign_keys(TABLE):
        assert len(key["constrained_columns"]) == 1, key["name"]
    assert inspect(at_m8).get_unique_constraints(TABLE) == []


def test_the_indexes_are_exactly_the_directed_ones(at_m8):
    """pg_indexes, verbatim: both partial unique indexes with their WHERE clauses."""
    assert _index_definitions(at_m8, TABLE) == INDEX_DEFINITIONS


def test_the_model_declares_the_same_three_indexes(at_m8):
    """Name, columns, uniqueness and predicate, the model's DDL against the database's."""
    declared = {}
    for index in Base.metadata.tables[TABLE].indexes:
        predicate = index.dialect_options["postgresql"]["where"]
        ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        where = _normalised(ddl.split(" WHERE ", 1)[1]) if predicate is not None else None
        declared[index.name] = ([column.name for column in index.columns], index.unique, where)
    observed = {
        index["name"]: (index["column_names"], index["unique"],
                        _normalised(index["dialect_options"]["postgresql_where"])
                        if "postgresql_where" in index.get("dialect_options", {}) else None)
        for index in inspect(at_m8).get_indexes(TABLE)
    }

    assert declared == observed == DECLARED_INDEXES


def test_every_foreign_key_is_the_leading_column_of_an_index(at_m8):
    """§0.7.5: brief_id by its own index; supersedes_id by the successor index."""
    leading = {index["column_names"][0] for index in inspect(at_m8).get_indexes(TABLE)}

    assert {"brief_id", "supersedes_id"} <= leading


def test_the_function_is_the_one_trigger_function(at_m8):
    """pg_proc: one plpgsql function, no arguments, returning trigger."""
    with at_m8.connect() as connection:
        rows = connection.execute(text(
            "SELECT p.pronargs, p.prorettype::regtype::text, l.lanname"
            " FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang"
            " JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'public' AND p.proname = :name"), {"name": APPEND_ONLY}).all()

    assert [tuple(row) for row in rows] == [(0, "trigger", "plpgsql")]


def test_the_trigger_is_row_level_before_update_or_delete_and_enabled(at_m8):
    """pg_trigger: BEFORE, FOR EACH ROW, UPDATE and DELETE, never INSERT or TRUNCATE."""
    with at_m8.connect() as connection:
        rows = connection.execute(text(
            "SELECT t.tgtype, t.tgenabled, t.tgrelid::regclass::text, p.proname"
            " FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid"
            " WHERE NOT t.tgisinternal AND t.tgname = :name"), {"name": APPEND_ONLY}).all()

    [(kind, enabled, table, function)] = [tuple(row) for row in rows]
    assert (enabled, table, function) == ("O", TABLE, APPEND_ONLY)
    assert kind == TRIGGER_ROW | TRIGGER_BEFORE | TRIGGER_UPDATE | TRIGGER_DELETE
    assert not kind & (TRIGGER_INSERT | TRIGGER_TRUNCATE)


def test_brief_decisions_is_the_only_table_with_a_user_trigger(at_m8):
    with at_m8.connect() as connection:
        tables = connection.execute(text(
            "SELECT DISTINCT tgrelid::regclass::text FROM pg_trigger"
            " WHERE NOT tgisinternal")).scalars().all()

    assert tables == [TABLE]


def test_no_other_table_changed(at_previous_head, migration_url):
    """
    Plan A31: Layer 1, M4's link table and M7's three tables are untouched.
    Every table that existed before the step has the same columns, types,
    nullability, defaults, keys and index definitions after it.
    """
    before_tables = _tables(at_previous_head)
    before = _fingerprint(at_previous_head, before_tables)

    _run(migration_url, command.upgrade, M8_REVISION)

    assert _fingerprint(at_previous_head, before_tables) == before


# ---------------------------------------------------------------------------
# Downgrade removes exactly those objects
# ---------------------------------------------------------------------------


def test_downgrading_removes_exactly_the_table_its_function_and_its_trigger(
        at_previous_head, migration_url):
    before = _objects(at_previous_head)
    before_fingerprint = _fingerprint(at_previous_head, before[0])
    _run(migration_url, command.upgrade, M8_REVISION)
    assert TABLE in _tables(at_previous_head)

    _run(migration_url, command.downgrade, PREVIOUS_HEAD)

    assert _objects(at_previous_head) == before
    assert _fingerprint(at_previous_head, before[0]) == before_fingerprint


def test_the_cycle_is_repeatable(at_previous_head, migration_url):
    _run(migration_url, command.upgrade, M8_REVISION)
    first = (_fingerprint(at_previous_head, {TABLE}), _objects(at_previous_head))
    _run(migration_url, command.downgrade, PREVIOUS_HEAD)
    _run(migration_url, command.upgrade, M8_REVISION)

    assert (_fingerprint(at_previous_head, {TABLE}), _objects(at_previous_head)) == first
