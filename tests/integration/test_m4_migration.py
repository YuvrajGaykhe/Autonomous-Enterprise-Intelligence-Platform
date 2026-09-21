"""
The M4 migration as an additive step, tested at its own boundary.

test_h3_migrations.py already proves the whole chain reaches the expected
schema and unwinds to empty. What it cannot show is that THIS revision is
additive: that stopping at the previous head gives a database with no link
table, that one step forward adds exactly one table and touches nothing
else, and that one step back removes exactly that table and leaves Layer 1
whole. A downgrade that dropped a canonical table would still satisfy the
end-to-end test, because that test unwinds to base anyway.

So the assertions here are differences between two adjacent revisions, not
absolute table sets.
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

PREVIOUS_HEAD = "8bfd73b6af60"
M4_REVISION = "c4a1e97d5b02"
LINK_TABLE = "document_customer_links"

EXPECTED_COLUMNS = {
    "id", "document_id", "customer_id", "basis", "matched_token",
    "match_start", "match_end", "linker_version", "layer1_fingerprint",
}
IDENTITY_COLUMNS = [
    "document_id", "customer_id", "basis", "linker_version", "layer1_fingerprint",
]


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
    name = f"{base.database}_m4_migration_test"
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
    """A database migrated to B1 and no further."""
    _run(migration_url, command.downgrade, "base")
    _run(migration_url, command.upgrade, PREVIOUS_HEAD)
    engine = create_engine(migration_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


# ---------------------------------------------------------------------------
# The revision chains where the plan says it does
# ---------------------------------------------------------------------------


def test_the_m4_revision_chains_after_the_b1_schema():
    """Plan A18: an additive revision from 8bfd73b6af60."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("postgresql://unused/unused"))
    revision = script.get_revision(M4_REVISION)

    assert revision.down_revision == PREVIOUS_HEAD
    assert list(script.get_heads()) == [M4_REVISION]


def test_the_previous_head_has_no_link_table(at_previous_head):
    """The control: without this revision the table genuinely does not exist."""
    assert LINK_TABLE not in _tables(at_previous_head)


# ---------------------------------------------------------------------------
# Upgrade adds exactly one table
# ---------------------------------------------------------------------------


def test_upgrading_adds_only_the_link_table(at_previous_head, migration_url):
    before = _tables(at_previous_head)

    _run(migration_url, command.upgrade, "head")

    assert _tables(at_previous_head) - before == {LINK_TABLE}


def test_the_created_table_matches_the_orm_model(at_previous_head, migration_url):
    _run(migration_url, command.upgrade, "head")
    inspector = inspect(at_previous_head)

    actual = {column["name"] for column in inspector.get_columns(LINK_TABLE)}
    expected = {column.name for column in Base.metadata.tables[LINK_TABLE].columns}

    assert actual == expected == EXPECTED_COLUMNS


def test_every_column_is_not_null(at_previous_head, migration_url):
    """
    DerivedLink validates every corresponding value as present, so a
    nullable column could hold a link the contract would refuse.
    """
    _run(migration_url, command.upgrade, "head")

    for column in inspect(at_previous_head).get_columns(LINK_TABLE):
        assert not column["nullable"], column["name"]


def test_the_identity_constraint_is_the_five_column_key(at_previous_head, migration_url):
    """§0.3.4's key, enforced by the database rather than by the application."""
    _run(migration_url, command.upgrade, "head")

    unique = {
        constraint["name"]: constraint["column_names"]
        for constraint in inspect(at_previous_head).get_unique_constraints(LINK_TABLE)
    }

    assert unique == {"uq_document_customer_links_identity": IDENTITY_COLUMNS}


