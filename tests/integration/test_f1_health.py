"""
GET /api/v1/health readiness against the migrated test database.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import create_app

pytestmark = pytest.mark.integration


def test_health_is_healthy_when_postgresql_is_reachable(e1_sessions):
    response = TestClient(create_app(sessions=e1_sessions)).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "ai-ceo-layer1",
                               "version": "0.1.0", "checks": {"database": "ok"}}


def test_health_is_unhealthy_when_no_pooled_connection_is_available(e1_engine, caplog):
    engine = create_engine(e1_engine.url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    try:
        with engine.connect(), caplog.at_level(logging.WARNING, logger="app.api.v1.health"):
            response = TestClient(create_app(sessions=sessionmaker(bind=engine))).get(
                "/api/v1/health")
    finally:
        engine.dispose()
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}
    assert [record.getMessage() for record in caplog.records] == [
        "readiness_check_failed dependency=database failure=TimeoutError"]
