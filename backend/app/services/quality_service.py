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

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactRefreshGeneration,
    FactSourceLoad,
    FactSourcePublication,
    FactTransfer,
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
    #: Which refresh generation the check describes, and whether that
    #: generation was a candidate in staging or is the dataset being served.
    #: Both None for rows written before contexts existed.
    refresh_id: str | None = None
    generation_id: str | None = None
    context: str | None = None


@dataclass(frozen=True)
class CandidateChecks:
    """The newest checks that describe a refresh nobody is being served.

    Kept apart from the published checks on purpose. Production serving G4
    while a G5 candidate was checked and then failed at promotion used to put
    G5's checks on the public page above G4's data - every tick describing a
    dataset the reader could not see.

    Keyed by refresh rather than generation: Transfermarkt has no generation
    and its staging checks are candidates all the same.
    """

    source: str
    refresh_id: str
    generation_id: str | None
    executed_at: datetime
    checks: list[CheckRecord]


@dataclass(frozen=True)
class PublishedChecks:
    """The checks that validated the dataset this source is serving."""

    source: str
    refresh_id: str | None
    generation_id: str | None
    published_at: datetime | None
    executed_at: datetime | None
    checks: list[CheckRecord]


@dataclass(frozen=True)
class ProviderQuality:
    """One source, two datasets: what is serving and what is waiting.

    The shape `/data-quality` renders. `published` is about the data on
    screen; `candidate` is about a refresh between staging and production, or
    one that failed to reach it, and is None when nothing is waiting.
    """

    source: str
    published: PublishedChecks | None
    candidate: CandidateChecks | None


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    last_checked_at: datetime
    age_days: int
    checks_run: int
    failures: int
    warnings: int
    #: When this source's data was last *published* - the moment the dataset a
    #: reader is looking at became the one being served. Not when a load ran:
    #: loads write to staging and many of them never reach production.
    #: `None` for a source published before publications were recorded.
    last_published_at: datetime | None = None
    data_age_days: int | None = None
    rows_published: int | None = None
    #: When this source was last loaded into staging, published or not. Kept
    #: separate so an operator can see a refresh stuck between the two without
    #: it being reported to readers as fresh data.
    last_load_attempt_at: datetime | None = None


@dataclass(frozen=True)
class Volumes:
    players: int
    competitions: int
    clubs: int
    player_seasons: int


#: Rows that describe the dataset being served: flipped to PUBLISHED by a
#: promotion, or written before contexts existed and therefore about whatever
#: was serving at the time. CANDIDATE rows are excluded - they describe a
#: staging generation, and the whole point of the column is that a reader
#: must not take them for the data on screen.
_DESCRIBES_SERVING = (FactDataQuality.context.is_(None)) | (FactDataQuality.context == "PUBLISHED")


def _record(row: FactDataQuality) -> CheckRecord:
    return CheckRecord(
        source=row.source,
        entity=row.entity,
        check_name=row.check_name,
        status=row.status,
        record_count=row.record_count,
        detail=row.detail,
        executed_at=row.executed_at,
        refresh_id=row.refresh_id,
        generation_id=row.generation_id,
        context=row.context,
    )


def latest_checks(session: Session, *, limit: int = 200) -> list[CheckRecord]:
    """The most recent run's checks per source, about the dataset being served.

    Only the newest run of each source: showing every historical run would bury
    the current state, which is the question a reader actually has.

    Never a CANDIDATE run. Those describe a staging generation that may never
    reach readers; `candidate_checks` reports them, separately and labelled.
    """
    newest = (
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at).label("latest"))
        .where(_DESCRIBES_SERVING)
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
        .where(_DESCRIBES_SERVING)
        .order_by(FactDataQuality.source, FactDataQuality.entity, FactDataQuality.check_name)
        .limit(limit)
    ).scalars()
    return [_record(row) for row in rows]


