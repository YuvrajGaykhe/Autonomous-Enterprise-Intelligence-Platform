"""
API v1 router: every versioned route is mounted under /api/v1.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.entities import router as entities_router
from app.api.v1.health import router as health_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.sources import router as sources_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(sources_router)
api_router.include_router(ingestion_router)
api_router.include_router(entities_router)
