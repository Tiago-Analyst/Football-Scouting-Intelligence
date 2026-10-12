"""Response models for system/meta endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.api import Message


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "unavailable", "not_configured"]
    detail: str | None = Field(
        default=None,
        description="Short, non-sensitive explanation. Never contains driver or SQL detail.",
    )
    #: The same diagnostic as a code, so a page can say it in either
    #: language. `detail` stays, in English, for a caller reading it -
    #: and for the one case nothing here wrote: a driver's own refusal.
    detail_message: Message | None = None


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
    #: The same note as a code, so a page can say it in either language.
    #:
    #: `notes` stays, in English, for a caller already reading it.
    notes_message: Message | None = None
    #: The licence, where the source states one. Said separately because
    #: it is appended to several different notes.
    licence: str | None = None


class SourcePublicationOut(BaseModel):
    """When one source's data was last published.

    Keyed by the loader's own source name rather than by a provider class, so
    nothing has to be inferred: this is a record of what was published, under
    the name it was published as.

    Reported per source and never summed into one date. The performance and
    market pipelines run on different schedules, so a single "updated today"
    would be wrong whenever one refreshed and the other did not - which is the
    normal case, not the exception.
    """

    source: str
    #: When this source's data was **published** - the moment what a reader is
    #: looking at became these figures. Not when a load ran: loads write to
    #: `analytics_staging`, and a staging load that fails its checks never
    #: reaches production, so reporting one here would put a date on the footer
    #: that the served data does not have.
    last_published_at: datetime
    rows_published: int


class MetricCensusOut(BaseModel):
    """How many canonical metrics there are, and what became of each.

    Four public pages each stated these counts in their own prose and three of
    the four were wrong, in different directions: thirty-four mapped against
    thirty-six, five unsupplied against three. Every number came from the same
    mapping; the categories had been conflated.

    They are now read from here. `native + derived + unavailable == total`,
    and `rejected_provider_fields` is deliberately outside that sum because it
    counts provider fields, not canonical metrics.
    """

    total: int
    native: int
    derived: int
    unavailable: int
    usable: int
    rejected_provider_fields: int


class MetaResponse(BaseModel):
    """Public application metadata, consumed by the frontend shell."""

    app_name: str
    app_mode: Literal["demo", "production"]
    version: str
    demo_data_notice: str | None = Field(
        default=None,
        description="Populated in demo mode so the UI can display a persistent banner.",
    )
    #: The same notice as a code, for an interface with a language of its own.
    #:
    #: Additive: the English sentence above is unchanged and still correct.
    demo_data_notice_message: Message | None = None
    data_sources: list[DataSourceStatus]
    #: The one place public copy may read metric counts from. Null when no
    #: provider mapping has been verified, which is a real state and not a
    #: zero: "nothing profiled yet" and "39 metrics, none supplied" are
    #: different facts and a page must be able to tell them apart.
    metric_census: MetricCensusOut | None = None
    #: Empty when nothing has been loaded since load times began to be
    #: recorded, or when the database could not be reached. Absent rather
    #: than guessed from when the checks last ran, which is a different
    #: fact and would read as a fresher claim than the data supports.
    data_freshness: list[SourcePublicationOut] = Field(default_factory=list)
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
