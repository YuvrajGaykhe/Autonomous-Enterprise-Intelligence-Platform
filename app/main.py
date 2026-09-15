"""
FastAPI application entry point.

create_app wires the application-scoped resources (the database session
factory, the connector provider and the in-process ingestion counters, which
start at zero with the application), the request-ID middleware, the
structured error handlers and the versioned /api/v1 router. Application startup configures structured logging
from APP_LOG_LEVEL and LOG_FORMAT (app.core.logging); invalid values stop
startup.

The API engine never echoes SQL and hides bound parameters from database
error messages, so source payload values cannot reach logs through a
database exception.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.connectors import ConnectorProvider
from app.api.errors import install_error_handlers
from app.api.request_id import RequestIdMiddleware
from app.api.v1.router import api_router
from app.core.config import SERVICE_VERSION, get_settings
from app.core.logging import configured_logging
from app.observability.metrics import ProcessMetrics

# Bounds how long a readiness probe waits for an unreachable PostgreSQL host.
DATABASE_CONNECT_TIMEOUT_SECONDS = 5


def _create_engine() -> Engine:
    return create_engine(
        get_settings().effective_database_url,
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS},
    )


def create_app(
    *,
    sessions: sessionmaker[Session] | None = None,
    connectors: ConnectorProvider | None = None,
    process_metrics: ProcessMetrics | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        sessions: session factory to use; by default one is bound to a new
            engine for DATABASE_URL, disposed when the application shuts down.
        connectors: connector provider to use; by default the committed
            config/connectors/ sources, each built on first use.
        process_metrics: in-process ingestion counters to use; by default new
            counters starting now.
    """
    engine: Engine | None = None
    if sessions is None:
        engine = _create_engine()
        sessions = sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        with configured_logging(settings.app_log_level, settings.log_format):
            yield
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="AI CEO — Layer 1",
        description="Connector and Ingestion Subsystem",
        version=SERVICE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.connectors = ConnectorProvider() if connectors is None else connectors
    app.state.process_metrics = ProcessMetrics() if process_metrics is None else process_metrics
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
