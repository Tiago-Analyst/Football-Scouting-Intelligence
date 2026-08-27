"""Logging pipeline.

Regression cover for a bug where the structlog processor chain was paired with
an incompatible logger factory, so every log call raised AttributeError. At the
default INFO level that crashed the request-logging middleware on every
request, surfacing as an empty HTTP 500.
"""

from __future__ import annotations

import json

import pytest

from app.core.logging import configure_logging, get_logger
from tests.conftest import build_client, build_settings


@pytest.mark.parametrize("log_format", ["console", "json"])
@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING"])
class TestEmitting:
    def test_every_level_emits_without_raising(
        self, log_format: str, level: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(build_settings(log_format=log_format, log_level=level))
        log = get_logger("test.logger")

        log.debug("debug_event", value=1)
        log.info("info_event", value=2)
        log.warning("warning_event", value=3)
        log.error("error_event", value=4)

        assert "error_event" in capsys.readouterr().out

    def test_exc_info_renders_without_raising(
        self, log_format: str, level: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """JSON and console renderers need exc_info handled differently."""
        configure_logging(build_settings(log_format=log_format, log_level=level))
        log = get_logger("test.logger")

        try:
            raise ValueError("boom")
        except ValueError:
            log.error("failed", exc_info=True)

        out = capsys.readouterr().out
        assert "failed" in out
        assert "ValueError" in out


class TestRedaction:
    @pytest.mark.parametrize(
        "field", ["api_key", "footystats_api_key", "password", "token", "authorization"]
    )
    def test_credential_shaped_keys_are_scrubbed(
        self, field: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging(build_settings(log_format="json", log_level="INFO"))
        get_logger("test.logger").info("call", **{field: "SUPER_SECRET_VALUE"})

        out = capsys.readouterr().out
        assert "SUPER_SECRET_VALUE" not in out
        assert json.loads(out.strip().splitlines()[-1])[field] == "***redacted***"

    def test_ordinary_fields_are_untouched(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(build_settings(log_format="json", log_level="INFO"))
        get_logger("test.logger").info("call", player_id=42, competition="Liga Portugal")

        record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert record["player_id"] == 42
        assert record["competition"] == "Liga Portugal"


class TestRequestLoggingUnderInfoLevel:
    """The original failure only appeared once request logging was reached."""

    @pytest.mark.parametrize("log_format", ["console", "json"])
    def test_requests_succeed_when_access_logging_is_active(self, log_format: str) -> None:
        settings = build_settings(log_level="INFO", log_format=log_format)
        with build_client(settings) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/api/v1/meta").status_code == 200

    def test_rate_limit_rejection_logs_and_still_returns_429(self) -> None:
        settings = build_settings(log_level="INFO", rate_limit_per_minute=1)
        with build_client(settings) as client:
            client.get("/api/v1/meta")
            assert client.get("/api/v1/meta").status_code == 429
