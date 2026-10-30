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
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES, can_rate
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

    #: Whether this is the player-season that represents the player when a
    #: population spans more than one competition.
    #:
    #: A player who appears in a league, a continental competition and a cup
    #: has three rows in the same season. Against their own league that is
    #: correct - each competition's population contains exactly the players who
    #: played in it. Across competitions it is not: the same person entered a
    #: single distribution three times, so their form counted three times
    #: towards where everyone else ranked, and a player with three entries
    #: pulled the distribution harder than one with a league season alone.
    #:
    #: `build_view` sets this on the row it already chooses to display - the
    #: most minutes played - so the row that represents the player on the site
    #: is the row that represents them in a cross-competition comparison.
    #: Defaulting to True keeps every existing caller and test constructing
    #: single-competition populations behaving exactly as before.
    is_primary: bool = True

    @property
    def minutes(self) -> int | None:
        """The denominator most of this player's rates divide by."""
        return self.metrics.minutes

    @property
    def rateable_minutes(self) -> int | None:
        """The largest denominator this player has any rate under.

        There are two, and they can differ: goals, assists and goals conceded
        divide by time on the pitch, everything else by the minutes the
        detailed feed describes. See `app.analytics.denominators`.

        Eligibility asks whether the player has *any* rate at all, so it takes
        whichever is available. Using the detailed figure alone would drop a
        player whose detailed feed covers nothing out of every population,
        including the goalscoring ones their playing minutes fully support -
        which would be a minutes-based exclusion arriving through the back
        door, and there are none of those by deliberate product decision.

        The per-metric answer is still per-metric: a metric whose own
        denominator is missing comes out `None` and is skipped when the values
        are collected, so nothing is ranked against a rate it does not have.
        """
        candidates = [m for m in (self.metrics.minutes, self.metrics.playing_minutes) if m]
        return max(candidates) if candidates else None


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

    # -- How far into their seasons this population is ----------------------
    #
    # A percentile against "all covered competitions" sounds like a comparison
    # with the wider game. On the loaded data most of that population has
    # barely started its season, so the rank is largely against a handful of
    # matches - and how few depends on the position, because a goalkeeper
    # accumulates minutes faster than a forward.
    #
    # The figures are NOT repeated here. They change with every generation,
    # and the copy that used to sit in this comment outlived the data by
    # weeks. `docs/methodology.md` carries them, per position group and with
    # the date they were measured; the fields below report them per request.
    #
    # None of that makes the percentile wrong - it is an honest rank within
    # the population it names. It makes it easy to misread as something
    # broader, and the only thing missing was a way to say so. Nothing here
    # changes a number; it describes the room.
    #: How many competitions contributed a player to this population.
    competitions_in_population: int = 0
    #: How many of those contain a player who has reached a full season's
    #: minutes, so a season-long figure from them is possible at all.
    competitions_established: int = 0
    #: Share of the population drawn from those, 0-1.
    established_share: float = 1.0
    #: The median minutes behind the figures being ranked.
    median_minutes: int = 0

    @property
    def is_early_season(self) -> bool:
        """True when most of this population has not played much football yet."""
        return self.competitions_in_population > 1 and self.established_share < 0.5

    @property
    def maturity_note(self) -> str | None:
        """What the population is made of, when that is worth saying.

        Returned beside the percentile rather than folded into it. A reader
        deciding whether to trust an all-leagues rank needs to know that most
        of the players in it have played two matches; a reader looking at a
        single mature competition does not need a sentence about it.
        """
        if self.competitions_in_population <= 1:
            return None
        established = self.competitions_established
        total = self.competitions_in_population
        if established == total:
            return None
        return (
            f"{total} competitions, of which {established} have played enough of their "
            f"season for a full-season figure to be possible. "
            f"{self.established_share * 100:.0f}% of this population comes from those, and "
            f"the median player here has {self.median_minutes:,} minutes. "
            f"A rank against the rest is a rank against a season that has barely started."
        )

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


@dataclass(frozen=True)
class _Maturity:
    """How far into their seasons a population's competitions are."""

    competitions: int
    established: int
    established_share: float
    median_minutes: int


