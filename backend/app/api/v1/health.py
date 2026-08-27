"""Health and metadata endpoints.

`/health/live` answers only "is the process up" and never touches the
database, so a database outage does not cause an orchestrator to kill an
otherwise healthy container. `/health` is the readiness check.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import SettingsDep
from app.core.config import Settings
from app.core.database import check_database_connection, get_schema_revision
from app.core.errors import AppError
from app.core.logging import get_logger
from app.providers.registry import build_market_provider, build_performance_provider
from app.schemas.system import (
    DataSourceStatus,
    DependencyStatus,
    HealthResponse,
    LivenessResponse,
    MetaResponse,
)

log = get_logger(__name__)

router = APIRouter(tags=["system"])

APP_VERSION = "0.1.0"

DEMO_NOTICE = (
    "Demo mode: all player names and statistics shown are fabricated sample "
    "data generated for testing. They do not describe real footballers."
)


@router.get("/health/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Process liveness. Deliberately performs no I/O."""
    return LivenessResponse(status="ok")


@router.get("/health", response_model=HealthResponse)
def health(response: Response, settings: SettingsDep) -> HealthResponse:
    """Readiness: reports the application and every dependency it needs."""
    db_ok, db_error = check_database_connection()
    if not db_ok:
        # Driver messages name hosts, users and databases. Log them; do not
        # return them to the caller.
        log.error("health_database_unavailable", error=db_error)

    revision = get_schema_revision() if db_ok else None

    if not db_ok:
        db_status, db_detail = "unavailable", "Could not establish a database connection."
    elif revision is None:
        db_status, db_detail = (
            "degraded",
            "Database reachable but migrations have not been applied.",
        )
    else:
        db_status, db_detail = "ok", None

    dependencies = [
        DependencyStatus(name="postgresql", status=db_status, detail=db_detail),
        _footystats_status(settings),
    ]

    overall = "ok" if db_status == "ok" else "degraded"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status=overall,
        app_mode=settings.app_mode.value,  # type: ignore[arg-type]
        app_env=settings.app_env.value,
        version=APP_VERSION,
        schema_revision=revision,
        dependencies=dependencies,
    )


def _footystats_status(settings: Settings) -> DependencyStatus:
    """FootyStats readiness.

    In demo mode an absent key is the expected state, not a fault: the mock
    provider is in use and nothing calls FootyStats.
    """
    if not settings.footystats_configured:
        return DependencyStatus(
            name="footystats",
            status="not_configured",
            detail=(
                "No API key supplied. Mock performance data in use."
                if settings.app_mode.value == "demo"
                else "No API key supplied. Production performance data is unavailable."
            ),
        )
    return DependencyStatus(
        name="footystats",
        status="degraded",
        detail="API key present, but the provider field schema is not yet validated.",
    )


def _performance_source(settings: Settings) -> DataSourceStatus:
    """Describe the performance provider actually in use.

    Read from the provider itself rather than inferred from the mode, so the UI
    cannot claim a provider the backend did not manage to construct. When the
    registry refuses - production without a validated provider - that refusal
    is reported as-is instead of being smoothed over.
    """
    try:
        info = build_performance_provider(settings).info
    except AppError as exc:
        log.warning("performance_provider_unavailable", code=exc.code, message=exc.message)
        return DataSourceStatus(
            name="Performance data",
            kind="performance",
            provider="unavailable",
            is_mock=False,
            validated=False,
            notes=exc.message,
        )

    return DataSourceStatus(
        name="Performance data",
        kind="performance",
        provider=info.name,
        is_mock=info.is_mock,
        validated=info.validated,
        notes=info.notes,
    )


def _market_source(settings: Settings) -> DataSourceStatus:
    """Describe the market provider actually in use."""
    try:
        info = build_market_provider(settings).info
    except AppError as exc:
        log.warning("market_provider_unavailable", code=exc.code, message=exc.message)
        return DataSourceStatus(
            name="Market data",
            kind="market",
            provider="unavailable",
            is_mock=False,
            validated=False,
            notes=exc.message,
        )

    notes = info.notes
    if info.licence:
        notes = f"{notes} Licence: {info.licence}." if notes else f"Licence: {info.licence}."
    return DataSourceStatus(
        name="Market data",
        kind="market",
        provider=info.name,
        is_mock=info.is_mock,
        validated=info.validated,
        notes=notes,
    )


@router.get("/api/v1/meta", response_model=MetaResponse)
def meta(settings: SettingsDep) -> MetaResponse:
    """Application metadata for the frontend shell (mode banner, provenance)."""
    is_demo = settings.app_mode.value == "demo"

    data_sources = [
        _performance_source(settings),
        _market_source(settings),
    ]

    return MetaResponse(
        app_name=settings.app_name,
        app_mode=settings.app_mode.value,  # type: ignore[arg-type]
        version=APP_VERSION,
        demo_data_notice=DEMO_NOTICE if is_demo else None,
        data_sources=data_sources,
    )
