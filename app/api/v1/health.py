"""
Minimal health endpoint for API v1.

Provides /api/v1/health for container health checking and
basic service dependency verification.

This is intentionally minimal for A2. The full API contract
(ingestion, entities, sources, metrics) belongs to later tasks.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """
    Liveness/readiness probe.

    Returns basic application status. Database and mock-source
    connectivity checks are kept minimal for A2; the full health
    contract will be implemented in later tasks (F1).
    """
    return {
        "status": "healthy",
        "service": "ai-ceo-layer1",
        "version": "0.1.0",
    }
