"""
FastAPI application entry point.

Creates the FastAPI application instance and includes routers.
This is the minimal bootstrap required for Docker container startup.

The full router set (ingestion, entities, sources, metrics) will
be added in later tasks (F1, F2).
"""

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AI CEO — Layer 1",
        description="Connector and Ingestion Subsystem",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.include_router(health_router)

    return app


app = create_app()
