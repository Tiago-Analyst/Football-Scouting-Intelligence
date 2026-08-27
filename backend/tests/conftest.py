"""Shared test fixtures.

Settings are built explicitly with `_env_file=None` so tests never depend on
whatever happens to be in the developer's local `.env`, and are injected
through `app.dependency_overrides` rather than by patching module internals.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


def build_settings(**overrides: Any) -> Settings:
    """Construct isolated Settings, ignoring the on-disk .env file."""
    defaults: dict[str, Any] = {
        "app_mode": "demo",
        "app_env": "development",
        "debug": False,
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_db": "fri",
        "postgres_user": "fri_app",
        "postgres_password": "test_password",
        "cors_allow_origins": ["http://localhost:3000"],
        "rate_limit_per_minute": 120,
        "footystats_api_key": "",
        "log_format": "console",
        "log_level": "WARNING",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


def build_client(settings: Settings) -> TestClient:
    """App + client wired to the supplied settings."""
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def settings() -> Settings:
    return build_settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with build_client(settings) as test_client:
        yield test_client
