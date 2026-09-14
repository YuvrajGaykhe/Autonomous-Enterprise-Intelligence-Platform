"""
FastAPI dependencies shared by API routes.

Application-scoped resources are created once by app.main.create_app and
kept on app.state; routes receive them through these dependencies.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.api.connectors import ConnectorProvider


def get_sessions(request: Request) -> sessionmaker[Session]:
    """The application's session factory. Routes own their transactions."""
    sessions: sessionmaker[Session] = request.app.state.sessions
    return sessions


@contextmanager
def read_snapshot(sessions: sessionmaker[Session]) -> Iterator[Session]:
    """A read-only session whose queries all see one REPEATABLE READ snapshot.

    A page and its total, and runs and their aggregates, stay consistent
    while an ingestion commits concurrently; the transaction cannot write.
    """
    with sessions() as session:
        session.connection(execution_options={
            "isolation_level": "REPEATABLE READ", "postgresql_readonly": True,
        })
        yield session


def get_connectors(request: Request) -> ConnectorProvider:
    """The application's connector provider."""
    connectors: ConnectorProvider = request.app.state.connectors
    return connectors
