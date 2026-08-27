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

from app.models import DimClub, DimCompetition, DimPlayer, FactDataQuality, FactPlayerSeasonStats


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
    return [
        SourceFreshness(
            source=source,
            last_checked_at=latest,
            age_days=max((now - latest).days, 0),
            checks_run=int(checks_run),
            failures=int(failures),
            warnings=int(warnings),
        )
        for source, latest, checks_run, failures, warnings in rows
    ]


def volumes(session: Session) -> Volumes:
    """What is actually loaded. Cheap counts, safe to serve on a request."""
    return Volumes(
        players=session.scalar(select(func.count()).select_from(DimPlayer)) or 0,
        competitions=session.scalar(select(func.count()).select_from(DimCompetition)) or 0,
        clubs=session.scalar(select(func.count()).select_from(DimClub)) or 0,
        player_seasons=session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0,
    )
