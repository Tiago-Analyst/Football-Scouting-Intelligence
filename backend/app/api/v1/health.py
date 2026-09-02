"""Health and metadata endpoints.

`/health/live` answers only "is the process up" and never touches the
database, so a database outage does not cause an orchestrator to kill an
otherwise healthy container. `/health` is the readiness check.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import SettingsDep
from app.core.config import Settings
from app.core.database import (
    check_database_connection,
    get_schema_revision,
    get_session_factory,
)
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.middleware import has_build_access
from app.providers.footystats_mapping import get_mapping
from app.providers.registry import build_market_provider, build_performance_provider
from app.schemas.system import (
    DataSourceStatus,
    DependencyStatus,
    HealthResponse,
    LivenessResponse,
    MetaResponse,
    SourceLoadOut,
)
from app.services.analytics_service import get_analytics_view, view_is_stale
from app.services.quality_service import last_loads

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
        _analytics_status(),
        _footystats_status(settings),
    ]

    # Only the dependencies the product cannot serve without decide the overall
    # verdict. FootyStats is deliberately excluded: an absent key is the expected
    # state in demo mode, and letting it turn the whole service red would train
    # anyone watching to ignore a red service.
    #
    # `analytics` is included, and that is the point of this list existing. An
    # empty database used to report "ok" while search, profiles and every ranking
    # had nothing to return.
    required = {"postgresql", "analytics"}
    blocking = [d for d in dependencies if d.name in required and d.status != "ok"]
    overall = "ok" if not blocking else "degraded"
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
    # A key is necessary and not sufficient. How many fields have actually been
    # verified against a real response is read from the mapping file, so this
    # answer changes when the profiling pipeline runs rather than when someone
    # remembers to edit this string.
    verified = len(get_mapping().available_metrics)
    if verified == 0:
        return DependencyStatus(
            name="footystats",
            status="degraded",
            detail=(
                "API key present, but no field has been verified against a real "
                "API response. Run the profiling pipeline."
            ),
        )
    # Reported without calling FootyStats. A health check that spent a request
    # on every probe would burn a rate limit measured in requests per hour, and
    # the ingest is what actually exercises the API.
    return DependencyStatus(
        name="footystats",
        status="ok",
        detail=(
            f"{verified} metric(s) mapped and verified against real responses. "
            "Not contacted by this check."
        ),
    )


def _analytics_status() -> DependencyStatus:
    """What the site is actually serving, and whether it is current.

    The view is assembled from the database once per process. A load that runs
    while the API is up therefore does not reach it, and the honest thing is to
    say so here rather than to serve last week's figures under this week's
    freshness badge.
    """
    try:
        view = get_analytics_view()
    except AppError as exc:
        return DependencyStatus(name="analytics", status="unavailable", detail=exc.message)

    if view.is_empty:
        return DependencyStatus(
            name="analytics",
            status="unavailable",
            detail=(
                "No player data is loaded. Run the ingestion pipeline; until then "
                "search, profiles and rankings have nothing to serve."
            ),
        )

    excluded = (
        f" {view.players_without_position} excluded for having no position group."
        if view.players_without_position
        else ""
    )

    try:
        stale = view_is_stale()
    except AppError:
        stale = False

    if stale:
        return DependencyStatus(
            name="analytics",
            status="degraded",
            detail=(
                f"Serving {len(view.players)} player-seasons built at "
                f"{view.built_at.isoformat(timespec='seconds')}. The database has been "
                "loaded since; restart the API to serve the new data."
            ),
        )

    return DependencyStatus(
        name="analytics",
        status="ok",
        detail=(
            f"{len(view.players)} player-seasons across {len(view.competitions)} "
            f"competitions, built at {view.built_at.isoformat(timespec='seconds')}.{excluded}"
        ),
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


def _data_freshness() -> list[SourceLoadOut]:
    """When each source was last loaded, for the shell to show unobtrusively.

    Never inferred from when the checks last ran: that is a different fact, and
    a check against a fortnight-old load happens routinely. A source with no
    recorded load is simply absent.

    A database that cannot be reached returns nothing rather than failing the
    endpoint. This is a footer line; the health check is where an unreachable
    database is supposed to be reported.
    """
    try:
        with get_session_factory()() as session:
            return [
                SourceLoadOut(source=source, last_loaded_at=loaded_at, rows_loaded=rows)
                for source, (loaded_at, rows) in sorted(last_loads(session).items())
            ]
    except Exception as exc:
        log.warning("data_freshness_unavailable", error=type(exc).__name__)
        return []


@router.get("/api/v1/meta", response_model=MetaResponse)
def meta(settings: SettingsDep, request: Request) -> MetaResponse:
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
        data_freshness=_data_freshness(),
        build_access=has_build_access(request, settings.build_token),
    )
