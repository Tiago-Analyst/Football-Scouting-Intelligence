"""Application settings.

Configuration is read from the environment, falling back to the repository-root
`.env` file during local development. Nothing here has a production-safe
default that could silently leak: secrets default to empty and are validated at
the point of use, not guessed.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core import paths

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo root
REPO_ROOT = paths.REPO_ROOT


class AppMode(StrEnum):
    """Where the application reads its football data from."""

    DEMO = "demo"
    PRODUCTION = "production"


class AppEnv(StrEnum):
    """Deployment environment. Governs how much detail errors may expose."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application ----------------------------------------------------------
    app_name: str = "Football Recruitment Intelligence"
    app_mode: AppMode = AppMode.DEMO
    app_env: AppEnv = AppEnv.DEVELOPMENT
    debug: bool = False

    # -- Database -------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "fri"
    postgres_user: str = "fri_app"
    postgres_password: SecretStr = SecretStr("")
    database_url: str | None = None

    # -- API ------------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    # NoDecode stops pydantic-settings JSON-decoding the raw env value, so the
    # `_split_origins` validator below receives the plain comma-separated string.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    rate_limit_per_minute: int = 120

    #: A shared secret that lifts the rate limit for the deploy that renders
    #: the site.
    #:
    #: The limit exists to stop anyone drawing the database out through the
    #: public API, and it should stay where it is for every public caller. The
    #: build is not one: it is our own infrastructure, it runs once per deploy,
    #: and rendering every profile ahead of time is precisely how readers stop
    #: waiting for this service to wake up.
    #:
    #: Unset means no caller can claim the exemption, which is the right
    #: default for any deployment that does not prerender.
    build_token: str | None = None

    #: A shared secret for the endpoints that change this service's state.
    #:
    #: Deliberately not `build_token`. That one only lifts a rate limit, grants
    #: no access a public caller lacks, and is handed to a build running on
    #: someone else's infrastructure. This one makes the API rebuild its
    #: analytical view, and the two should not be able to stand in for each
    #: other - a secret that leaks from a build log must not also be able to
    #: drive the service.
    #:
    #: Unset means the endpoints refuse everybody, including a caller offering
    #: an empty token, which is the right default anywhere nothing is meant to
    #: reach in.
    internal_token: str | None = None

    # -- FootyStats -----------------------------------------------------------
    # A real key has been used and the mapping validated against real responses;
    # see docs/footystats_provider_status.md. Never logged, never serialised
    # into a response - SecretStr guards accidental printing.
    footystats_api_key: SecretStr = SecretStr("")
    footystats_base_url: str = "https://api.football-data-api.com"

    # -- Transfermarkt --------------------------------------------------------
    transfermarkt_dataset_ref: str = "dcaribou/transfermarkt-datasets"

    # -- Logging --------------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = "console"

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept `a,b,c` from the environment as well as a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allow_origins")
    @classmethod
    def _reject_wildcard(cls, value: list[str]) -> list[str]:
        """A wildcard origin is incompatible with credentialed requests and
        would expose the API to any site. Fail loudly rather than degrade."""
        if "*" in value:
            raise ValueError("CORS_ALLOW_ORIGINS must list exact origins; '*' is not permitted.")
        return value

    @property
    def sqlalchemy_url(self) -> str:
        """Connection URL for SQLAlchemy, preferring an explicit DATABASE_URL.

        Managed providers hand out `postgresql://` or `postgres://` URLs; both
        are normalised onto the psycopg (v3) driver we actually depend on.
        """
        if self.database_url:
            url = self.database_url
            for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
                if url.startswith(prefix):
                    return url
            if url.startswith("postgres://"):
                return url.replace("postgres://", "postgresql+psycopg://", 1)
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url

        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def footystats_configured(self) -> bool:
        """True only when a non-empty FootyStats key is present.

        Callers must consult this instead of reading the key directly, so that
        "no key" is an explicit, testable state rather than an empty string that
        silently produces failing HTTP calls.
        """
        return bool(self.footystats_api_key.get_secret_value().strip())

    def safe_summary(self) -> dict[str, object]:
        """Non-sensitive settings, safe to log at startup or expose on /health."""
        return {
            "app_name": self.app_name,
            "app_mode": self.app_mode.value,
            "app_env": self.app_env.value,
            "debug": self.debug,
            "database": f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}",
            "footystats_configured": self.footystats_configured,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Tests clear the cache via `get_settings.cache_clear()`."""
    return Settings()