def candidate_checks(session: Session, *, limit: int = 200) -> list[CandidateChecks]:
    """The newest CANDIDATE run per source that is genuinely still waiting.

    "Still waiting" has two conditions, and the first was missing:

    - newer than the source's latest publication. R2 checked at 10:00 and
      stuck; R3 checked at 11:00 and published at 12:00. R2's rows stay
      CANDIDATE forever - they are history, and history is not deleted - but
      after R3's promotion the newest CANDIDATE row for the source is R2
      again, and the page announced "latest candidate refresh: R2" about a
      refresh older than what it was serving.
    - for a FootyStats refresh, its generation is not FAILED or PUBLISHED.
      An abandoned G5's checks stay for audit; they are not a candidate.

    A refresh between staging and production, or one that failed to get
    there *since the last publication*, is what this returns. Nothing older.
    """
    latest_publication = (
        select(
            FactSourcePublication.source,
            func.max(FactSourcePublication.published_at).label("published_at"),
        )
        .group_by(FactSourcePublication.source)
        .subquery()
    )
    still_live = (FactDataQuality.generation_id.is_(None)) | (
        FactDataQuality.generation_id.in_(
            select(FactRefreshGeneration.generation_id).where(
                FactRefreshGeneration.source == FactDataQuality.source,
                FactRefreshGeneration.status.in_(["IN_PROGRESS", "COMPLETE", "VALIDATED"]),
            )
        )
    )
    newer_than_serving = (latest_publication.c.published_at.is_(None)) | (
        FactDataQuality.executed_at > latest_publication.c.published_at
    )
    newest = (
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at).label("latest"))
        .outerjoin(latest_publication, FactDataQuality.source == latest_publication.c.source)
        .where(FactDataQuality.context == "CANDIDATE", newer_than_serving, still_live)
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
        .where(FactDataQuality.context == "CANDIDATE")
        .order_by(FactDataQuality.source, FactDataQuality.entity, FactDataQuality.check_name)
        .limit(limit)
    ).scalars()

    grouped: dict[str, list[CheckRecord]] = {}
    for row in rows:
        grouped.setdefault(row.source, []).append(_record(row))

    return [
        CandidateChecks(
            source=source,
            refresh_id=records[0].refresh_id or "",
            generation_id=records[0].generation_id,
            executed_at=records[0].executed_at,
            checks=records,
        )
        for source, records in grouped.items()
        if records and records[0].refresh_id
    ]


def published_generation_id(session: Session, *, source: str = "footystats") -> str | None:
    """The generation whose data this source is serving, per the publication ledger."""
    return session.scalar(
        select(FactSourcePublication.generation_id)
        .where(FactSourcePublication.source == source)
        .order_by(FactSourcePublication.published_at.desc(), FactSourcePublication.id.desc())
        .limit(1)
    )


def _latest_publication(session: Session, source: str) -> FactSourcePublication | None:
    return session.scalar(
        select(FactSourcePublication)
        .where(FactSourcePublication.source == source)
        .order_by(FactSourcePublication.published_at.desc(), FactSourcePublication.id.desc())
        .limit(1)
    )


def provider_quality(session: Session, *, limit: int = 200) -> list[ProviderQuality]:
    """Per source: the checks that validated what is serving, and the checks
    of whatever is waiting to be served. Never the two mixed.

    Every source that has either is listed. The published block comes from
    `latest_checks`, which excludes candidates by construction; the candidate
    block from `candidate_checks`. The publication ledger supplies when the
    served dataset was published and which refresh it was.
    """
    published_by_source: dict[str, list[CheckRecord]] = {}
    for record in latest_checks(session, limit=limit):
        published_by_source.setdefault(record.source, []).append(record)
    candidate_by_source = {c.source: c for c in candidate_checks(session, limit=limit)}

    sources = sorted(set(published_by_source) | set(candidate_by_source))
    result: list[ProviderQuality] = []
    for source in sources:
        published_records = published_by_source.get(source, [])
        publication = _latest_publication(session, source)
        published = (
            PublishedChecks(
                source=source,
                refresh_id=(
                    published_records[0].refresh_id
                    if published_records and published_records[0].refresh_id
                    else (publication.refresh_id if publication else None)
                ),
                generation_id=(
                    published_records[0].generation_id
                    if published_records and published_records[0].generation_id
                    else (publication.generation_id if publication else None)
                ),
                published_at=publication.published_at if publication else None,
                executed_at=published_records[0].executed_at if published_records else None,
                checks=published_records,
            )
            if published_records or publication
            else None
        )
        result.append(
            ProviderQuality(
                source=source,
                published=published,
                candidate=candidate_by_source.get(source),
            )
        )
    return result


