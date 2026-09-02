"""Read the data quality picture for the API.

Section 24 requires quality checks to be recorded rather than merely run, and
this is the half that makes the record useful: the site shows what was checked,
when, and what it found. A check nobody can see is barely better than a check
nobody ran.

The service reads. It never runs a check — `pipelines/quality/report.py` does
that, on a schedule or before a deployment. A web request that ran a full table
scan over every metric would be a denial-of-service waiting for a curious user.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    FactDataQuality,
    FactPlayerSeasonStats,
    FactSourceLoad,
)
from app.providers.registry import build_performance_provider
from app.schemas.canonical import CanonicalMetric


@dataclass(frozen=True)
class CheckRecord:
    source: str
    entity: str
    check_name: str
    status: str
    record_count: int
    detail: str | None
    executed_at: datetime


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    last_checked_at: datetime
    age_days: int
    checks_run: int
    failures: int
    warnings: int
    #: When this source's data was last loaded, which is not when it was last
    #: checked. `None` for a source loaded before the two were told apart.
    last_loaded_at: datetime | None = None
    data_age_days: int | None = None
    rows_loaded: int | None = None


@dataclass(frozen=True)
class Volumes:
    players: int
    competitions: int
    clubs: int
    player_seasons: int


def latest_checks(session: Session, *, limit: int = 200) -> list[CheckRecord]:
    """The most recent run's checks, per source.

    Only the newest run of each source: showing every historical run would bury
    the current state, which is the question a reader actually has.
    """
    newest = (
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at).label("latest"))
        .group_by(FactDataQuality.source)
        .subquery()
    )
    rows = session.execute(
        select(FactDataQuality)
        .join(
            newest,
            (FactDataQuality.source == newest.c.source)
            & (FactDataQuality.executed_at == newest.c.latest),
        )
        .order_by(FactDataQuality.source, FactDataQuality.entity, FactDataQuality.check_name)
        .limit(limit)
    ).scalars()

    return [
        CheckRecord(
            source=row.source,
            entity=row.entity,
            check_name=row.check_name,
            status=row.status,
            record_count=row.record_count,
            detail=row.detail,
            executed_at=row.executed_at,
        )
        for row in rows
    ]


def last_loads(session: Session) -> dict[str, tuple[datetime, int]]:
    """When each source's data was last loaded, and how many rows arrived.

    Deliberately separate from `freshness` below, which reports when checks
    last *ran*. Those are different facts and conflating them lets the site
    tell somebody the performance data was updated today because a check ran
    against a fortnight-old load.
    """
    newest = (
        select(FactSourceLoad.source, func.max(FactSourceLoad.loaded_at).label("latest"))
        .group_by(FactSourceLoad.source)
        .subquery()
    )
    rows = session.execute(
        select(FactSourceLoad.source, FactSourceLoad.loaded_at, FactSourceLoad.rows_loaded)
        .join(
            newest,
            (FactSourceLoad.source == newest.c.source)
            & (FactSourceLoad.loaded_at == newest.c.latest),
        )
        .order_by(FactSourceLoad.source)
    ).all()
    return {source: (loaded_at, int(rows_loaded)) for source, loaded_at, rows_loaded in rows}


def freshness(session: Session) -> list[SourceFreshness]:
    """When each source was last checked, and how that run went."""
    newest = (
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at).label("latest"))
        .group_by(FactDataQuality.source)
        .subquery()
    )
    rows = session.execute(
        select(
            FactDataQuality.source,
            newest.c.latest,
            func.count().label("checks_run"),
            func.count(1).filter(FactDataQuality.status == "fail").label("failures"),
            func.count(1).filter(FactDataQuality.status == "warn").label("warnings"),
        )
        .join(
            newest,
            (FactDataQuality.source == newest.c.source)
            & (FactDataQuality.executed_at == newest.c.latest),
        )
        .group_by(FactDataQuality.source, newest.c.latest)
        .order_by(FactDataQuality.source)
    ).all()

    now = datetime.now(UTC)
    loads = last_loads(session)

    def with_load(source: str, **fields: object) -> SourceFreshness:
        entry = loads.get(source)
        if entry is None:
            # Loaded before this was recorded, or never loaded. Absent rather
            # than guessed: the check time is not the load time, and filling
            # one in from the other is the mistake this exists to prevent.
            return SourceFreshness(source=source, **fields)  # type: ignore[arg-type]
        loaded_at, row_count = entry
        return SourceFreshness(
            source=source,
            last_loaded_at=loaded_at,
            data_age_days=max((now - loaded_at).days, 0),
            rows_loaded=row_count,
            **fields,  # type: ignore[arg-type]
        )

    return [
        with_load(
            source,
            last_checked_at=latest,
            age_days=max((now - latest).days, 0),
            checks_run=int(checks_run),
            failures=int(failures),
            warnings=int(warnings),
        )
        for source, latest, checks_run, failures, warnings in rows
    ]


@dataclass(frozen=True)
class IdentityCoverage:
    """How much of the two sources has been reconciled into one identity.

    `unmatched` is not a failure. A FootyStats player with no Transfermarkt
    counterpart is a player we know less about, and the honest thing is to
    count them rather than let the total imply a completeness nobody achieved.
    """

    players: int
    matched: int
    unmatched: int
    manual_overrides: int
    #: Matched below this confidence, so the link is plausible rather than
    #: settled. Worth surfacing because these are where a wrong join would be.
    ambiguous: int

    @property
    def matched_share(self) -> float:
        return self.matched / self.players if self.players else 0.0


#: Below this a match was accepted on weaker evidence and is worth reviewing.
AMBIGUOUS_CONFIDENCE = 0.90


def identity_coverage(session: Session) -> IdentityCoverage:
    """Players carrying links from more than one source, and how firm they are."""
    players = session.scalar(select(func.count()).select_from(DimPlayer)) or 0

    per_player = (
        select(
            BridgePlayerSource.player_id,
            func.count(func.distinct(BridgePlayerSource.source)).label("sources"),
            func.min(BridgePlayerSource.match_confidence).label("weakest"),
            func.bool_or(BridgePlayerSource.manual_override).label("manual"),
        )
        .group_by(BridgePlayerSource.player_id)
        .subquery()
    )

    matched = (
        session.scalar(select(func.count()).select_from(per_player).where(per_player.c.sources > 1))
        or 0
    )
    ambiguous = (
        session.scalar(
            select(func.count())
            .select_from(per_player)
            .where(per_player.c.sources > 1, per_player.c.weakest < AMBIGUOUS_CONFIDENCE)
        )
        or 0
    )
    manual = (
        session.scalar(
            select(func.count()).select_from(per_player).where(per_player.c.manual.is_(True))
        )
        or 0
    )

    return IdentityCoverage(
        players=players,
        matched=matched,
        unmatched=max(players - matched, 0),
        manual_overrides=manual,
        ambiguous=ambiguous,
    )


def average_detailed_coverage(session: Session) -> float | None:
    """Mean share of played minutes that carry detailed statistics.

    `None` when nothing can be measured, which is different from nought.
    Rows without a recorded figure are excluded rather than counted as zero
    coverage: the provider not telling us is not the same as it telling us
    nothing was recorded.
    """
    value = session.scalar(
        select(
            func.avg(
                100.0
                * FactPlayerSeasonStats.recorded_minutes
                / func.nullif(FactPlayerSeasonStats.minutes, 0)
            )
        ).where(
            FactPlayerSeasonStats.recorded_minutes.is_not(None),
            FactPlayerSeasonStats.minutes.is_not(None),
            FactPlayerSeasonStats.minutes > 0,
        )
    )
    return float(value) if value is not None else None


def unavailable_metrics(settings: Settings) -> list[str]:
    """Canonical metrics the configured provider cannot supply.

    Asked of the provider rather than read off the mapping file. A first
    attempt compared against the mapping's `metrics` block and reported
    `non_penalty_goals` and `penalties_taken` as unavailable - both are
    derived from fields that are supplied, and both appear on the site. The
    provider is the thing that knows what it can produce.

    A statement about the provider, not about a particular load: a metric can
    be thin in one refresh for ordinary reasons, while this is what is
    permanently out of reach.
    """
    try:
        available = build_performance_provider(settings).info.available_metrics
    except AppError:
        # No provider configured. Saying every metric is unavailable would be
        # true and useless; saying nothing is the honest shape of "unknown".
        return []
    return sorted(metric.value for metric in CanonicalMetric if metric not in available)


def volumes(session: Session) -> Volumes:
    """What is actually loaded. Cheap counts, safe to serve on a request."""
    return Volumes(
        players=session.scalar(select(func.count()).select_from(DimPlayer)) or 0,
        competitions=session.scalar(select(func.count()).select_from(DimCompetition)) or 0,
        clubs=session.scalar(select(func.count()).select_from(DimClub)) or 0,
        player_seasons=session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0,
    )
