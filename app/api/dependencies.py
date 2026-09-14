"""
FastAPI dependencies shared by API routes.

Application-scoped resources are created once by app.main.create_app and
kept on app.state; routes receive them through these dependencies.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


def get_sessions(request: Request) -> sessionmaker[Session]:
    """The application's session factory. Routes own their transactions."""
    sessions: sessionmaker[Session] = request.app.state.sessions
    return sessions