def last_publications(session: Session) -> dict[str, tuple[datetime, int]]:
    """When each source's data last reached readers, and how much of it.

    THREE FACTS, NOT ONE
    --------------------

    A check ran. A load ran. A dataset was published. They were the same event
    once and none of them are now:

      - a check runs against whatever is serving, however old
      - a load writes to `analytics_staging`, and a staging load that fails
        identity resolution or a quality gate never becomes production
      - a publication is the schema swap, and only that

    This reads publications, because "how old is what I am looking at" is the
    question the freshness panel answers. Reading loads instead would let the
    site report a 10:00 refresh while still serving yesterday's figures - false
    in precisely the way a reader would act on.
    """
    newest = (
        select(
            FactSourcePublication.source,
            func.max(FactSourcePublication.published_at).label("latest"),
        )
        .group_by(FactSourcePublication.source)
        .subquery()
    )
    rows = session.execute(
        select(
            FactSourcePublication.source,
            FactSourcePublication.published_at,
            FactSourcePublication.rows_published,
        )
        .join(
            newest,
            (FactSourcePublication.source == newest.c.source)
            & (FactSourcePublication.published_at == newest.c.latest),
        )
        .order_by(FactSourcePublication.source)
    ).all()
    return {source: (published_at, int(rows)) for source, published_at, rows in rows}


def last_load_attempts(session: Session) -> dict[str, datetime]:
    """When each source was last loaded into staging, published or not.

    Operational rather than editorial. It answers "did the refresh run", which
    is worth knowing when loads happen hourly and nothing is being published;
    it must never be shown as the age of the data on screen.
    """
    rows = session.execute(
        select(FactSourceLoad.source, func.max(FactSourceLoad.loaded_at)).group_by(
            FactSourceLoad.source
        )
    ).all()
    return {source: loaded_at for source, loaded_at in rows}