def test_both_foreign_keys_cascade(at_previous_head, migration_url):
    """
    SET NULL is structurally impossible here: both columns are NOT NULL, and
    a link missing either endpoint asserts nothing.
    """
    _run(migration_url, command.upgrade, "head")

    keys = {
        key["referred_table"]: key.get("options", {}).get("ondelete")
        for key in inspect(at_previous_head).get_foreign_keys(LINK_TABLE)
    }

    assert keys == {"documents": "CASCADE", "customers": "CASCADE"}


def test_the_customer_lookup_is_indexed(at_previous_head, migration_url):
    """documents_for queries by customer; the unique index leads with document_id."""
    _run(migration_url, command.upgrade, "head")

    indexes = {index["name"] for index in inspect(at_previous_head).get_indexes(LINK_TABLE)}

    assert "ix_document_customer_links_customer_id" in indexes
    assert "ix_document_customer_links_document_id" in indexes


def test_no_canonical_table_gained_a_column(at_previous_head, migration_url):
    """
    Plan A31: Layer 1 is untouched. documents and customers are exactly what
    B1 created them as.
    """
    inspector = inspect(at_previous_head)
    before = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("documents", "customers")
    }

    _run(migration_url, command.upgrade, "head")

    inspector = inspect(at_previous_head)
    after = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in ("documents", "customers")
    }

    assert after == before


# ---------------------------------------------------------------------------
# Downgrade removes exactly that table
# ---------------------------------------------------------------------------


def test_downgrading_removes_only_the_link_table(at_previous_head, migration_url):
    """
    The assertion the end-to-end migration test cannot make: it unwinds to
    base, so a downgrade that dropped `documents` too would still pass there.
    """
    before = _tables(at_previous_head)
    _run(migration_url, command.upgrade, "head")
    assert LINK_TABLE in _tables(at_previous_head)

    _run(migration_url, command.downgrade, PREVIOUS_HEAD)

    assert _tables(at_previous_head) == before
    assert LINK_TABLE not in _tables(at_previous_head)


def test_the_cycle_is_repeatable(at_previous_head, migration_url):
    """Up, down, up again: the revision is not one-way."""
    _run(migration_url, command.upgrade, "head")
    _run(migration_url, command.downgrade, PREVIOUS_HEAD)
    _run(migration_url, command.upgrade, "head")

    assert LINK_TABLE in _tables(at_previous_head)
    assert {column["name"] for column in
            inspect(at_previous_head).get_columns(LINK_TABLE)} == EXPECTED_COLUMNS


def test_the_model_declares_the_same_identity_constraint_as_the_migration(
    at_previous_head, migration_url
):
    """
    Model and migration must agree, and nothing else checks it here.

    The migration creates the real constraint, so a test that only inspects
    the database would pass while the ORM model declared a weaker key - and
    the model is what a reader consults. Both are asserted, and against each
    other.
    """
    _run(migration_url, command.upgrade, "head")

    declared = {
        constraint.name: list(constraint.columns.keys())
        for constraint in Base.metadata.tables[LINK_TABLE].constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    observed = {
        constraint["name"]: constraint["column_names"]
        for constraint in inspect(at_previous_head).get_unique_constraints(LINK_TABLE)
    }

    assert declared == observed
    assert declared == {"uq_document_customer_links_identity": IDENTITY_COLUMNS}


def test_the_model_declares_the_same_indexes_as_the_migration(at_previous_head, migration_url):
    """
    The same agreement for the two access paths documents_for depends on.

    PostgreSQL also reports the index backing the unique constraint, which
    the ORM does not declare separately. That one difference is named
    explicitly rather than absorbed by a subset check, so any OTHER
    divergence still fails.
    """
    _run(migration_url, command.upgrade, "head")

    declared = {index.name for index in Base.metadata.tables[LINK_TABLE].indexes}
    observed = {index["name"] for index in inspect(at_previous_head).get_indexes(LINK_TABLE)}

    assert declared == {
        "ix_document_customer_links_customer_id",
        "ix_document_customer_links_document_id",
    }
    assert observed - declared == {"uq_document_customer_links_identity"}
    assert declared <= observed
