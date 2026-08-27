"""Uniform error responses.

Every failure leaves the API in the same envelope shape, and unhandled
exceptions never leak a stack trace or a database message to the client.
The full detail goes to the structured log, keyed by request id, so an
operator can still find it.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


class AppError(Exception):
    """Base class for errors the application raises deliberately."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "app_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationError(AppError):
    status_code = 422  # name differs across Starlette versions
    code = "validation_error"


class ProviderNotConfiguredError(AppError):
    """A data provider was requested but its credentials are absent.

    Raised, for example, when production mode asks for FootyStats without a
    key. We fail loudly instead of silently substituting mock data - a silent
    fallback would put fabricated numbers in front of a recruitment decision.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "provider_not_configured"


class DataNotValidatedError(AppError):
    """A feature depends on provider fields that have not yet been verified.

    Used to keep FootyStats-dependent features switched off until the real API
    schema has been profiled, rather than shipping guessed field mappings.
    """

    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "data_not_validated"


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    """Attach handlers converting exceptions into the standard envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log.warning(
            "app_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic's raw errors can echo submitted values back; keep only the
        # field location and the rule that failed.
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])), "reason": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "Request validation failed", {"fields": details}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> Any:
        if isinstance(exc, HTTPException) or isinstance(exc.detail, str):
            return JSONResponse(
                status_code=exc.status_code,
                content=_envelope("http_error", str(exc.detail)),
                headers=getattr(exc, "headers", None),
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(SQLAlchemyError)
    async def _handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Database messages routinely contain table, column and constraint
        # names. Log them; never return them.
        log.error("database_error", error=str(exc), path=request.url.path, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=_envelope("database_unavailable", "A database error occurred."),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error=str(exc), path=request.url.path, exc_info=True)
        # Only a development environment may see the underlying message.
        message = (
            f"{type(exc).__name__}: {exc}"
            if not settings.is_production and settings.debug
            else "An internal error occurred."
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", message),
        )
