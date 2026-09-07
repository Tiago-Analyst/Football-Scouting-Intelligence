"""One player, one place in a cross-competition population.

THE DEFECT

A player who appears in a domestic league, a continental competition and a cup
has three player-seasons in the same season. Every one of them went into the
global comparison population, so the same person entered a single distribution
three times: their form counted three times towards where everybody else
ranked, and a player with three entries pulled the distribution harder than one
with a league season alone.

THE POLICY, WHICH IS OPTION A OF THE BRIEF

For any population spanning more than one competition, a player is represented
by one player-season - the one the site already displays, being the one with
the most minutes. A single competition's own population is untouched: every row
in it belongs to that competition, so there is nothing to deduplicate and a
player whose primary row is elsewhere still played there.

Option B - aggregating totals across competitions and re-deriving rates - is
documented as future work in `docs/multi_competition.md`. It is not done here
because a combined season has no obvious comparison population, and answering
that badly produces an authoritative-looking figure comparable with nothing.
"""

from __future__ import annotations

from app.analytics.metrics import DerivedMetric, DerivedMetrics
from app.analytics.percentiles import (
    MIN_POPULATION,
    PercentileEngine,
    PercentileScope,
    PlayerMetrics,
)
from app.schemas.canonical import PositionGroup

SEASON = "2026/27"
LEAGUE = "liga-portugal"
EUROPE = "champions-league"
CUP = "taca-de-portugal"


def record(
    key: str,
    competition: str,
    passes: float,
    *,
    minutes: int = 900,
    primary: bool = True,
) -> PlayerMetrics:
    return PlayerMetrics(
        player_key=key,
        position_group=PositionGroup.CM,
        competition_id=competition,
        season_id=SEASON,
        metrics=DerivedMetrics(minutes=minutes, passes_per90=passes),
        is_primary=primary,
    )


def filler(count: int, competition: str = LEAGUE) -> list[PlayerMetrics]:
    """Enough distinct players to clear `MIN_POPULATION`."""
    return [record(f"filler-{i}", competition, passes=10.0 + i) for i in range(count)]


class TestTheGlobalPopulationCountsEachPlayerOnce:
    def test_a_players_secondary_seasons_do_not_enter_it(self) -> None:
        population = [
            *filler(MIN_POPULATION),
            record("multi", LEAGUE, passes=90.0, minutes=2000, primary=True),
            record("multi", EUROPE, passes=91.0, minutes=400, primary=False),
            record("multi", CUP, passes=92.0, minutes=200, primary=False),
        ]
        engine = PercentileEngine(population)
        target = population[MIN_POPULATION]

        result = engine.rank(target, DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL)

        assert result.context.population_size == MIN_POPULATION + 1, (
            "the same player entered the global population more than once"
        )

    def test_removing_the_duplicates_changes_where_others_rank(self) -> None:
        """Not a cosmetic count. The duplicates moved everybody else.

        Three entries at the top of the distribution push every other player
        down; one entry pushes them down once. If deduplication did not change
        a single percentile it would not be worth doing.
        """
        others = filler(MIN_POPULATION)
        singleton = [*others, record("multi", LEAGUE, passes=90.0, primary=True)]
        duplicated = [
            *others,
            record("multi", LEAGUE, passes=90.0, primary=True),
            record("multi", EUROPE, passes=90.5, primary=False),
            record("multi", CUP, passes=91.0, primary=False),
        ]
        subject = others[0]

        deduped = PercentileEngine(singleton).rank(
            subject, DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL
        )
        # The same engine, told nothing about primacy, is the old behaviour.
        naive_population = [
            PlayerMetrics(
                player_key=r.player_key,
                position_group=r.position_group,
                competition_id=r.competition_id,
                season_id=r.season_id,
                metrics=r.metrics,
            )
            for r in duplicated
        ]
        naive = PercentileEngine(naive_population).rank(
            subject, DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL
        )

        assert deduped.percentile != naive.percentile

    def test_the_primary_season_is_the_one_that_represents_the_player(self) -> None:
        """And it is rankable itself, against a population of one-each."""
        population = [
            *filler(MIN_POPULATION),
            record("multi", LEAGUE, passes=95.0, minutes=2000, primary=True),
            record("multi", EUROPE, passes=5.0, minutes=90, primary=False),
        ]
        engine = PercentileEngine(population)
        primary = population[MIN_POPULATION]

        result = engine.rank(primary, DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL)

        assert result.percentile is not None
        assert result.context.population_size == MIN_POPULATION + 1


