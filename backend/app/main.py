"""FastAPI application entrypoint.

Run locally:
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import check_database_connection, dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import register_middleware

log = get_logger(__name__)

DESCRIPTION = """
Analytical API for football recruitment intelligence.

Serves derived metrics, contextual percentiles, intelligence scores, player
role fit, statistical similarity and recruitment rankings.

**Scoring formulas, similarity modelling and identity-resolution logic run
server-side and are not exposed through this API.** Endpoints return results,
not implementations.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("startup", **settings.safe_summary())

    db_ok, db_error = check_database_connection()
    if db_ok:
        log.info("database_connected")
    else:
        # Do not abort: the API should still start and report itself unhealthy,
        # so an operator sees a 503 with a reason rather than a crash loop.
        log.error("database_unavailable_at_startup", error=db_error)

    if settings.app_mode.value == "production" and not settings.footystats_configured:
        log.warning(
            "production_mode_without_footystats_key",
            detail="Performance data features will be unavailable.",
        )

    yield

    dispose_engine()
    log.info("shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory. Tests build isolated instances through this."""
    settings = settings or get_settings()
    configure_logging(settings)

    # Interactive docs describe the API surface; keep them off in production.
    expose_docs = not settings.is_production

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    register_middleware(app, settings)
    register_exception_handlers(app, settings)
    app.include_router(api_router)

    return app


app = create_app()
