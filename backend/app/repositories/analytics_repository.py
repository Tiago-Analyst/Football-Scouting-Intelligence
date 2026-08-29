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
    """One player-season as stored, before analytics are computed over it."""

    player_key: str
    full_name: str
    position_group: PositionGroup | None
    raw_position: str | None
    competition_id: str
    competition_name: str
    club_id: str | None
    club_name: str | None
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
    last_loaded_at: datetime | None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UniverseFingerprint):
            return NotImplemented
        return (
            self.player_seasons == other.player_seasons
            and self.last_loaded_at == other.last_loaded_at
        )


def fingerprint(session: Session) -> UniverseFingerprint:
    """What is loaded right now, without reading any of it."""
    return UniverseFingerprint(
        player_seasons=session.scalar(select(func.count()).select_from(FactPlayerSeasonStats)) or 0,
        last_loaded_at=session.scalar(select(func.max(FactDataQuality.executed_at))),
    )


def load_universe(session: Session, *, source: str | None = None) -> LoadedUniverse:
    """Read every stored player-season, with the dimensions they refer to."""
    competitions = {
        row.competition_id: row.name for row in session.scalars(select(DimCompetition)).all()
    }
    clubs = {row.club_id: row.name for row in session.scalars(select(DimClub)).all()}

    # Keyed on the starting year rather than the season's name: two providers
    # write the same season as "2026/27" and "2026/2027", and pooling them is
    # the entire point.
    seasons = {
        row.season_id: str(row.start_year) for row in session.scalars(select(DimSeason)).all()
    }

    players_by_id = {row.player_id: row for row in session.scalars(select(DimPlayer)).all()}

    # The provider's own identifier, which is what the rest of the system uses
    # as a player key. Not the database's integer id: that is an implementation
    # detail, and switching to it would change every player URL and orphan every
    # shortlist entry saved against the old key.
    source_keys = {
        (row.source, row.player_id): row.source_player_id
        for row in session.scalars(select(BridgePlayerSource)).all()
    }

    statement = select(FactPlayerSeasonStats)
    if source is not None:
        statement = statement.where(FactPlayerSeasonStats.source == source)

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
        club_id = player.current_club_id
        loaded.append(
            LoadedPlayer(
                player_key=player_key,
                full_name=player.full_name,
                position_group=player.position_group,
                raw_position=player.raw_position,
                competition_id=row.competition_id,
                competition_name=competitions.get(row.competition_id, row.competition_id),
                club_id=club_id,
                club_name=clubs.get(club_id) if club_id else None,
                nationality=player.nationality,
                preferred_foot=player.preferred_foot,
                height_cm=player.height_cm,
                date_of_birth=player.date_of_birth,
                market_value_eur=player.current_market_value_eur,
                contract_expires=player.contract_expires,
                stats=_stats_from_row(row, player_key=player_key, club_id=club_id or ""),
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