class TestACompetitionsOwnPopulationIsUnchanged:
    def test_every_row_of_that_competition_is_still_in_it(self) -> None:
        """A secondary season is a real season of the competition it belongs to.

        Excluding it here would compare the continental players against a
        population missing whoever plays their league football elsewhere.
        """
        population = [
            *filler(MIN_POPULATION, competition=EUROPE),
            record("multi", LEAGUE, passes=90.0, minutes=2000, primary=True),
            record("multi", EUROPE, passes=91.0, minutes=400, primary=False),
        ]
        engine = PercentileEngine(population)
        european = population[0]

        result = engine.rank(
            european, DerivedMetric.PASSES_PER90, scope=PercentileScope.COMPETITION
        )

        assert result.context.population_size == MIN_POPULATION + 1, (
            "the multi-competition player's European season was dropped from the "
            "European population, where it belongs"
        )

    def test_a_player_ranked_in_their_secondary_competition_still_ranks(self) -> None:
        population = [
            *filler(MIN_POPULATION, competition=EUROPE),
            record("multi", LEAGUE, passes=90.0, minutes=2000, primary=True),
            record("multi", EUROPE, passes=91.0, minutes=400, primary=False),
        ]
        engine = PercentileEngine(population)
        secondary = population[-1]

        result = engine.rank(
            secondary, DerivedMetric.PASSES_PER90, scope=PercentileScope.COMPETITION
        )

        assert result.percentile is not None
        assert result.unavailable_reason is None


class TestALeagueGroupBehavesLikeGlobal:
    """A group spanning competitions has the same defect and takes the same fix."""

    def test_a_player_counts_once_across_the_group(self) -> None:
        population = [
            *filler(MIN_POPULATION),
            record("multi", LEAGUE, passes=90.0, minutes=2000, primary=True),
            record("multi", EUROPE, passes=91.0, minutes=400, primary=False),
        ]
        engine = PercentileEngine(population)
        target = population[0]

        result = engine.rank(
            target,
            DerivedMetric.PASSES_PER90,
            scope=PercentileScope.LEAGUE_GROUP,
            competition_ids=frozenset({LEAGUE, EUROPE}),
        )

        assert result.context.population_size == MIN_POPULATION + 1


class TestNothingElseChanged:
    def test_a_population_of_ordinary_single_competition_players_is_unaffected(self) -> None:
        """`is_primary` defaults to True, so every existing caller is untouched."""
        population = filler(MIN_POPULATION + 5)
        engine = PercentileEngine(population)

        result = engine.rank(
            population[0], DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL
        )

        assert result.context.population_size == MIN_POPULATION + 5

    def test_minutes_still_do_not_exclude_anybody(self) -> None:
        """The product decision, re-asserted where it could quietly regress.

        A one-minute player with a valid rate is in the population like anyone
        else. Deduplication is about people appearing twice, not about how much
        football is behind a figure.
        """
        population = [
            *filler(MIN_POPULATION),
            record("brief", LEAGUE, passes=180.0, minutes=1, primary=True),
        ]
        engine = PercentileEngine(population)
        brief = population[-1]

        result = engine.rank(brief, DerivedMetric.PASSES_PER90, scope=PercentileScope.GLOBAL)

        assert result.percentile is not None
        assert result.context.population_size == MIN_POPULATION + 1
