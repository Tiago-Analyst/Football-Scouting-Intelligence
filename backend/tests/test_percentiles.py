"""Percentile engine.

The interesting cases are ties, small populations, and keeping the comparison
context attached to the number. A percentile that looks precise but was computed
against eight players, or against the wrong position group, is worse than no
percentile at all.
"""

from __future__ import annotations

import pytest

from app.analytics.metrics import DerivedMetric, DerivedMetrics
from app.analytics.percentiles import (
    CROSS_LEAGUE_CAVEAT,
    ComparisonContext,
    PercentileEngine,
    PercentileScope,
    PlayerMetrics,
    percentile_of,
)
from app.schemas.canonical import PositionGroup

SEASON = "2026-2027"


def player(
    key: str,
    *,
    group: PositionGroup = PositionGroup.CM,
    competition: str = "c1",
    minutes: int = 2000,
    **metrics: float | None,
) -> PlayerMetrics:
    return PlayerMetrics(
        player_key=key,
        position_group=group,
        competition_id=competition,
        season_id=SEASON,
        metrics=DerivedMetrics(minutes=minutes, **metrics),  # type: ignore[arg-type]
    )


def cohort(
    values: list[float],
    *,
    metric: str = "progressive_passes_per90",
    group: PositionGroup = PositionGroup.CM,
    competition: str = "c1",
    minutes: int = 2000,
) -> list[PlayerMetrics]:
    return [
        player(
            f"{competition}-{i}",
            group=group,
            competition=competition,
            minutes=minutes,
            **{metric: v},
        )
        for i, v in enumerate(values)
    ]


