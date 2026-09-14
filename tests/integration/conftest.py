"""
Isolated PostgreSQL harness for E1 integration tests.

E1 tests need real commits and rollbacks, so they cannot share the
development database or the rollback-per-test pattern of the B1 tests.
Once per test session the harness recreates <database>_test on the
configured PostgreSQL server, migrates it with the committed Alembic
migrations (so every session proves an empty database reaches head), and
truncates every table before each test.

The guard refuses any database name that does not end in "_test".
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

import app.persistence.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base

REPO = Path(__file__).resolve().parents[2]
_TEST_DATABASE = re.compile(r"[a-z][a-z0-9_]*_test")


def _test_database_url() -> str:
    url = make_url(get_settings().effective_database_url)
    name = f"{url.database}_test"
    if not _TEST_DATABASE.fullmatch(name):
        raise RuntimeError(f"refusing to use non-test database {name!r}")
    return url.set(database=name).render_as_string(hide_password=False)


def _recreate_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(str(target.database))
    try:
        with admin.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {quoted}"))
    finally:
        admin.dispose()


def _migrate(url: str) -> None:
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "migrations"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            del os.environ["DATABASE_URL"]
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session")
def e1_engine() -> Iterator[Engine]:
    url = _test_database_url()
    _recreate_database(url)
    _migrate(url)
    engine = create_engine(url, echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def e1_sessions(e1_engine: Engine) -> sessionmaker[Session]:
    """A session factory over a freshly truncated test database."""
    tables = ", ".join(
        e1_engine.dialect.identifier_preparer.quote(table.name)
        for table in Base.metadata.sorted_tables
    )
    with e1_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=e1_engine, expire_on_commit=False)
