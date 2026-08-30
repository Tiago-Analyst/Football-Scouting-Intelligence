"""Assembles the analytical view the API serves.

Everything the website shows — percentiles, intelligence scores, role fit,
similarity — is derived from the same population, so it is built once and held
in memory rather than recomputed per request (spec section 27).

The cost of building it is real: roughly 1,700 players, each with 43 derived
metrics, ranked against position-scoped distributions and scored against up to
four roles. Doing that inside a request handler would make every page load
proportional to the size of the database.

**It reads PostgreSQL, in every mode.** It used to call the providers directly,
which meant the loader wrote tables nothing read: the loader's refusal to commit
a failing load - "corrupted data is never published" - guarded a database no
reader consulted, and a provider call sat inside the serving process. Demo mode
is no different now; the demo load writes the mock provider's output to the
database, and the site serves that.

A consequence worth stating: **the API needs a load to have happened.** An empty
database is reported as empty rather than rendered as a working but deserted
site.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache

from app.analytics.contracts import reference_date
from app.analytics.intelligence import IntelligenceScore, IntelligenceScoreEngine
from app.analytics.metrics import DerivedMetric, DerivedMetrics, compute_derived
from app.analytics.percentiles import (
    PercentileEngine,
    PercentileResult,
    PercentileScope,
    PlayerMetrics,
)
from app.analytics.roles import RoleEngine, RoleFit
from app.analytics.sample import SampleBand, classify_minutes
from app.analytics.similarity import (
    MINIMUM_SIMILARITY,
    SimilarityCandidate,
    SimilarityEngine,
    SimilarityFilters,
    SimilarityResult,
)
from app.core.config import AppMode, Settings, get_settings
from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.providers.market_base import MarketDataProvider
from app.providers.registry import build_market_provider
from app.repositories.analytics_repository import (
    UniverseFingerprint,
    fingerprint,
    load_universe,
)
from app.schemas.canonical import PlayerSeasonStats, PositionGroup, PreferredFoot

log = get_logger(__name__)

#: Kept as a name so callers read `reference_date()` rather than `date.today()`
#: scattered about, and so a test can pass its own date instead.
#:
#: This was a fixed 1 January 2027, chosen so the demo universe produced stable
#: ages. Against real data it put 28% of players at an age they had not reached.


@dataclass(frozen=True)
class PlayerRecord:
    """Everything the API knows about one player-season."""

    player_key: str
    full_name: str
    position_group: PositionGroup
    raw_position: str | None
    competition_id: str
    competition_name: str
    club_id: str | None
    club_name: str | None
    nationality: str | None
    preferred_foot: PreferredFoot | None
    height_cm: int | None
    date_of_birth: date | None
    age: int | None
    market_value_eur: int | None
    contract_expires: date | None
    minutes: int | None
    sample_band: SampleBand
    stats: PlayerSeasonStats
    metrics: DerivedMetrics
    #: The real season, used to group comparison populations. Kept on the record
    #: because it is needed wherever a `PlayerMetrics` is built, and building it
    #: from `stats.season_id` in one place and from here in another is how the
    #: two silently stopped agreeing.
    comparable_season: str = ""

    @property
    def slug(self) -> str:
        return self.player_key


@dataclass
class AnalyticsView:
    """The assembled, queryable analytical universe."""

    players: dict[str, PlayerRecord] = field(default_factory=dict)
    competitions: dict[str, str] = field(default_factory=dict)
    clubs: dict[str, str] = field(default_factory=dict)
    percentiles: PercentileEngine | None = None
    intelligence: IntelligenceScoreEngine | None = None
    roles: RoleEngine | None = None
    similarity: SimilarityEngine | None = None
    market: MarketDataProvider | None = None
    #: Best role per player, precomputed because player search shows it in a
    #: column and computing it per row would make the list quadratic.
    best_roles: dict[str, RoleFit] = field(default_factory=dict)
    build_seconds: float = 0.0
    is_mock: bool = True
    #: Which loaded sources the view was built from. Empty before a first load.
    sources: frozenset[str] = field(default_factory=frozenset)
    #: Loaded player-seasons left out because they carry no position group, and
    #: so cannot be ranked against a comparison population.
    players_without_position: int = 0
    #: When this view was assembled, and what the database held at the time.
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    fingerprint: UniverseFingerprint | None = None

    @property
    def is_empty(self) -> bool:
        """No data has been loaded.

        Callers must say so rather than serving an empty site as a working one:
        a search returning nothing looks the same whether the filter was narrow
        or the database was never filled.
        """
        return not self.players

    # -- Lookups ------------------------------------------------------------

    def get(self, player_key: str) -> PlayerRecord | None:
        return self.players.get(player_key)

    def player_metrics(self, player_key: str) -> PlayerMetrics | None:
        record = self.players.get(player_key)
        if record is None:
            return None
        return PlayerMetrics(
            player_key=record.player_key,
            position_group=record.position_group,
            competition_id=record.competition_id,
            season_id=record.comparable_season or record.stats.season_id,
            metrics=record.metrics,
        )

    def rank(
        self,
        player_key: str,
        metrics: list[DerivedMetric],
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
    ) -> dict[DerivedMetric, PercentileResult]:
        record = self.player_metrics(player_key)
        if record is None or self.percentiles is None:
            return {}
        return self.percentiles.rank_all(record, metrics, scope=scope)

    def scores(
        self, player_key: str, *, scope: PercentileScope = PercentileScope.COMPETITION
    ) -> dict[str, IntelligenceScore]:
        record = self.player_metrics(player_key)
        if record is None or self.intelligence is None:
            return {}
        return self.intelligence.score_all(record, scope=scope)

    def role_fit(
        self, player_key: str, *, scope: PercentileScope = PercentileScope.COMPETITION
    ) -> RoleFit | None:
        if scope is PercentileScope.COMPETITION and player_key in self.best_roles:
            return self.best_roles[player_key]
        record = self.player_metrics(player_key)
        if record is None or self.roles is None:
            return None
        return self.roles.fit(record, scope=scope)

    def similar(
        self,
        player_key: str,
        *,
        filters: SimilarityFilters | None = None,
        limit: int = 20,
        minimum_minutes: int | None = 900,
        minimum_similarity: float = MINIMUM_SIMILARITY,
    ) -> list[SimilarityResult]:
        if self.similarity is None:
            return []
        try:
            return self.similarity.similar_to(
                player_key,
                filters=filters,
                limit=limit,
                minimum_minutes=minimum_minutes,
                minimum_similarity=minimum_similarity,
                today=reference_date(),
            )
        except KeyError:
            return []


def _age_at(born: date | None, reference: date) -> int | None:
    if born is None:
        return None
    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))


def build_view(settings: Settings) -> AnalyticsView:
    """Assemble the analytical universe from what the pipeline loaded."""
    started = time.perf_counter()
    today = reference_date()

    # The market provider stays: valuation history and transfers are served per
    # player rather than held in the view. Everything the *view* needs now comes
    # from the database.
    market = build_market_provider(settings)

    with get_session_factory()() as session:
        loaded_fingerprint = fingerprint(session)
        universe = load_universe(session)

    view = AnalyticsView(
        market=market,
        is_mock=settings.app_mode is AppMode.DEMO,
        sources=universe.sources,
        fingerprint=loaded_fingerprint,
    )
    # Only competitions and clubs that actually have players in the view. The
    # dimension tables hold every competition any source has ever mentioned -
    # 65 of them arrive with the Transfermarkt market data and carry no
    # performance stats at all - and listing those as searchable would offer
    # filters that can only ever return nothing.
    view.clubs.update(universe.clubs)

    if universe.is_empty:
        # Not an error. A database before its first load is a normal state, and
        # the engines below would otherwise rank nobody against nobody.
        view.build_seconds = time.perf_counter() - started
        log.warning("analytics_view_empty", reason="no player-seasons loaded")
        return view

    population: list[PlayerMetrics] = []
    candidates: dict[str, SimilarityCandidate] = {}
    player_metrics: dict[str, PlayerMetrics] = {}

    skipped_no_position = 0
    #: Player-seasons belonging to a player who has more than one. Every one of
    #: them still shapes the comparison populations; only the row the site shows
    #: is chosen between.
    superseded = 0

    for loaded in universe.players:
        if loaded.position_group is None:
            # Percentiles are scoped to a position group, so a player without
            # one cannot be ranked against anybody. Including them would put a
            # player in the site with no comparison population behind their
            # numbers, which is worse than leaving them out and saying so.
            skipped_no_position += 1
            continue

        metrics = compute_derived(loaded.stats)
        record = PlayerRecord(
            player_key=loaded.player_key,
            full_name=loaded.full_name,
            position_group=loaded.position_group,
            raw_position=loaded.raw_position,
            competition_id=loaded.competition_id,
            competition_name=loaded.competition_name,
            club_id=loaded.club_id,
            club_name=loaded.club_name,
            nationality=loaded.nationality,
            preferred_foot=loaded.preferred_foot,
            height_cm=loaded.height_cm,
            date_of_birth=loaded.date_of_birth,
            age=_age_at(loaded.date_of_birth, today),
            market_value_eur=loaded.market_value_eur,
            contract_expires=loaded.contract_expires,
            minutes=loaded.stats.minutes,
            # Classified on the minutes the statistics cover, not on time on
            # the pitch. The sample-size rule exists to stop a ranking being
            # built on too little evidence, and the evidence is those minutes.
            sample_band=classify_minutes(
                loaded.stats.recorded_minutes
                if loaded.stats.recorded_minutes is not None
                else loaded.stats.minutes
            ),
            stats=loaded.stats,
            metrics=metrics,
            comparable_season=loaded.comparable_season or loaded.stats.season_id,
        )
        # A player can hold several player-seasons at once - a domestic league
        # and a cup, or a league and a continental competition. The view shows
        # one row per player, so one has to be chosen, and until now it was
        # whichever happened to be read last: 133 of 8,701 player-seasons were
        # discarded by insertion order, and a player with 184 league minutes
        # could be represented by their 9 minutes in the Champions League.
        #
        # The season with the most minutes played is the one that describes the
        # player. Ties break on competition id so the choice is stable across
        # runs rather than merely deterministic within one.
        existing = view.players.get(record.player_key)
        if existing is not None:
            superseded += 1
            incumbent = (existing.minutes or 0, existing.competition_id)
            challenger = (record.minutes or 0, record.competition_id)
            if challenger <= incumbent:
                view.competitions[record.competition_id] = record.competition_name
                population.append(
                    PlayerMetrics(
                        player_key=record.player_key,
                        position_group=record.position_group,
                        competition_id=record.competition_id,
                        season_id=record.comparable_season,
                        metrics=metrics,
                    )
                )
                continue

        view.players[record.player_key] = record
        view.competitions[record.competition_id] = record.competition_name

        record_metrics = PlayerMetrics(
            player_key=record.player_key,
            position_group=record.position_group,
            competition_id=record.competition_id,
            # The real season, not the provider's identifier for it. Percentile
            # populations are grouped by this, and grouping by the provider's id
            # partitioned every competition into its own island.
            season_id=record.comparable_season,
            metrics=metrics,
        )
        population.append(record_metrics)
        player_metrics[record.player_key] = record_metrics
        candidates[record.player_key] = SimilarityCandidate(
            player_key=record.player_key,
            display_name=record.full_name,
            position_group=record.position_group,
            competition_id=record.competition_id,
            club_id=record.club_id,
            age=record.age,
            market_value_eur=record.market_value_eur,
            contract_expires=record.contract_expires,
            nationality=record.nationality,
        )

    if superseded:
        log.info(
            "player_seasons_superseded",
            count=superseded,
            note="players with more than one competition; the most-played season is shown",
        )

    view.players_without_position = skipped_no_position
    if skipped_no_position:
        log.warning(
            "players_excluded_without_position",
            count=skipped_no_position,
            of=len(universe.players),
        )

    view.percentiles = PercentileEngine(population)
    view.intelligence = IntelligenceScoreEngine(view.percentiles)
    view.roles = RoleEngine(view.intelligence)
    view.similarity = SimilarityEngine(view.percentiles, candidates, players=player_metrics)

    # Precomputed because player search lists a best-role column: resolving it
    # per row would make a page of results cost as much as the whole database.
    for key, metrics_record in player_metrics.items():
        view.best_roles[key] = view.roles.fit(metrics_record)

    view.build_seconds = time.perf_counter() - started
    log.info(
        "analytics_view_built",
        players=len(view.players),
        competitions=len(view.competitions),
        seconds=round(view.build_seconds, 2),
        is_mock=view.is_mock,
    )
    return view


@lru_cache(maxsize=1)
def get_analytics_view() -> AnalyticsView:
    """Process-wide analytical view. Tests clear with `.cache_clear()`."""
    return build_view(get_settings())


def refresh_analytics_view() -> AnalyticsView:
    """Rebuild the view from the database.

    Held in memory for the life of the process, so a load that happens while
    the API is running does not reach it on its own. Rather than rebuild on a
    timer - which would make the site briefly disagree with itself for reasons
    nobody could see - staleness is *reported* by `is_stale`, and this is the
    explicit way to act on it.
    """
    get_analytics_view.cache_clear()
    return get_analytics_view()


def view_is_stale() -> bool:
    """Whether the database has been loaded since this view was built."""
    view = get_analytics_view()
    if view.fingerprint is None:
        return True
    with get_session_factory()() as session:
        return fingerprint(session) != view.fingerprint
