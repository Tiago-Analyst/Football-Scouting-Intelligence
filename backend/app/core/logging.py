"""Structured logging.

Console renderer for local development, JSON for anything deployed, so logs
are greppable by a log aggregator without a parsing layer. A request id is
bound per request (see app.core.middleware) and appears on every line emitted
while handling that request.

structlog renders each event to a string and hands it to the standard library,
which owns the actual sink. That keeps uvicorn's own records and application
events flowing through one handler, and it is what makes
`structlog.stdlib.add_logger_name` valid - it needs a stdlib logger to read the
name from.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings

# Keys that must never reach a log sink, whatever a caller passes in.
_REDACTED_KEYS = frozenset(
    {
        "footystats_api_key",
        "api_key",
        "apikey",
        "key",
        "password",
        "postgres_password",
        "secret",
        "token",
        "authorization",
        "cookie",
    }
)
_REDACTED = "***redacted***"


def _redact_secrets(
    _logger: Any, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Scrub credential-shaped keys from every event.

    Defence in depth: settings already wrap secrets in SecretStr, but a stray
    log.info("x", api_key=...) anywhere in the codebase must not leak.
    """
    for key in list(event_dict):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Install the structlog pipeline and route it through stdlib logging."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    use_json = settings.log_format.lower() == "json"

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_secrets,
    ]

    renderer: structlog.types.Processor
    if use_json:
        # JSONRenderer cannot serialise a raw exc_info tuple; flatten it first.
        processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        # ConsoleRenderer formats exc_info itself, so it must NOT be flattened.
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # structlog has already rendered the full line, so the stdlib formatter must
    # emit the message verbatim and add nothing of its own.
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # SQLAlchemy emits full statements at INFO. Statements can embed values, so
    # this stays off unless explicitly debugging outside production.
    sql_level = logging.INFO if (settings.debug and not settings.is_production) else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)
    # Replaced by RequestContextMiddleware, which also carries the request id.
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
