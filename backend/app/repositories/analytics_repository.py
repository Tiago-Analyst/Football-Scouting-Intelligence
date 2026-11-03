"""Read the analytical universe out of PostgreSQL.

Until now the serving layer built its view by calling the providers directly, and
the loader wrote to `dim_player` and `fact_player_season_stats` — tables nothing
read. Two consequences followed, and both are why this module exists:

**The validation gate protected nothing.** The loader refuses to commit a load
that fails its checks, so that "corrupted data is never published". But the site
was not serving that data, so the gate guarded a database no reader consulted.

**A provider call sat in the serving process.** `PerformanceDataProvider` says
providers are consumed by the ingestion pipeline and never during a web request.
Building the view from providers at startup put a 218 MB dataset scan — and, in
production, a FootyStats call — inside the API process.

So the API reads the database and the pipeline writes it, which is what the
architecture claimed all along.

One query per table, assembled in memory. The alternative — a join returning one
row per player-season with every dimension repeated — costs more to transfer than
the three lookups cost to stitch, and the whole set is loaded exactly once per
view build rather than per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactDataQuality,
    FactPlayerSeasonStats,
)
from app.schemas.canonical import (
    CanonicalMetric,
    PlayerSeasonStats,
    PositionGroup,
    PreferredFoot,
)


@dataclass(frozen=True)
class LoadedPlayer:
    """One player-season as stored, before analytics are computed over it.

    TWO CONTEXTS, NAMED AS TWO

    A row here answers two different questions and used to answer them under
    one set of names, which is how a profile came to read

        club: a Danish club
        competition: USA MLS
        contract: expires 2027

    with nothing wrong in the database. The competition, the season and every
    metric describe A SEASON THAT HAS BEEN PLAYED. The club, the value and the
    contract describe WHERE THE PLAYER IS NOW. Both were true; one of them was
    called `club` and sat next to the other on the same line.

    So the fields say which they belong to. `competition_*` and
    `performance_club_*` are the season; `current_*` is today. Nothing here is
    reconciled into a single state, because they are not one state - a player
    who moved in the summer has a July club and a May competition, and that is
    football rather than a defect.
    """

    player_key: str
    full_name: str
    position_group: PositionGroup | None
    raw_position: str | None
    #: -- Performance context: the season these metrics come from ------------
    competition_id: str
    competition_name: str
    competition_country: str | None
    #: The club this player-season was played for.
    #:
    #: Almost always absent. `fact_player_season_stats.club_id` is only written
    #: when the club is already in `dim_club`, and the performance provider's
    #: clubs are keyed in its own vocabulary, so for real data this is null far
    #: more often than not. Absent is reported as absent: the current club used
    #: to be shown here instead, which is the defect this split removes.
    performance_club_name: str | None
    #: -- Current market context: where the player is now ---------------------
    current_club_id: str | None
    current_club_name: str | None
    #: The competition the CURRENT club plays in, in the market provider's own
    #: vocabulary. Not comparable by id with `competition_id` above - the two
    #: providers key competitions differently and nothing maps between them -
    #: which is why `competition_country` exists beside it.
    current_competition_name: str | None
    current_competition_country: str | None
    nationality: str | None
    preferred_foot: PreferredFoot | None
    height_cm: int | None
    date_of_birth: date | None
    market_value_eur: int | None
    contract_expires: date | None
    stats: PlayerSeasonStats
    #: The season this player-season belongs to in the real world, as opposed to
    #: the identifier the provider gave it.
    #:
    #: FootyStats issues a distinct season id per competition, so 34 loaded
    #: competitions produced 34 season ids for one actual season. Percentile
    #: populations are grouped by season, so every group collapsed to a single
    #: competition and the global scope could never compare across leagues -
    #: silently, because a comparison that spans one league is still a valid
    #: comparison. `dim_season` knew all 34 were 2026/2027 all along.
    comparable_season: str = ""


@dataclass(frozen=True)
class LoadedUniverse:
    """Everything the analytical view is built from.

    `is_empty` is a normal state — a fresh database before its first load — and
    the caller must say so rather than presenting an empty site as a working
    one.
    """

    players: list[LoadedPlayer]
    competitions: dict[str, str]
    clubs: dict[str, str]
    sources: frozenset[str]

    @property
    def is_empty(self) -> bool:
        return not self.players


def _stats_from_row(
    row: FactPlayerSeasonStats, *, player_key: str, club_id: str
) -> PlayerSeasonStats:
    """Rebuild the canonical record from its stored columns.

    Driven by `CanonicalMetric` rather than by a written-out field list, so a
    metric added to the model cannot be silently dropped on the way back out —
    the column and the field share a name by construction, and a test asserts
    they stay in step.
    """
    return PlayerSeasonStats(
        source_player_id=player_key,
        season_id=row.season_id,
        competition_id=row.competition_id,
        club_id=club_id,
        **{metric.value: getattr(row, metric.value) for metric in CanonicalMetric},  # type: ignore[arg-type]
    )


@dataclass(frozen=True)
class UniverseFingerprint:
    """A cheap summary of what is currently loaded.

    Two scalar queries, so it can be asked on a health check without scanning
    anything. Comparing it against the fingerprint a view was built from is how
    "the pipeline has loaded new data since this process started" becomes a
    fact rather than a guess.
    """

    player_seasons: int
    #: The most recent check written about data that is actually SERVED.
    #: Named for what it measures: a candidate's checks are excluded, so this
    #: moves at promotion rather than at load.
    last_served_check_at: datetime | None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UniverseFingerprint):
            return NotImplemented
        return (
            self.player_seasons == other.player_seasons
            and self.last_served_check_at == other.last_served_check_at
        )


def fingerprint(session: Session) -> UniverseFingerprint:
    """What is loaded right now, without reading any of it.

    WHY CANDIDATE ROWS ARE EXCLUDED

    This used to take the maximum `executed_at` over every quality check, and
    a candidate load writes checks. So a FootyStats refresh landing in
    `analytics_staging` - data nobody is served, which may never be promoted -
    moved the fingerprint, the running view was declared stale, `/health`
    answered 503, and the heartbeat failed every run until somebody restarted
    an API that had nothing wrong with it. Measured on 3 November: the served
    `player_seasons` had not changed at all, and the only difference was 18
    candidate checks written two days earlier.

    `fact_data_quality.context` already draws the line. `CANDIDATE` means
    written against staging; `PUBLISHED` and `NULL` mean written about data
    being served. The promotion flips a refresh's rows to `PUBLISHED` in the
    same transaction as the schema swap, so the maximum below moves exactly
    when the served universe does.

    `fact_source_publication` is the more authoritative record of what reached
    readers, and this deliberately does not use it: a demo or local database
    never promotes anything, so its publication table is empty and staleness
    would rest on the row count alone. The context filter is correct in both.
    """
    return UniverseFingerprint(
        player_seasons=session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0,
        last_served_check_at=session.scalar(
            select(func.max(FactDataQuality.executed_at)).where(
                # `IS DISTINCT FROM` and not `!=`: context is nullable, and a
                # NULL compared with `!=` is NULL, which filters out every row
                # written before the staging schema existed.
                FactDataQuality.context.is_distinct_from("CANDIDATE")
            )
        ),
    )


def load_universe(session: Session, *, source: str | None = None) -> LoadedUniverse:
    """Read every stored player-season, with the dimensions they refer to."""
    competition_rows = session.scalars(select(DimCompetition)).all()
    competitions = {row.competition_id: row.name for row in competition_rows}
    #: The only thing a competition from one provider and a competition from
    #: the other can be compared by.
    #
    # FootyStats calls it `footystats:17097`, "Netherlands Eredivisie";
    # Transfermarkt calls the same league `transfermarkt:NL1`, "eredivisie".
    # There is no mapping between the two vocabularies and this product has
    # never needed one, so comparing the ids answers "different" for leagues
    # that are the same. Both carry a country, and a country is a real answer
    # to a smaller question - it cannot tell a first division from a second,
    # and nothing here claims it can.
    competition_countries = {row.competition_id: row.country for row in competition_rows}
    club_rows = session.scalars(select(DimClub)).all()
    clubs = {row.club_id: row.name for row in club_rows}

    # Keyed on the starting year rather than the season's name: two providers
    # write the same season as "2026/27" and "2026/2027", and pooling them is
    # the entire point.
    seasons = {
        row.season_id: str(row.start_year) for row in session.scalars(select(DimSeason)).all()
    }

    statement = select(FactPlayerSeasonStats)
    if source is not None:
        statement = statement.where(FactPlayerSeasonStats.source == source)

    # Only the players who actually have statistics.
    #
    # This used to read every row of `dim_player` and `bridge_player_source` -
    # 53,591 and 58,724 of them - to use the 8,568 that carry a player-season.
    # The other 45,000 are the pool identity resolution matches against, and
    # they belong in the database rather than in the process serving the site.
    #
    # It was merely wasteful until the percentile population stopped excluding
    # short seasons, which grew everything else; together they took the build
    # peak past what a 512 MB container will bear, and the process was killed
    # partway through - visible only as the API returning 502 to every request
    # while its liveness probe, which builds nothing, went on answering.
    with_stats = statement.with_only_columns(FactPlayerSeasonStats.player_id).distinct()

    players_by_id = {
        row.player_id: row
        for row in session.scalars(select(DimPlayer).where(DimPlayer.player_id.in_(with_stats)))
    }

    # The provider's own identifier, which is what the rest of the system uses
    # as a player key. Not the database's integer id: that is an implementation
    # detail, and switching to it would change every player URL and orphan every
    # shortlist entry saved against the old key.
    source_keys = {
        (row.source, row.player_id): row.source_player_id
        for row in session.scalars(
            select(BridgePlayerSource).where(BridgePlayerSource.player_id.in_(with_stats))
        )
    }

    loaded: list[LoadedPlayer] = []
    sources: set[str] = set()

    for row in session.scalars(statement).all():
        player = players_by_id.get(row.player_id)
        if player is None:
            # A fact row with no dimension is a broken load. The quality report
            # asserts this never happens; skipping here means one bad row does
            # not take down the whole site while that is being investigated.
            continue

        player_key = source_keys.get((row.source, row.player_id))
        if player_key is None:
            # A fact row whose player has no bridge entry for its own source.
            # The loader creates both together, so this cannot happen from a
            # clean load; skipping keeps one broken row from taking the site
            # down while the quality report flags it.
            continue

        sources.add(row.source)
        current_club_id = player.current_club_id
        current_competition_id = player.current_competition_id
        loaded.append(
            LoadedPlayer(
                player_key=player_key,
                full_name=player.full_name,
                position_group=player.position_group,
                raw_position=player.raw_position,
                competition_id=row.competition_id,
                competition_name=competitions.get(row.competition_id, row.competition_id),
                competition_country=competition_countries.get(row.competition_id),
                # `row.club_id`, which this read used to throw away and replace
                # with the current club. The row knows which club played the
                # season; where it does not, nothing does, and the answer is
                # null rather than a club that was never there.
                performance_club_name=clubs.get(row.club_id) if row.club_id else None,
                current_club_id=current_club_id,
                current_club_name=clubs.get(current_club_id) if current_club_id else None,
                current_competition_name=(
                    competitions.get(current_competition_id) if current_competition_id else None
                ),
                current_competition_country=(
                    competition_countries.get(current_competition_id)
                    if current_competition_id
                    else None
                ),
                nationality=player.nationality,
                preferred_foot=player.preferred_foot,
                height_cm=player.height_cm,
                date_of_birth=player.date_of_birth,
                market_value_eur=player.current_market_value_eur,
                contract_expires=player.contract_expires,
                # The club on the row, not the one the player is at now. This
                # argument used to carry the current club, which stamped a
                # season's statistics with a club that may never have fielded
                # them.
                stats=_stats_from_row(row, player_key=player_key, club_id=row.club_id or ""),
                # Falls back to the provider's id, which is what it was before:
                # a season nothing knows about is better compared narrowly than
                # pooled with seasons it may not belong to.
                comparable_season=seasons.get(row.season_id, row.season_id),
            )
        )

    return LoadedUniverse(
        players=loaded,
        competitions=competitions,
        clubs=clubs,
        sources=frozenset(sources),
    )
