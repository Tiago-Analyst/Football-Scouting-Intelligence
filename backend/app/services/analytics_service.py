"""Assembles the analytical view the API serves.

Everything the website shows — percentiles, intelligence scores, role fit,
similarity — is derived from the same population, so it is built once and held
in memory rather than recomputed per request (spec section 27).

The cost of building it is real: roughly 1,700 players, each with 43 derived
metrics, ranked against position-scoped distributions and scored against up to
four roles. Doing that inside a request handler would make every page load
proportional to the size of the database.

In production this layer reads from PostgreSQL. In demo mode it reads from the
mock providers, which is what makes the site fully navigable before any real
performance data exists.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

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
    SimilarityCandidate,
    SimilarityEngine,
    SimilarityFilters,
    SimilarityResult,
)
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.providers.market_base import MarketDataProvider
from app.providers.registry import build_market_provider, build_performance_provider
from app.schemas.canonical import PlayerSeasonStats, PositionGroup, PreferredFoot

log = get_logger(__name__)

REFERENCE_DATE = date(2027, 1, 1)


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
            season_id=record.stats.season_id,
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
    ) -> list[SimilarityResult]:
        if self.similarity is None:
            return []
        try:
            return self.similarity.similar_to(
                player_key,
                filters=filters,
                limit=limit,
                minimum_minutes=minimum_minutes,
                today=REFERENCE_DATE,
            )
        except KeyError:
            return []


def _age_at(born: date | None, reference: date) -> int | None:
    if born is None:
        return None
    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))


def build_view(settings: Settings) -> AnalyticsView:
    """Assemble the analytical universe from the configured providers."""
    started = time.perf_counter()
    performance = build_performance_provider(settings)
    market = build_market_provider(settings)

    market_by_id = {p.source_player_id: p for p in market.get_players()}

    view = AnalyticsView(market=market, is_mock=performance.info.is_mock)
    population: list[PlayerMetrics] = []
    candidates: dict[str, SimilarityCandidate] = {}
    player_metrics: dict[str, PlayerMetrics] = {}

    for competition in performance.get_competitions():
        view.competitions[competition.competition_id] = competition.name
        for season in performance.get_seasons(competition.competition_id):
            clubs = {
                c.club_id: c.name
                for c in performance.get_clubs(competition.competition_id, season.season_id)
            }
            view.clubs.update(clubs)

            identities = {
                p.source_player_id: p
                for p in performance.get_players(competition.competition_id, season.season_id)
            }
            for stats in performance.get_competition_stats(
                competition.competition_id, season.season_id
            ):
                identity = identities.get(stats.source_player_id)
                if identity is None:
                    continue

                metrics = compute_derived(stats)
                market_player = market_by_id.get(stats.source_player_id)
                age = _age_at(identity.date_of_birth, REFERENCE_DATE)

                record = PlayerRecord(
                    player_key=stats.source_player_id,
                    full_name=identity.full_name,
                    position_group=identity.position_group,
                    raw_position=identity.raw_position,
                    competition_id=competition.competition_id,
                    competition_name=competition.name,
                    club_id=identity.club_id,
                    club_name=clubs.get(identity.club_id),
                    nationality=identity.nationality,
                    preferred_foot=identity.preferred_foot,
                    height_cm=identity.height_cm,
                    date_of_birth=identity.date_of_birth,
                    age=age,
                    market_value_eur=(market_player.market_value_eur if market_player else None),
                    contract_expires=(market_player.contract_expires if market_player else None),
                    minutes=stats.minutes,
                    sample_band=classify_minutes(stats.minutes),
                    stats=stats,
                    metrics=metrics,
                )
                view.players[record.player_key] = record

                record_metrics = PlayerMetrics(
                    player_key=record.player_key,
                    position_group=record.position_group,
                    competition_id=record.competition_id,
                    season_id=stats.season_id,
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