class PercentileEngine:
    """Ranks players against position-scoped populations.

    Everyone whose figure exists is in the population. There is no minutes
    threshold: minutes band a figure for the reader, they do not decide who is
    compared. The one rule is arithmetic - a per-90 needs a denominator - and
    it is `can_rate`, not an editorial judgement about who has played enough.

    A caller may still pass `minimum_minutes` deliberately; nothing does by
    default.
    """

    def __init__(
        self,
        population: list[PlayerMetrics],
        *,
        # No floor. `can_rate` admits anyone with a positive denominator, which
        # is everyone who has a per-90 at all.
        #
        # This used to default to LOW_SAMPLE_MINUTES, which emptied every
        # competition whose season had just begun: no population, no
        # percentile, and a working engine reporting nothing. A player with no
        # recorded minutes is still excluded, because they have no rate to
        # contribute - counting them would only inflate the population size
        # reported beside the percentile, and that number answers a reader's
        # question "compared against how many?".
        minimum_minutes: int | None = None,
        min_population: int = MIN_POPULATION,
    ) -> None:
        self.minimum_minutes = minimum_minutes
        self.min_population = min_population
        # Asks "does this player have a rate at all", and nothing else.
        #
        # `rateable_minutes` rather than `minutes` because there are two
        # denominators and a player can have one without the other. A
        # goalkeeper whose detailed feed covers nothing still has a conceding
        # rate over the minutes they played, and dropping them here would
        # exclude them from every population on a minutes test - which this
        # project does not have.
        self._eligible = [
            record
            for record in population
            if can_rate(record.rateable_minutes, at_least=minimum_minutes)
        ]
        self._by_group: dict[tuple[PositionGroup, str], list[PlayerMetrics]] = defaultdict(list)
        for record in self._eligible:
            self._by_group[(record.position_group, record.season_id)].append(record)
        self._cache: dict[tuple, list[float]] = {}
        #: Season maturity per population, memoised on the same grounds as
        #: `_cache`: the populations above are built once in this constructor
        #: and never mutated, so the answer for a given population cannot
        #: change within an engine's life.
        #:
        #: Without this the measurement ran once per metric per player. A
        #: recruitment search over 947 candidates called it 30,304 times, each
        #: walking the whole population, and spent 32 of its 34 seconds here -
        #: past the thirty the frontend waits, so every brief that matched
        #: anybody failed in production. See `test_percentile_performance.py`.
        self._maturity_cache: dict[tuple, _Maturity] = {}

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
            # Global: one row per player. See `PlayerMetrics.is_primary`.
            return [r for r in records if r.is_primary]
        if len(competition_ids) == 1:
            # A single competition's own population. Every row in it belongs to
            # a different player-season *of that competition*, so there is
            # nothing to deduplicate and a player whose primary row is
            # elsewhere still belongs here.
            return [r for r in records if r.competition_id in competition_ids]
        # A league group spans competitions, so it has the same defect global
        # had and takes the same answer. A player whose primary row falls
        # outside the group is represented by nothing here rather than by a
        # secondary row: including one would compare a cup appearance against
        # other players' league seasons, which is the confusion the primary row
        # exists to avoid.
        return [r for r in records if r.is_primary and r.competition_id in competition_ids]

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
        maturity = self._maturity(position_group, season_id, competition_ids)
        return ComparisonContext(
            scope=scope,
            position_group=position_group,
            season_id=season_id,
            competition_ids=tuple(covered),
            population_size=population_size,
            # Nought where no floor was applied, which is the default. The
            # field reports the bar a reader had to clear to be in this
            # population; "none" and "zero" are the same bar.
            minimum_minutes=self.minimum_minutes or 0,
            competitions_in_population=maturity.competitions,
            competitions_established=maturity.established,
            established_share=maturity.established_share,
            median_minutes=maturity.median_minutes,
        )

    def _maturity(
        self,
        position_group: PositionGroup,
        season_id: str,
        competition_ids: frozenset[str] | None,
    ) -> _Maturity:
        """How far into their seasons the players in this population are.

        Measured from the population itself rather than configured, so it
        cannot go stale: as a season progresses the figures move on their own,
        and when every competition has played enough the note stops appearing.

        A competition counts as established when one of its players has
        reached the Established Sample threshold - meaning a full season's
        evidence is possible there at all, not that everyone has it.
        """
        key = (position_group, season_id, competition_ids)
        memoised = self._maturity_cache.get(key)
        if memoised is not None:
            return memoised
        measured = self._measure_maturity(position_group, season_id, competition_ids)
        self._maturity_cache[key] = measured
        return measured

    def _measure_maturity(
        self,
        position_group: PositionGroup,
        season_id: str,
        competition_ids: frozenset[str] | None,
    ) -> _Maturity:
        """The walk itself, separated so the memo above has one job."""
        records = self._population_for(position_group, season_id, competition_ids)
        if not records:
            return _Maturity(0, 0, 1.0, 0)
        best: dict[str, int] = {}
        minutes: list[int] = []
        for record in records:
            played = record.rateable_minutes or 0
            minutes.append(played)
            best[record.competition_id] = max(best.get(record.competition_id, 0), played)
        established = {c for c, top in best.items() if top >= ESTABLISHED_SAMPLE_MINUTES}
        from_established = sum(1 for r in records if r.competition_id in established)
        minutes.sort()
        return _Maturity(
            competitions=len(best),
            established=len(established),
            established_share=from_established / len(records),
            median_minutes=int(minutes[len(minutes) // 2]),
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

        if len(values) < self.min_population and selected is not None:
            # Too few comparable players in this competition - widen rather
            # than refuse.
            #
            # A rank against four players is noise wearing a number, so the
            # floor below stays. But refusing was answering "we cannot compare
            # him" when the truthful answer is "not against his own league,
            # yet". Four matches into a season a Portuguese midfielder has
            # fifteen league peers and nearly six hundred across every loaded
            # competition, and the second comparison is a real one.
            #
            # It is a weaker comparison, and the context says so: the scope
            # comes back as GLOBAL, the competitions it covered are listed, and
            # the cross-league caveat travels with it - the same caveat that
            # governs every deliberate cross-league percentile, because the
            # specification forbids inventing a league-strength coefficient
            # rather than admitting the difference.
            wider = self._sorted_values(metric, player.position_group, player.season_id, None)
            if len(wider) >= self.min_population:
                values = wider
                context = self._context(
                    PercentileScope.GLOBAL,
                    player.position_group,
                    player.season_id,
                    None,
                    len(wider),
                )

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
