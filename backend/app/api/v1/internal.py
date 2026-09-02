"""Endpoints that change this service's state, for our own pipeline.

There is exactly one at present, and it closes a real gap: a successful load
put new rows in PostgreSQL and the running API went on serving the analytical
view it had built at start-up. `view_is_stale()` could already tell you the two
disagreed, and `refresh_analytics_view()` could already fix it, but nothing
connected them - so new data reached the database and stopped there until
somebody happened to restart the service.

WHY A SEPARATE SECRET
---------------------

`build_token` lifts a rate limit and grants no access a public caller does not
already have; it is handed to a build running on someone else's infrastructure
and appears in that build's environment. This endpoint makes the service throw
away its analytical view and rebuild it, which is a different kind of
permission. A secret that leaks from a build log must not also be able to drive
the service, so the two cannot stand in for each other.

Unset means refuse everybody. A deployment that nothing is meant to reach into
is the common case, and it should not depend on nobody guessing.

WHAT THIS IS NOT
----------------

It is not a cache purge for the public. There is no unauthenticated path to any
of it, the router carries no read endpoints, and a wrong token is refused
before any work is done.
"""

from __future__ import annotations

import secrets
import time

import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import SettingsDep
from app.core.config import Settings
from app.schemas.system import ReloadAnalyticsResponse
from app.services.analytics_service import get_analytics_view, refresh_analytics_view

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])

log = structlog.get_logger(__name__)

#: Header the pipeline identifies itself with.
INTERNAL_TOKEN_HEADER = "x-internal-token"  # noqa: S105 - a header name, not a secret


def require_internal(request: Request, settings: Settings) -> None:
    """Refuse anyone who is not our own pipeline.

    Constant-time comparison, and only when a token is configured: an unset
    secret must not be satisfiable by an absent or empty header, which is the
    shape of this mistake that actually happens.
    """
    configured = settings.internal_token
    if not configured:
        # 404 rather than 401. A deployment with no internal token has no such
        # endpoint as far as anyone outside is concerned, and saying "wrong
        # credentials" would confirm the route exists and is worth guessing at.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    offered = request.headers.get(INTERNAL_TOKEN_HEADER)
    if not offered or not secrets.compare_digest(offered, configured):
        log.warning(
            "internal_auth_rejected",
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token"
        )


@router.post("/reload-analytics", response_model=ReloadAnalyticsResponse)
def reload_analytics(request: Request, settings: SettingsDep) -> ReloadAnalyticsResponse:
    """Rebuild the analytical view from what is now in the database.

    Called by the pipeline after a load has been verified, which is the only
    moment it should be: rebuilding on a timer would make the site briefly
    disagree with itself for reasons nobody could see, and rebuilding on every
    request would cost seconds per page.

    Idempotent, and honest about doing nothing. Calling it when the database
    has not moved still rebuilds - that is cheap and unsurprising - and the
    response says whether the fingerprint actually changed, so a pipeline can
    tell "the load reached the API" from "the load changed nothing".
    """
    require_internal(request, settings)

    before = get_analytics_view()
    previous = before.fingerprint

    started = time.perf_counter()
    view = refresh_analytics_view()
    elapsed = time.perf_counter() - started

    changed = view.fingerprint != previous
    log.info(
        "analytics_view_reloaded",
        changed=changed,
        players=len(view.players),
        competitions=len(view.competitions),
        seconds=round(elapsed, 2),
    )

    return ReloadAnalyticsResponse(
        changed=changed,
        players=len(view.players),
        competitions=len(view.competitions),
        build_seconds=round(elapsed, 2),
        is_stale=False,
    )