class TestPercentileOf:
    def test_the_lowest_and_highest_values_sit_at_the_extremes(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile_of(1.0, values) == pytest.approx(10.0)
        assert percentile_of(5.0, values) == pytest.approx(90.0)

    def test_the_median_sits_in_the_middle(self) -> None:
        assert percentile_of(3.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(50.0)

    def test_tied_values_share_a_percentile(self) -> None:
        """Otherwise the many players on a repeated value would be ordered
        against each other by nothing but list position."""
        values = [0.0, 0.0, 0.0, 0.0, 5.0]
        assert percentile_of(0.0, values) == pytest.approx(40.0)

    def test_a_value_above_everything_does_not_exceed_one_hundred(self) -> None:
        assert percentile_of(99.0, [1.0, 2.0, 3.0]) == pytest.approx(100.0)

    def test_an_empty_population_is_an_error_not_a_zero(self) -> None:
        with pytest.raises(ValueError, match="empty population"):
            percentile_of(1.0, [])


class TestPositionScoping:
    def test_a_player_is_ranked_only_against_their_own_position_group(self) -> None:
        """A centre-back's tackling measured against forwards is meaningless."""
        midfielders = cohort([1.0] * 20, group=PositionGroup.CM)
        defenders = cohort([9.0] * 20, group=PositionGroup.CB)
        engine = PercentileEngine(midfielders + defenders)

        target = player("target", group=PositionGroup.CM, progressive_passes_per90=1.0)
        result = engine.rank(target, DerivedMetric.PROGRESSIVE_PASSES_PER90)

        assert result.context.position_group is PositionGroup.CM
        assert result.context.population_size == 20
        # Ranked mid-pack among midfielders, not bottom against the defenders.
        assert result.percentile == pytest.approx(50.0)

    def test_a_group_without_enough_players_yields_no_percentile(self) -> None:
        engine = PercentileEngine(cohort([1.0] * 5))
        result = engine.rank(
            player("t", progressive_passes_per90=1.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert result.percentile is None
        assert result.unavailable_reason is not None
        assert "too small" in result.unavailable_reason


class TestScopes:
    @pytest.fixture
    def engine(self) -> PercentileEngine:
        # One weak competition and one strong one.
        return PercentileEngine(
            cohort([1.0] * 15, competition="weak") + cohort([9.0] * 15, competition="strong")
        )

    def test_competition_scope_uses_only_the_players_own_league(
        self, engine: PercentileEngine
    ) -> None:
        target = player("t", competition="weak", progressive_passes_per90=1.0)
        result = engine.rank(target, DerivedMetric.PROGRESSIVE_PASSES_PER90)
        assert result.context.scope is PercentileScope.COMPETITION
        assert result.context.competition_ids == ("weak",)
        assert result.percentile == pytest.approx(50.0)

    def test_global_scope_spans_every_competition(self, engine: PercentileEngine) -> None:
        target = player("t", competition="weak", progressive_passes_per90=1.0)
        result = engine.rank(
            target, DerivedMetric.PROGRESSIVE_PASSES_PER90, scope=PercentileScope.GLOBAL
        )
        assert result.context.scope is PercentileScope.GLOBAL
        assert result.context.population_size == 30
        # Bottom half once the stronger league is included.
        assert result.percentile == pytest.approx(25.0)

    def test_league_group_scope_uses_the_selected_competitions(
        self, engine: PercentileEngine
    ) -> None:
        target = player("t", competition="weak", progressive_passes_per90=1.0)
        result = engine.rank(
            target,
            DerivedMetric.PROGRESSIVE_PASSES_PER90,
            scope=PercentileScope.LEAGUE_GROUP,
            competition_ids=frozenset({"weak", "strong"}),
        )
        assert result.context.scope is PercentileScope.LEAGUE_GROUP
        assert sorted(result.context.competition_ids) == ["strong", "weak"]

    def test_a_league_group_without_competitions_is_rejected(
        self, engine: PercentileEngine
    ) -> None:
        with pytest.raises(ValueError, match="requires competition_ids"):
            engine.rank(
                player("t", progressive_passes_per90=1.0),
                DerivedMetric.PROGRESSIVE_PASSES_PER90,
                scope=PercentileScope.LEAGUE_GROUP,
            )


class TestComparisonContext:
    def test_the_context_is_always_returned(self) -> None:
        """Section 25: the reference population must never be hidden."""
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(
            player("t", progressive_passes_per90=5.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert isinstance(result.context, ComparisonContext)
        assert result.context.label
        assert result.context.population_size == 20

    def test_a_single_competition_carries_no_cross_league_caveat(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(
            player("t", progressive_passes_per90=5.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert result.context.caveat is None

    def test_a_multi_competition_context_carries_the_caveat(self) -> None:
        """Cross-league percentiles are not strength-adjusted, and that warning
        travels with the context so it cannot be dropped downstream."""
        engine = PercentileEngine(
            cohort([1.0] * 15, competition="a") + cohort([2.0] * 15, competition="b")
        )
        result = engine.rank(
            player("t", competition="a", progressive_passes_per90=1.0),
            DerivedMetric.PROGRESSIVE_PASSES_PER90,
            scope=PercentileScope.GLOBAL,
        )
        assert result.context.caveat == CROSS_LEAGUE_CAVEAT

    def test_no_context_ever_claims_to_be_strength_adjusted(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(
            player("t", progressive_passes_per90=5.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert result.context.strength_adjusted is False


class TestOrientation:
    def test_a_normal_metric_keeps_its_direction(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(
            player("t", progressive_passes_per90=19.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert result.lower_is_better is False
        assert result.oriented == pytest.approx(result.percentile)

    def test_an_inverse_metric_is_flipped_for_scoring(self) -> None:
        """Being dispossessed often ranks high on the raw metric and badly on
        quality. Storing the raw rank keeps the number meaning what its name
        says; `oriented` is what scoring consumes."""
        engine = PercentileEngine(
            cohort([float(i) for i in range(20)], metric="dispossessed_per90")
        )
        result = engine.rank(player("t", dispossessed_per90=19.0), DerivedMetric.DISPOSSESSED_PER90)
        assert result.lower_is_better is True
        assert result.percentile == pytest.approx(97.5)
        assert result.oriented == pytest.approx(2.5)

    def test_oriented_percentiles_are_ready_for_scoring(self) -> None:
        engine = PercentileEngine(
            cohort([float(i) for i in range(20)], metric="dispossessed_per90")
        )
        values = engine.oriented_percentiles(
            player("t", dispossessed_per90=0.0), [DerivedMetric.DISPOSSESSED_PER90]
        )
        # Losing the ball least often is the best outcome.
        assert values[DerivedMetric.DISPOSSESSED_PER90] == pytest.approx(97.5)


class TestSampleSizeHandling:
    def test_everyone_with_minutes_defines_the_distribution(self) -> None:
        """The floor this used to assert is gone, deliberately.

        A 450-minute floor kept short seasons out of the population, which is
        right in March and ruinous in August: four matches into 2026/27 nobody
        in the Portuguese league cleared it, the population was empty, and no
        percentile could be computed for anyone there. A working engine
        reported nothing because its own guard had excluded everybody.

        What the floor protected against is real - a ninety-minute cameo can
        pull a distribution built from full seasons - and it is now carried by
        saying so rather than by hiding people: every figure travels with the
        minutes behind it and the size of the population it was measured
        against.

        A caller who wants the old behaviour passes `minimum_minutes`.
        """
        established = cohort([1.0] * 20, minutes=2000)
        brief = cohort([50.0] * 20, competition="c1", minutes=100)
        engine = PercentileEngine(established + brief)
        assert engine.eligible_count == 40

        guarded = PercentileEngine(established + brief, minimum_minutes=450)
        assert guarded.eligible_count == 20

    def test_a_small_sample_player_can_still_be_ranked(self) -> None:
        """Their figures are shown with a warning, not withheld."""
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(
            player("t", minutes=120, progressive_passes_per90=10.0),
            DerivedMetric.PROGRESSIVE_PASSES_PER90,
        )
        assert result.percentile is not None

    def test_the_minutes_threshold_is_configurable(self) -> None:
        engine = PercentileEngine(cohort([1.0] * 20, minutes=300), minimum_minutes=200)
        assert engine.eligible_count == 20


class TestMissingValues:
    def test_a_player_without_the_metric_gets_no_percentile(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        result = engine.rank(player("t"), DerivedMetric.PROGRESSIVE_PASSES_PER90)
        assert result.percentile is None
        assert result.unavailable_reason == "metric not available for this player"

    def test_players_missing_a_metric_are_excluded_from_its_population(self) -> None:
        """They must not be counted as zero, which would drag the whole
        distribution down."""
        with_values = cohort([10.0] * 15)
        without = [player(f"n{i}", minutes=2000) for i in range(50)]
        engine = PercentileEngine(with_values + without)
        result = engine.rank(
            player("t", progressive_passes_per90=10.0), DerivedMetric.PROGRESSIVE_PASSES_PER90
        )
        assert result.context.population_size == 15
        assert result.percentile == pytest.approx(50.0)


class TestRankAll:
    def test_ranks_every_requested_metric(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        results = engine.rank_all(
            player("t", progressive_passes_per90=5.0),
            [DerivedMetric.PROGRESSIVE_PASSES_PER90, DerivedMetric.TACKLES_PER90],
        )
        assert set(results) == {
            DerivedMetric.PROGRESSIVE_PASSES_PER90,
            DerivedMetric.TACKLES_PER90,
        }
        assert results[DerivedMetric.TACKLES_PER90].percentile is None

    def test_defaults_to_every_metric(self) -> None:
        engine = PercentileEngine(cohort([float(i) for i in range(20)]))
        results = engine.rank_all(player("t", progressive_passes_per90=5.0))
        assert len(results) == len(list(DerivedMetric))


class TestAgainstTheMockDataset:
    def test_percentiles_stay_within_range_across_the_whole_cohort(self) -> None:
        from app.analytics.metrics import compute_derived
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=2, clubs_per_competition=10)
        population: list[PlayerMetrics] = []
        for competition in provider.get_competitions():
            groups = {
                p.source_player_id: p.position_group
                for p in provider.get_players(competition.competition_id, SEASON_ID)
            }
            for record in provider.get_competition_stats(competition.competition_id, SEASON_ID):
                population.append(
                    PlayerMetrics(
                        player_key=record.source_player_id,
                        position_group=groups[record.source_player_id],
                        competition_id=record.competition_id,
                        season_id=record.season_id,
                        metrics=compute_derived(record),
                    )
                )

        engine = PercentileEngine(population)
        checked = 0
        for record in population[:200]:
            for result in engine.rank_all(
                record, [DerivedMetric.PROGRESSIVE_PASSES_PER90, DerivedMetric.TACKLES_PER90]
            ).values():
                if result.percentile is not None:
                    assert 0.0 <= result.percentile <= 100.0
                    assert 0.0 <= (result.oriented or 0.0) <= 100.0
                    checked += 1
        assert checked > 0