def last_loads(session: Session) -> dict[str, tuple[datetime, int]]:
    """When each source was last loaded into staging, and how many rows arrived.

    The load ledger, unchanged. `/health` reports it because an operator asking
    "did the pipeline run" wants attempts, including the ones that never
    published. Readers get `last_publications` instead.
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
    """When each source was last checked, and how that run went.

    "Checked" means the dataset being served was checked. A candidate run
    against staging does not count: reporting it here would say the served
    data was checked today when what was checked today never reached readers.
    """
    newest = (
        select(FactDataQuality.source, func.max(FactDataQuality.executed_at).label("latest"))
        .where(_DESCRIBES_SERVING)
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
        .where(_DESCRIBES_SERVING)
        .group_by(FactDataQuality.source, newest.c.latest)
        .order_by(FactDataQuality.source)
    ).all()

    now = datetime.now(UTC)
    publications = last_publications(session)
    attempts = last_load_attempts(session)

    def with_load(source: str, **fields: object) -> SourceFreshness:
        attempted_at = attempts.get(source)
        entry = publications.get(source)
        if entry is None:
            # Published before publications were recorded, or never published.
            # Absent rather than guessed, and specifically not filled in from
            # the load attempt: a load that was never promoted is not an update
            # to anything a reader can see, and reporting it as one is the
            # mistake this separation exists to prevent.
            return SourceFreshness(
                source=source,
                last_load_attempt_at=attempted_at,
                **fields,  # type: ignore[arg-type]
            )
        published_at, row_count = entry
        return SourceFreshness(
            source=source,
            last_published_at=published_at,
            data_age_days=max((now - published_at).days, 0),
            rows_published=row_count,
            last_load_attempt_at=attempted_at,
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


@dataclass(frozen=True)
class CompetitionIdentityCoverage:
    """How much of one competition was reconciled against the identity source."""

    competition_id: str
    name: str
    players: int
    matched: int

    @property
    def matched_share(self) -> float:
        return self.matched / self.players if self.players else 0.0


def identity_coverage_by_competition(
    session: Session,
) -> list[CompetitionIdentityCoverage]:
    """The same figure as `identity_coverage`, split by competition.

    WHY THE SPLIT IS THE HONEST VIEW

    One overall share reads as a property of the product. It is not: measured
    over a real resolution it ran from 5% for the Copa Sudamericana to 92% for
    Eliteserien, because the Transfermarkt dataset covers South America, Asia,
    Canada and Finland far more thinly than it covers Europe's top divisions.

    That matters to a reader, and not as a footnote. A player with no identity
    counterpart has no position group, so they are not in the analytical view
    at all - and a competition at 5% is one the site barely represents while
    naming it alongside the Premier League. Nothing on the page said so.

    Unmatched is not a failure and this is not a check. It is the size of what
    each competition could be reconciled against, reported rather than averaged
    away, for the same reason every per-90 figure carries the minutes behind it.

    Counted over `fact_player_season_stats` rather than a player's current
    competition: the current one is inherited from the identity row when a
    merge happens, so grouping by it would ask the question of the answer.
    """
    matched_players = (
        select(BridgePlayerSource.player_id)
        .group_by(BridgePlayerSource.player_id)
        .having(func.count(func.distinct(BridgePlayerSource.source)) > 1)
        .subquery()
    )

    rows = session.execute(
        select(
            FactPlayerSeasonStats.competition_id,
            # Defensive, and unreachable today: the fact table's foreign key to
            # `dim_competition` makes a missing name impossible. Left in rather
            # than tested, because a test for it would have to be a lie.
            func.coalesce(DimCompetition.name, FactPlayerSeasonStats.competition_id),
            func.count(func.distinct(FactPlayerSeasonStats.player_id)),
            func.count(
                func.distinct(
                    case(
                        (
                            FactPlayerSeasonStats.player_id.in_(select(matched_players)),
                            FactPlayerSeasonStats.player_id,
                        ),
                        else_=None,
                    )
                )
            ),
        )
        .outerjoin(
            DimCompetition,
            DimCompetition.competition_id == FactPlayerSeasonStats.competition_id,
        )
        .group_by(FactPlayerSeasonStats.competition_id, DimCompetition.name)
    ).all()

    coverage = [
        CompetitionIdentityCoverage(
            competition_id=str(competition_id),
            name=str(name),
            players=int(players),
            matched=int(matched),
        )
        for competition_id, name, players, matched in rows
    ]
    # Thinnest first: the reader needs the competitions the site represents
    # least, and a list ordered by name buries them.
    coverage.sort(key=lambda c: (c.matched_share, -c.players))
    return coverage


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


@dataclass(frozen=True)
class MetricAvailability:
    """One canonical metric the provider cannot supply, and what was found.

    The reason comes from the profiling that established it - a key declared
    and never populated, an attempt count absent where only successes are
    given, a percentage returning zero for everybody. A page that lists five
    names tells a reader nothing about whether the gap could ever close.
    """

    metric: str
    label: str
    reason: str | None


@dataclass(frozen=True)
class DerivedMetricNote:
    """A metric the provider has no field for and the system computes anyway."""

    metric: str
    label: str
    formula: str


def metric_availability(
    settings: Settings,
) -> tuple[list[MetricAvailability], list[DerivedMetricNote]]:
    """What cannot be supplied and what is computed instead.

    Two lists rather than one, because they are opposite facts and were being
    reported as the same one. Non-penalty goals has no FootyStats field and
    appears on every forward's profile, computed from goals and penalty goals;
    it was listed as unavailable on the page whose job is to describe the data
    accurately.
    """
    try:
        provider = build_performance_provider(settings)
    except AppError:
        return [], []

    info = provider.info
    reasons = info.absent_reasons
    derived = [
        DerivedMetricNote(metric=name, label=_metric_label(name), formula=formula)
        for name, formula in sorted(info.derived_metrics.items())
    ]

    available = info.available_metrics
    unavailable = [
        MetricAvailability(
            metric=metric.value,
            label=_metric_label(metric.value),
            reason=reasons.get(metric.value),
        )
        for metric in CanonicalMetric
        if metric not in available
    ]
    return sorted(unavailable, key=lambda item: item.metric), derived


def _metric_label(name: str) -> str:
    """The reader's name for a canonical metric, not the column's."""
    return name.replace("_", " ").capitalize()


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


@dataclass(frozen=True)
class MarketServing:
    """How much market data the product is currently serving.

    SERVING, NOT INGESTIBLE
    -----------------------

    There are two market questions and they had been collapsed into one.

    "Can a Transfermarkt snapshot be read from disk right now?" is an
    *ingestion* precondition. It is answered by the downloaded dataset, it is
    false on the serving host by design - the API does not do the downloading -
    and it says nothing about what a reader sees.

    "Is market data available and valid for the product?" is a *serving*
    question, answered by the rows in this database. Those rows are what the
    market value, the valuation history, the transfer list, the Opportunities
    filters and the replacement affordability context are all built from.

    The status page asked the first and published the answer as if it were the
    second: production served market values on every profile while System
    Status called market data unavailable and told the reader to run a
    download command. Both statements were about different things and only one
    of them was about the product.
    """

    #: Players carrying a current valuation - the figure profiles display.
    players_with_value: int
    #: Players with a contract expiry, which the recruitment filters screen on.
    players_with_contract: int
    #: Rows behind the market value chart.
    valuations: int
    #: Rows behind the transfer history.
    transfers: int

    @property
    def available(self) -> bool:
        """Whether any market figure on the site has something behind it."""
        return self.players_with_value > 0 or self.valuations > 0 or self.transfers > 0


def market_serving(session: Session) -> MarketServing:
    """Count the market data actually behind the pages. Four cheap counts."""
    return MarketServing(
        players_with_value=session.scalar(
            select(func.count())
            .select_from(DimPlayer)
            .where(DimPlayer.current_market_value_eur.is_not(None))
        )
        or 0,
        players_with_contract=session.scalar(
            select(func.count())
            .select_from(DimPlayer)
            .where(DimPlayer.contract_expires.is_not(None))
        )
        or 0,
        valuations=session.scalar(select(func.count()).select_from(FactMarketValue)) or 0,
        transfers=session.scalar(select(func.count()).select_from(FactTransfer)) or 0,
    )


def volumes(session: Session) -> Volumes:
    """What is actually loaded. Cheap counts, safe to serve on a request."""
    return Volumes(
        players=session.scalar(select(func.count()).select_from(DimPlayer)) or 0,
        competitions=session.scalar(select(func.count()).select_from(DimCompetition)) or 0,
        clubs=session.scalar(select(func.count()).select_from(DimClub)) or 0,
        player_seasons=session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0,
    )


# ---------------------------------------------------------------------------
# Refresh generations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationSummary:
    """One generation, reduced to what a public page may show."""

    generation_id: str
    status: str
    created_at: str | None
    last_updated_at: str | None
    published_at: str | None
    total_expected_players: int
    completed_players: int
    failed_players: int
    completion_pct: float
    competitions_complete: int
    competitions_expected: int
    complete: bool


@dataclass(frozen=True)
class RefreshStatus:
    """What the refresh is doing, and what the site is actually serving.

    Two generations, and the distance between them is the point. `current` is
    the one being worked on and `published` is the one a reader is looking at;
    they are different objects until a promotion makes them the same, and a
    panel showing only one of them cannot answer "why is this still last
    week's figure".
    """

    #: Fetching | Validating | Ready to publish | Failed | Idle.
    state: str
    #: The same five states as a key, for an interface that names them itself.
    state_key: str
    published: GenerationSummary | None
    current: GenerationSummary | None


def refresh_status(session: Session) -> RefreshStatus | None:
    """Where the FootyStats refresh has got to, if anything has recorded it.

    Reads `fact_refresh_generation`, which the pipeline writes as it goes. Not
    the generation directory: the fetch runs in CI with its snapshots in the
    job cache, and this process cannot see that filesystem. Reading the disk
    would show full progress in development and nothing in production.

    `None` when nothing has been recorded - a database loaded before
    generations existed. The page then hides the panel rather than showing an
    empty progress bar implying a stalled refresh.
    """
    rows = session.scalars(
        select(FactRefreshGeneration)
        .where(FactRefreshGeneration.source == "footystats")
        .order_by(FactRefreshGeneration.generation_id)
    ).all()
    if not rows:
        return None

    published = next((r for r in reversed(rows) if r.status == "PUBLISHED"), None)
    # VALIDATED belongs here as much as the other two. It means the fetch
    # finished, the checks passed, and promotion has not happened yet - a
    # generation genuinely waiting to be published. Leaving it out reported
    # "Idle" over a refresh that was one step from the site, which is the
    # state a reader most wants to see named.
    current = next(
        (r for r in reversed(rows) if r.status in {"IN_PROGRESS", "COMPLETE", "VALIDATED"}),
        None,
    )

    # The word and the key beside it: the word is the English sentence, the
    # key is what an interface in another language names the same state by.
    state, state_key = "Idle", "idle"
    if current is not None:
        state, state_key = {
            "IN_PROGRESS": ("Fetching", "fetching"),
            "COMPLETE": ("Validating", "validating"),
            "VALIDATED": ("Ready to publish", "ready_to_publish"),
        }[current.status]
    elif rows[-1].status == "FAILED":
        state, state_key = "Failed", "failed"

    return RefreshStatus(
        state=state,
        state_key=state_key,
        published=_summarise(published) if published else None,
        current=_summarise(current) if current else None,
    )


def _summarise(row: FactRefreshGeneration) -> GenerationSummary:
    expected = row.total_expected_players
    return GenerationSummary(
        generation_id=row.generation_id,
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else None,
        last_updated_at=row.updated_at.isoformat() if row.updated_at else None,
        published_at=row.published_at.isoformat() if row.published_at else None,
        total_expected_players=expected,
        completed_players=row.completed_players,
        failed_players=row.failed_players,
        completion_pct=round(100.0 * row.completed_players / expected, 1) if expected else 0.0,
        competitions_complete=row.competitions_complete,
        competitions_expected=row.competitions_expected,
        complete=row.complete,
    )
