"""HTTP middleware: request correlation, access logging, rate limiting, headers."""

from __future__ import annotations

import secrets
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]

#: Header the deploy identifies itself with. Not a credential for anything else
#: - it lifts a rate limit and grants no access that a public caller lacks.
BUILD_TOKEN_HEADER = "x-build-token"  # noqa: S105 - a header name, not a secret


def has_build_access(request: Request, build_token: str | None) -> bool:
    """Whether this request is our own deploy rendering the site.

    The rate limit protects the database from being drawn out through the
    public API, and the build is not the public: it runs once per deploy, from
    our own pipeline, to render pages readers then get without waking this
    service at all.

    Compared in constant time, and only when a token is configured - so a
    deployment that sets none cannot have the exemption claimed against it by
    an empty or absent header.

    Lives here rather than on the middleware because `/api/v1/meta` reports the
    answer, so a deploy can find out whether prerendering is possible before it
    starts rather than by failing partway through.
    """
    if not build_token:
        return False
    offered = request.headers.get(BUILD_TOKEN_HEADER)
    if not offered:
        return False
    return secrets.compare_digest(offered, build_token)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, bind it to the log context, and time the request."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["x-request-id"] = request_id
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Conservative security headers for a JSON API."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        super().__init__(app)
        # HSTS only in production. On a development machine it would pin
        # localhost to https for six months in the developer's browser, which
        # is remarkably annoying to undo and affects every project they run on
        # that port.
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window-free sliding rate limit, per client IP.

    LIMITATION: state is in-process, so the effective limit multiplies by the
    number of worker processes and resets on deploy. That is acceptable as a
    basic abuse brake; a shared Redis counter is required before this can be
    treated as a real quota across multiple instances.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int,
        build_token: str | None = None,
    ) -> None:
        super().__init__(app)
        self.limit = requests_per_minute
        self.window_seconds = 60.0
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self.build_token = build_token or None

    def _client_key(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _is_build(self, request: Request) -> bool:
        return has_build_access(request, self.build_token)

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        # Health and docs must stay reachable for probes even under limiting.
        if request.url.path in {"/health", "/health/live", "/docs", "/openapi.json"}:
            return await call_next(request)

        if self._is_build(request):
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - hits[0])))
            log.warning("rate_limited", client=key, path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please retry shortly.",
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Install middleware.

    Starlette runs middleware in reverse registration order, so the last one
    added is outermost. Request context is registered last and therefore wraps
    everything, giving every log line - including rate-limit rejections - a
    request id.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_per_minute,
        build_token=settings.build_token,
    )
    app.add_middleware(RequestContextMiddleware)
