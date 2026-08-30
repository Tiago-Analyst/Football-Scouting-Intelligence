"""Percentile engine.

A per-90 figure is hard to read without knowing what is normal. 5.4 progressive
passes per 90 is unremarkable for a deep-lying midfielder and exceptional for a
striker, so every metric is also expressed as a rank within a comparable
population.

Four decisions shape this module:

**The population is always position-scoped.** Comparing a centre-back's tackling
against forwards produces a number that means nothing (spec section 8).

**Ties share a percentile.** Many metrics are dominated by repeated values — a
squad's worth of defenders with zero shots on target. Mid-rank scoring gives
identical values identical percentiles, so no player is ranked above another by
accident of list order.

**The comparison population is part of the result, never implied.** A percentile
without its reference group is uninterpretable, and section 25 requires the
context to be displayed rather than assumed.

**Cross-league percentiles are not strength-adjusted.** No competition-strength
coefficient is applied, because an unvalidated one would introduce error while
looking authoritative. Any context spanning more than one competition carries
that caveat with it so it cannot be dropped downstream.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from app.analytics.metrics import LOWER_IS_BETTER, DerivedMetric, DerivedMetrics
from app.analytics.sample import is_rankable
from app.schemas.canonical import PositionGroup

#: Fewer comparable players than this and a percentile is noise dressed as
#: precision: with eight players, each rank step is worth 12 percentile points.
MIN_POPULATION = 10

CROSS_LEAGUE_CAVEAT = (
    "Cross-league percentiles do not currently account for differences in competition strength."
)


class PercentileScope(StrEnum):
    """Which competitions form the comparison population (spec section 25)."""

    COMPETITION = "competition"
    LEAGUE_GROUP = "league_group"
    GLOBAL = "global"


@dataclass(frozen=True)
class PlayerMetrics:
    """One player-season's derived metrics, with what is needed to place them."""

    player_key: str
    position_group: PositionGroup
    competition_id: str
    season_id: str
    metrics: DerivedMetrics

    @property
    def minutes(self) -> int | None:
        return self.metrics.minutes


@dataclass(frozen=True)
class ComparisonContext:
    """The population a percentile was measured against.

    Returned with every percentile because a rank without its reference group
    cannot be interpreted. `caveat` carries the cross-league warning so a
    multi-competition comparison cannot be presented without it.
    """

    scope: PercentileScope
    position_group: PositionGroup
    season_id: str
    competition_ids: tuple[str, ...]
    population_size: int
    minimum_minutes: int

    #: Always False. Recorded explicitly rather than left implicit so that any
    #: future strength model has to change this deliberately.
    strength_adjusted: bool = False

    @property
    def label(self) -> str:
        """Short description of the population, for display beside the number."""
        if self.scope is PercentileScope.COMPETITION and self.competition_ids:
            where = self.competition_ids[0]
        elif self.scope is PercentileScope.GLOBAL:
            where = "all covered competitions"
        else:
            where = f"{len(self.competition_ids)} competitions"
        return f"{self.position_group.value} · {where} · {self.season_id}"

    @property
    def caveat(self) -> str | None:
        return CROSS_LEAGUE_CAVEAT if len(self.competition_ids) > 1 else None


@dataclass(frozen=True)
class PercentileResult:
    """One metric's rank within one population."""

    metric: DerivedMetric
    value: float | None
    #: Rank of the raw metric, 0-100. Reads in the metric's own direction: a
    #: high percentile for `dispossessed_per90` means dispossessed often.
    percentile: float | None
    #: Same rank oriented so higher is always better. This is what scoring
    #: consumes; `percentile` is what a metric table displays.
    oriented: float | None
    lower_is_better: bool
    context: ComparisonContext
    #: Why no percentile was produced, when there is none.
    unavailable_reason: str | None = None

    @property
    def is_available(self) -> bool:
        return self.percentile is not None


def percentile_of(value: float, sorted_values: list[float]) -> float:
    """Mid-rank percentile of `value` within `sorted_values`, 0-100.

    Averages the strict and weak ranks, which is what makes tied values share a
    percentile. The alternative — counting only values strictly below — would
    put every player on a tied value at the bottom of that group, so the many
    defenders with zero shots on target would all rank 0th while a single player
    with one shot jumped far above them.
    """
    if not sorted_values:
        raise ValueError("cannot compute a percentile against an empty population")
    below = bisect_left(sorted_values, value)
    at_or_below = bisect_right(sorted_values, value)
    return 100.0 * (below + at_or_below) / (2 * len(sorted_values))


