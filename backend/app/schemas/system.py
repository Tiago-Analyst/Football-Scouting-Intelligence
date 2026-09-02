"""Response models for system/meta endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "unavailable", "not_configured"]
    detail: str | None = Field(
        default=None,
        description="Short, non-sensitive explanation. Never contains driver or SQL detail.",
    )


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app_mode: Literal["demo", "production"]
    app_env: str
    version: str
    schema_revision: str | None = Field(
        default=None,
        description="Alembic revision applied to the database; null if unmigrated.",
    )
    dependencies: list[DependencyStatus]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class DataSourceStatus(BaseModel):
    """What the UI needs in order to label data provenance honestly."""

    name: str
    kind: Literal["performance", "market"]
    provider: str = Field(description="Concrete provider implementation currently in use.")
    is_mock: bool = Field(description="True when the values shown are fabricated demo data.")
    validated: bool = Field(
        description=(
            "True only once the provider's real field schema has been profiled "
            "and mapped. False means dependent features are intentionally disabled."
        )
    )
    notes: str | None = None


class SourceLoadOut(BaseModel):
    """When one source's data was last loaded.

    Keyed by the loader's own source name rather than by a provider class, so
    nothing has to be inferred: this is a record of what was written, under the
    name it was written as.

    Reported per source and never summed into one date. The performance and
    market pipelines run on different schedules, so a single "updated today"
    would be wrong whenever one refreshed and the other did not - which is the
    normal case, not the exception.
    """

    source: str
    last_loaded_at: datetime
    rows_loaded: int


class MetaResponse(BaseModel):
    """Public application metadata, consumed by the frontend shell."""

    app_name: str
    app_mode: Literal["demo", "production"]
    version: str
    demo_data_notice: str | None = Field(
        default=None,
        description="Populated in demo mode so the UI can display a persistent banner.",
    )
    data_sources: list[DataSourceStatus]
    #: Empty when nothing has been loaded since load times began to be
    #: recorded, or when the database could not be reached. Absent rather
    #: than guessed from when the checks last ran, which is a different
    #: fact and would read as a fresher claim than the data supports.
    data_freshness: list[SourceLoadOut] = Field(default_factory=list)
    #: Whether this caller's build token was accepted.
    #:
    #: Asked by the deploy before it commits to rendering every profile ahead
    #: of time. Without the exemption that is thousands of requests against a
    #: limit of 120 a minute, and the build fails partway through with a 429 -
    #: an unhelpful way to discover that a token is set on one side and not the
    #: other. False for everybody else, which tells them nothing they could not
    #: work out by making a request.
    build_access: bool = False


class ReloadAnalyticsResponse(BaseModel):
    """What a pipeline learns from asking the API to reload.

    `changed` is the useful one: it separates "the load reached the API" from
    "the load changed nothing", which look identical from the outside and mean
    very different things about the run that just finished.
    """

    changed: bool
    players: int
    competitions: int
    build_seconds: float
    #: Always false immediately after a reload. Returned so a caller can assert
    #: on it rather than infer it.
    is_stale: bool = False
