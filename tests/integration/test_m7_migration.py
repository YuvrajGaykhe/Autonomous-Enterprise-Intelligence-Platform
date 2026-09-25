"""
The M7 migration as an additive step, tested at its own boundary (§0.6.5).

M4's migration test is the pattern: test_h3_migrations.py proves the whole
chain reaches the expected schema and unwinds to empty, and cannot show that
THIS revision is additive. So the assertions here are differences between two
adjacent revisions: stopping at M4's head gives no M7 table, one step forward
adds exactly three tables and touches nothing else, and one step back removes
exactly those three and leaves Layer 1 and the link table whole.

The column, nullability, key, foreign-key, index and default contract is
§0.6.5's, asserted against the database and against the ORM models, and the
two against each other: a test that only inspected the database would pass
while a model declared a weaker key.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine.url import make_url

import app.persistence.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]

PREVIOUS_HEAD = "c4a1e97d5b02"
M7_REVISION = "66eddc6b7136"
M7_TABLES = {"risk_assessments", "risk_positions", "risk_briefs"}

#: §0.6.5, column for column.
EXPECTED_COLUMNS = {
    "risk_assessments": {
        "id", "customer_id", "as_of", "source_system", "layer1_fingerprint",
        "rules_version", "linker_version", "band", "executive_worthy", "signals",
        "satisfied_rules", "ranking_key",
    },
    # Exactly the nine directed columns, and no `confidence` (§0.6.14 OPEN-M7-1).
    "risk_positions": {
        "id", "assessment_id", "ordinal", "function", "object_ref", "proposed_action",
        "stance", "rationale", "citations",
    },
    "risk_briefs": {
        "id", "assessment_id", "policy_version", "template_version", "decision_payload",
        "payload_hash", "narrative", "status",
    },
}
IDENTITY_KEYS = {
    "risk_assessments": {"uq_risk_assessments_identity": [
        "customer_id", "as_of", "source_system", "layer1_fingerprint",
        "rules_version", "linker_version"]},
    "risk_positions": {"uq_risk_positions_identity": [
        "assessment_id", "function", "object_ref", "proposed_action"]},
    "risk_briefs": {"uq_risk_briefs_identity": ["assessment_id", "payload_hash"]},
}
FOREIGN_KEYS = {
    "risk_assessments": {("customer_id", "customers", "SET NULL")},
    "risk_positions": {("assessment_id", "risk_assessments", "CASCADE")},
    "risk_briefs": {("assessment_id", "risk_assessments", "CASCADE")},
}
INDEXES = {
    "risk_assessments": {"ix_risk_assessments_customer_id"},
    "risk_positions": {"ix_risk_positions_assessment_id"},
    "risk_briefs": {"ix_risk_briefs_assessment_id"},
}
JSONB_COLUMNS = {
    "risk_assessments": {"signals", "satisfied_rules", "ranking_key"},
    "risk_positions": {"citations"},
    "risk_briefs": {"decision_payload"},
}


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
    name = f"{base.database}_m7_migration_test"
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
    """A database migrated to M4's head and no further."""
    _run(migration_url, command.downgrade, "base")
    _run(migration_url, command.upgrade, PREVIOUS_HEAD)
    engine = create_engine(migration_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def at_m7(at_previous_head: Engine, migration_url: str) -> Engine:
    """The same database, one step forward."""
    _run(migration_url, command.upgrade, M7_REVISION)
    return at_previous_head


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def _schema(engine: Engine, tables) -> dict[str, dict[str, tuple[str, bool]]]:
    inspector = inspect(engine)
    return {
        table: {
            column["name"]: (str(column["type"]), column["nullable"])
            for column in inspector.get_columns(table)
        }
        for table in sorted(tables)
    }


# ---------------------------------------------------------------------------
# The revision chains where the plan says it does
# ---------------------------------------------------------------------------


def test_the_m7_revision_chains_after_m4_and_is_the_single_head():
    """§0.6.5: the second additive revision, down_revision c4a1e97d5b02, one head."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused/unused"))

    assert script.get_revision(M7_REVISION).down_revision == PREVIOUS_HEAD
    assert list(script.get_heads()) == [M7_REVISION]


def test_m4s_head_has_no_m7_table(at_previous_head):
    """The control: without this revision the tables genuinely do not exist."""
    assert not M7_TABLES & _tables(at_previous_head)


# ---------------------------------------------------------------------------
# Upgrade adds exactly three tables
# ---------------------------------------------------------------------------


def test_upgrading_adds_exactly_the_three_tables(at_previous_head, migration_url):
    before = _tables(at_previous_head)

    _run(migration_url, command.upgrade, M7_REVISION)

    assert _tables(at_previous_head) - before == M7_TABLES


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_each_table_has_exactly_its_directed_columns(at_m7, table):
    actual = {column["name"] for column in inspect(at_m7).get_columns(table)}
    declared = {column.name for column in Base.metadata.tables[table].columns}

    assert actual == declared == EXPECTED_COLUMNS[table]


def test_there_is_no_confidence_column():
    """§0.6.14 OPEN-M7-1: the frozen Position has no confidence, so no column holds one."""
    for table in M7_TABLES:
        assert "confidence" not in EXPECTED_COLUMNS[table]
        assert "confidence" not in Base.metadata.tables[table].columns


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_no_table_has_a_timestamp_column(at_m7, table):
    """§0.6.5: no timestamp column anywhere; an assessment is a function of its key."""
    for column in inspect(at_m7).get_columns(table):
        assert "TIMESTAMP" not in str(column["type"]).upper(), f"{table}.{column['name']}"


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_only_the_customer_reference_is_nullable(at_m7, table):
    """NOT NULL unless stated; SET NULL is the one stated exception (DR2)."""
    nullable = {
        column["name"] for column in inspect(at_m7).get_columns(table) if column["nullable"]
    }
    declared = {
        column.name for column in Base.metadata.tables[table].columns if column.nullable
    }

    expected = {"customer_id"} if table == "risk_assessments" else set()
    assert nullable == declared == expected


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_the_json_columns_are_jsonb(at_m7, table):
    types = {column["name"]: str(column["type"]) for column in inspect(at_m7).get_columns(table)}

    for name in JSONB_COLUMNS[table]:
        assert types[name] == "JSONB", f"{table}.{name}"


def test_the_column_types_are_the_directed_ones(at_m7):
    """§0.6.5's types and sizes (DR3), as PostgreSQL reports them."""
    schema = _schema(at_m7, M7_TABLES)

    assert {name: kind for name, (kind, _) in schema["risk_assessments"].items()} == {
        "id": "UUID", "customer_id": "UUID", "as_of": "DATE",
        "source_system": "VARCHAR(100)", "layer1_fingerprint": "VARCHAR(64)",
        "rules_version": "INTEGER", "linker_version": "VARCHAR(50)", "band": "VARCHAR(50)",
        "executive_worthy": "BOOLEAN", "signals": "JSONB", "satisfied_rules": "JSONB",
        "ranking_key": "JSONB",
    }
    assert {name: kind for name, (kind, _) in schema["risk_positions"].items()} == {
        "id": "UUID", "assessment_id": "UUID", "ordinal": "INTEGER",
        "function": "VARCHAR(50)", "stance": "VARCHAR(50)", "proposed_action": "VARCHAR(50)",
        "object_ref": "VARCHAR(255)", "rationale": "TEXT", "citations": "JSONB",
    }
    assert {name: kind for name, (kind, _) in schema["risk_briefs"].items()} == {
        "id": "UUID", "assessment_id": "UUID", "policy_version": "INTEGER",
        "template_version": "VARCHAR(50)", "decision_payload": "JSONB",
        "payload_hash": "VARCHAR(64)", "narrative": "TEXT", "status": "VARCHAR(50)",
    }


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_the_identity_key_is_the_directed_one_in_model_and_database(at_m7, table):
    declared = {
        constraint.name: list(constraint.columns.keys())
        for constraint in Base.metadata.tables[table].constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    observed = {
        constraint["name"]: constraint["column_names"]
        for constraint in inspect(at_m7).get_unique_constraints(table)
    }

    assert declared == observed == IDENTITY_KEYS[table]


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_the_foreign_keys_and_their_delete_rules(at_m7, table):
    observed = {
        (key["constrained_columns"][0], key["referred_table"],
         key.get("options", {}).get("ondelete"))
        for key in inspect(at_m7).get_foreign_keys(table)
    }
    declared = {
        (constraint.column_keys[0], list(constraint.elements)[0].column.table.name,
         constraint.ondelete)
        for constraint in Base.metadata.tables[table].foreign_key_constraints
    }

    assert observed == declared == FOREIGN_KEYS[table]


@pytest.mark.parametrize("table", sorted(M7_TABLES))
def test_every_foreign_key_is_indexed_in_model_and_database(at_m7, table):
    """
    §0.6.5: every FK indexed. PostgreSQL also reports the index backing the
    unique constraint, which the ORM does not declare separately; that one
    difference is named rather than absorbed by a subset check.
    """
    declared = {index.name for index in Base.metadata.tables[table].indexes}
    observed = {index["name"] for index in inspect(at_m7).get_indexes(table)}
    (identity,) = IDENTITY_KEYS[table]

    assert declared == INDEXES[table]
    assert observed - declared == {identity}
    indexed = {
        tuple(index["column_names"]) for index in inspect(at_m7).get_indexes(table)
    }
    for column, _, _ in FOREIGN_KEYS[table]:
        assert (column,) in indexed, f"{table}.{column}"


def test_a_brief_defaults_to_draft_in_the_database(at_m7):
    """§0.6.5: server default 'DRAFT', so a row written without a status is a draft."""
    (status,) = [
        column for column in inspect(at_m7).get_columns("risk_briefs")
        if column["name"] == "status"
    ]
    column = Base.metadata.tables["risk_briefs"].columns["status"]

    assert status["default"] == "'DRAFT'::character varying"
    assert column.server_default is not None
    assert column.server_default.arg == "DRAFT"
    assert column.default is not None and column.default.arg == "DRAFT"


def test_no_other_table_changed(at_previous_head, migration_url):
    """
    Plan A31: Layer 1 is untouched, and so is M4's link table. Every table
    that existed before the step has the same columns, types and nullability
    after it.
    """
    before_tables = _tables(at_previous_head)
    before = _schema(at_previous_head, before_tables)

    _run(migration_url, command.upgrade, M7_REVISION)

    assert _schema(at_previous_head, before_tables) == before


# ---------------------------------------------------------------------------
# Downgrade removes exactly those tables
# ---------------------------------------------------------------------------


def test_downgrading_removes_exactly_the_three_tables(at_previous_head, migration_url):
    before = _tables(at_previous_head)
    before_schema = _schema(at_previous_head, before)
    _run(migration_url, command.upgrade, M7_REVISION)
    assert M7_TABLES <= _tables(at_previous_head)

    _run(migration_url, command.downgrade, PREVIOUS_HEAD)

    assert _tables(at_previous_head) == before
    assert _schema(at_previous_head, before) == before_schema


def test_the_cycle_is_repeatable(at_previous_head, migration_url):
    _run(migration_url, command.upgrade, M7_REVISION)
    first = _schema(at_previous_head, M7_TABLES)
    _run(migration_url, command.downgrade, PREVIOUS_HEAD)
    _run(migration_url, command.upgrade, M7_REVISION)

    assert _schema(at_previous_head, M7_TABLES) == first