class PercentileEngine:
    """Ranks players against position-scoped populations.

    The population is drawn from players who meet the minutes threshold, because
    a per-90 rate from 200 minutes is noise and would distort the distribution
    everyone else is measured against. Any player can still be *scored* against
    it, including one below the threshold — their figures are then shown with a
    sample-size warning rather than hidden.
    """

    def __init__(
        self,
        population: list[PlayerMetrics],
        *,
        # Having played at all - no more than that. This was
        # LOW_SAMPLE_MINUTES, which emptied every competition whose season had
        # just begun: no population, no percentile, and a working engine
        # reporting nothing.
        #
        # One rather than nought, because a player with no minutes has no
        # per-90 to contribute. They would never affect a distribution, only
        # inflate the population size reported beside it - and that number is
        # shown to a reader as the answer to "compared against how many?".
        #
        # A caller that wants a real floor still passes one.
        minimum_minutes: int = 1,
        min_population: int = MIN_POPULATION,
    ) -> None:
        self.minimum_minutes = minimum_minutes
        self.min_population = min_population
        # Only players with enough minutes define the distribution.
        self._eligible = [
            record
            for record in population
            if is_rankable(record.minutes, minimum_minutes=minimum_minutes)
        ]
        self._by_group: dict[tuple[PositionGroup, str], list[PlayerMetrics]] = defaultdict(list)
        for record in self._eligible:
            self._by_group[(record.position_group, record.season_id)].append(record)
        self._cache: dict[tuple, list[float]] = {}

    @property
    def eligible_count(self) -> int:
        return len(self._eligible)

    def _population_for(
        self,
        position_group: PositionGroup,
        season_id: str,
        competition_ids: frozenset[str] | None,
    ) -> list[PlayerMetrics]:
        records = self._by_group.get((position_group, season_id), [])
        if competition_ids is None:
            return records
        return [r for r in records if r.competition_id in competition_ids]

    def _sorted_values(
        self,
        metric: DerivedMetric,
        position_group: PositionGroup,
        season_id: str,
        competition_ids: frozenset[str] | None,
    ) -> list[float]:
        key = (metric, position_group, season_id, competition_ids)
        cached = self._cache.get(key)
        if cached is None:
            values = [
                value
                for record in self._population_for(position_group, season_id, competition_ids)
                if (value := record.metrics.get(metric)) is not None
            ]
            values.sort()
            self._cache[key] = values
            cached = values
        return cached

    def _context(
        self,
        scope: PercentileScope,
        position_group: PositionGroup,
        season_id: str,
        competition_ids: frozenset[str] | None,
        population_size: int,
    ) -> ComparisonContext:
        if competition_ids is None:
            covered = sorted(
                {r.competition_id for r in self._by_group.get((position_group, season_id), [])}
            )
        else:
            covered = sorted(competition_ids)
        return ComparisonContext(
            scope=scope,
            position_group=position_group,
            season_id=season_id,
            competition_ids=tuple(covered),
            population_size=population_size,
            minimum_minutes=self.minimum_minutes,
        )

    def rank(
        self,
        player: PlayerMetrics,
        metric: DerivedMetric,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> PercentileResult:
        """Rank one player on one metric within the requested population.

        `competition_ids` is required for a league-group scope and ignored
        otherwise: a competition scope always uses the player's own competition,
        and a global scope uses everything covered.
        """
        if scope is PercentileScope.COMPETITION:
            selected: frozenset[str] | None = frozenset({player.competition_id})
        elif scope is PercentileScope.GLOBAL:
            selected = None
        else:
            if not competition_ids:
                raise ValueError("a league_group scope requires competition_ids")
            selected = frozenset(competition_ids)

        lower_is_better = metric in LOWER_IS_BETTER
        values = self._sorted_values(metric, player.position_group, player.season_id, selected)
        context = self._context(
            scope, player.position_group, player.season_id, selected, len(values)
        )
        value = player.metrics.get(metric)

        def unavailable(reason: str) -> PercentileResult:
            return PercentileResult(
                metric=metric,
                value=value,
                percentile=None,
                oriented=None,
                lower_is_better=lower_is_better,
                context=context,
                unavailable_reason=reason,
            )

        if value is None:
            return unavailable("metric not available for this player")
        if len(values) < self.min_population:
            # Better to show nothing than a rank derived from a handful of
            # players, which would look equally precise and be far less true.
            return unavailable(
                f"comparison population too small ({len(values)} < {self.min_population})"
            )

        raw = percentile_of(value, values)
        return PercentileResult(
            metric=metric,
            value=value,
            percentile=raw,
            oriented=100.0 - raw if lower_is_better else raw,
            lower_is_better=lower_is_better,
            context=context,
        )

    def rank_all(
        self,
        player: PlayerMetrics,
        metrics: list[DerivedMetric] | None = None,
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> dict[DerivedMetric, PercentileResult]:
        """Rank a player across every metric, or a chosen subset."""
        chosen = metrics if metrics is not None else list(DerivedMetric)
        return {
            metric: self.rank(player, metric, scope=scope, competition_ids=competition_ids)
            for metric in chosen
        }

    def oriented_percentiles(
        self,
        player: PlayerMetrics,
        metrics: list[DerivedMetric],
        *,
        scope: PercentileScope = PercentileScope.COMPETITION,
        competition_ids: frozenset[str] | None = None,
    ) -> dict[DerivedMetric, float | None]:
        """Higher-is-better percentiles, ready to feed the scoring utilities.

        This is the boundary section 9 describes: components arrive at
        `weighted_score` already on one 0-100 scale, so no raw metric is ever
        weighted directly.
        """
        ranked = self.rank_all(player, metrics, scope=scope, competition_ids=competition_ids)
        return {metric: result.oriented for metric, result in ranked.items()}
