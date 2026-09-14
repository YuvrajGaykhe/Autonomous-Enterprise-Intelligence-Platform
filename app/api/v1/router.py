"""
API v1 router: every versioned route is mounted under /api/v1.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.health import router as health_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
