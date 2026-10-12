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
from app.schemas.api import Message
from app.schemas.system import (
    DataSourceStatus,
    DependencyStatus,
    HealthResponse,
    LivenessResponse,
    MetaResponse,
    MetricCensusOut,
    SourcePublicationOut,
)
from app.services.analytics_service import get_analytics_view, view_is_stale
from app.services.quality_service import last_publications, market_serving

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
    mapping = get_mapping()
    census = mapping.census()
    verified = len(mapping.available_metrics)
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
            # Counted from the census, like every other public statement about
            # these numbers. Four pages each did their own arithmetic on this
            # mapping and three reached different answers.
            f"{census.usable} of {census.total} canonical metrics usable: "
            f"{census.native} supplied as fields, {census.derived} derived from fields "
            f"that are, {census.unavailable} unavailable. Verified against real "
            "responses; not contacted by this check."
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
    """Describe the market data the product is serving.

    THE QUESTION THIS ANSWERS
    -------------------------

    "Is the market data currently serving the product available and valid?" -
    not "is an ingestion snapshot sitting on this machine's disk".

    It used to answer the second. `build_market_provider` opens the downloaded
    Transfermarkt dataset, which is an ingestion precondition: the download
    happens in a pipeline, the API runs elsewhere, and on the serving host that
    file is absent by design. So production served a market value, a valuation
    history and a transfer list on every profile, ran the Opportunities market
    filters, and showed Transfermarkt on the Data Quality page as a serving
    source with rows and passing checks - while System Status called market
    data unavailable and told the reader to run a download command.

    Nothing was broken. The page was asking a question nobody reading it was
    asking. It now counts the rows the pages are built from, and falls back to
    the provider only to explain an absence it has established for itself.
    """
    if settings.app_mode.value == "demo":
        # Demo serves fabricated market data. Counting its rows would be
        # counting an invention, and the provider already says so.
        serving = None
    else:
        try:
            with get_session_factory()() as session:
                serving = market_serving(session)
        except Exception as exc:  # pragma: no cover - the health check reports this
            log.warning("market_serving_unknown", error=type(exc).__name__)
            serving = None

    if serving is not None and serving.available:
        return DataSourceStatus(
            name="Market data",
            kind="market",
            provider="Transfermarkt (serving database)",
            is_mock=False,
            validated=True,
            notes=(
                f"Serving {serving.players_with_value} current valuations, "
                f"{serving.valuations} historical valuations and {serving.transfers} "
                f"transfers; {serving.players_with_contract} players carry a contract "
                "expiry. Counted from the database behind the pages, not from an "
                "ingestion snapshot."
            ),
        )

    try:
        info = build_market_provider(settings).info
    except AppError as exc:
        log.warning("market_provider_unavailable", code=exc.code, message=exc.message)
        detail = (
            "No market data is being served, and no snapshot is available to load one. "
            if serving is not None
            else ""
        )
        return DataSourceStatus(
            name="Market data",
            kind="market",
            provider="unavailable",
            is_mock=False,
            validated=False,
            notes=f"{detail}{exc.message}",
        )

    notes = info.notes
    if serving is not None:
        notes = (
            "A snapshot is readable but no market rows are being served: the pages that "
            f"need them will be empty. {notes}"
            if notes
            else "A snapshot is readable but no market rows are being served."
        )
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


def _data_freshness() -> list[SourcePublicationOut]:
    """When each source was last published, for the shell to show unobtrusively.

    PUBLISHED, NOT LOADED
    ---------------------

    This is the line on every page of the site - "Performance data updated 8
    Sep" - which makes it the most-read freshness claim there is, and it was
    reading the load ledger.

    Loads write to `analytics_staging` now. A refresh that loads at 10:00 and
    fails identity resolution at 10:20 leaves production serving yesterday,
    with a load row stamped 10:00 that this line would have turned into a
    promise about the figures on screen.

    Never inferred from when the checks last ran either: that is a third fact,
    and a check against a fortnight-old dataset happens routinely. A source
    with no recorded publication is simply absent, because a missing line is a
    smaller lie than an invented date.

    A database that cannot be reached returns nothing rather than failing the
    endpoint. This is a footer line; the health check is where an unreachable
    database is supposed to be reported.
    """
    try:
        with get_session_factory()() as session:
            return [
                SourcePublicationOut(
                    source=source, last_published_at=published_at, rows_published=rows
                )
                for source, (published_at, rows) in sorted(last_publications(session).items())
            ]
    except Exception as exc:
        log.warning("data_freshness_unavailable", error=type(exc).__name__)
        return []


def _metric_census() -> MetricCensusOut | None:
    """The counts every public page reads instead of writing its own.

    Null rather than zeroes when no mapping has been verified: a page that
    cannot tell "not profiled yet" from "39 metrics and none of them supplied"
    will eventually publish the second while the first is true.
    """
    mapping = get_mapping()
    if mapping.is_empty:
        return None
    census = mapping.census()
    return MetricCensusOut(
        total=census.total,
        native=census.native,
        derived=census.derived,
        unavailable=census.unavailable,
        usable=census.usable,
        rejected_provider_fields=census.rejected_provider_fields,
    )


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
        demo_data_notice_message=(Message(code="demo_mode") if is_demo else None),
        data_sources=data_sources,
        metric_census=_metric_census(),
        data_freshness=_data_freshness(),
        build_access=has_build_access(request, settings.build_token),
    )
