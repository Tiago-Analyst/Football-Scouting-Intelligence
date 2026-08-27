"""Derived metrics.

The arithmetic is trivial; the edge cases are not. Almost every test here is
about a division that has no answer, and about keeping "we do not know" distinct
from "it is zero". Getting either wrong does not raise — it produces a plausible
number that quietly corrupts every percentile built on it.
"""

from __future__ import annotations

import pytest

from app.analytics.metrics import (
    LOWER_IS_BETTER,
    PERCENTAGE_METRICS,
    DerivedMetric,
    DerivedMetrics,
    compute_derived,
    per90,
    percentage,
    ratio,
    subtract,
)
from app.schemas.canonical import PlayerSeasonStats

IDENTITY = {
    "source_player_id": "p1",
    "season_id": "2026-2027",
    "competition_id": "c1",
    "club_id": "club1",
}


def stats(**metrics: object) -> PlayerSeasonStats:
    return PlayerSeasonStats(**IDENTITY, **metrics)  # type: ignore[arg-type]


class TestPer90:
    def test_scales_a_total_to_ninety_minutes(self) -> None:
        assert per90(10, 900) == pytest.approx(1.0)
        assert per90(5, 450) == pytest.approx(1.0)

    def test_a_full_season_rate(self) -> None:
        assert per90(18, 2700) == pytest.approx(0.6)

    def test_absent_total_stays_absent(self) -> None:
        assert per90(None, 900) is None

    def test_absent_minutes_stays_absent(self) -> None:
        assert per90(10, None) is None

    def test_zero_minutes_is_undefined_not_infinite(self) -> None:
        """Nothing happened in no time; there is no rate to report."""
        assert per90(10, 0) is None

    def test_a_genuine_zero_total_gives_a_zero_rate(self) -> None:
        """Distinct from the cases above: this player played and did none."""
        assert per90(0, 900) == 0.0


class TestRatioAndPercentage:
    def test_ratio_is_a_proportion(self) -> None:
        assert ratio(30, 40) == pytest.approx(0.75)

    def test_percentage_is_the_same_on_a_hundred_scale(self) -> None:
        assert percentage(30, 40) == pytest.approx(75.0)

    def test_zero_denominator_is_undefined_not_zero(self) -> None:
        """A player with no attempts has no success rate. Reporting 0% would
        rank them below everyone who attempted and failed."""
        assert ratio(0, 0) is None
        assert percentage(0, 0) is None

    def test_zero_numerator_over_real_attempts_is_zero(self) -> None:
        """This player did attempt, and succeeded none of the time."""
        assert percentage(0, 20) == 0.0

    def test_absent_inputs_propagate(self) -> None:
        assert ratio(None, 40) is None
        assert ratio(30, None) is None


class TestSubtract:
    def test_subtracts(self) -> None:
        assert subtract(40, 5) == 35

    def test_absence_propagates_rather_than_assuming_zero(self) -> None:
        """Treating unknown penalties as zero would overstate open-play shot
        volume for every penalty taker."""
        assert subtract(40, None) is None
        assert subtract(None, 5) is None


class TestMetricEnumStaysInSync:
    def test_enum_matches_the_model_fields(self) -> None:
        identity_fields = {
            "player_id",
            "source_player_id",
            "season_id",
            "competition_id",
            "minutes",
        }
        model_metrics = set(DerivedMetrics.model_fields) - identity_fields
        assert model_metrics == {m.value for m in DerivedMetric}

    def test_inverse_and_percentage_sets_name_real_metrics(self) -> None:
        for metric in LOWER_IS_BETTER | PERCENTAGE_METRICS:
            assert metric in set(DerivedMetric)


class TestComputeDerived:
    def test_computes_rates_from_totals(self) -> None:
        derived = compute_derived(
            stats(minutes=2700, goals=18, passes=1800, progressive_passes=180)
        )
        assert derived.goals_per90 == pytest.approx(0.6)
        assert derived.passes_per90 == pytest.approx(60.0)
        assert derived.progressive_passes_per90 == pytest.approx(6.0)

    def test_computes_percentages_from_pairs(self) -> None:
        derived = compute_derived(
            stats(minutes=2700, passes=1000, passes_completed=870, duels=300, duels_won=165)
        )
        assert derived.pass_completion == pytest.approx(87.0)
        assert derived.duel_win_percentage == pytest.approx(55.0)

    def test_unsupplied_metric_yields_no_derived_value(self) -> None:
        """A provider that does not carry tackles must not produce a tackle rate
        of zero, which would rank the player as the worst defender in the pool."""
        derived = compute_derived(stats(minutes=2700, goals=10))
        assert derived.tackles_per90 is None
        assert derived.tackle_success_percentage is None

    def test_a_player_with_no_minutes_has_no_rates(self) -> None:
        derived = compute_derived(stats(minutes=0, goals=0, passes=0))
        assert derived.goals_per90 is None
        assert derived.passes_per90 is None

    def test_no_attempts_means_no_success_rate(self) -> None:
        derived = compute_derived(stats(minutes=2700, dribbles=0, successful_dribbles=0))
        assert derived.dribbles_per90 == 0.0
        assert derived.dribble_success_percentage is None


class TestFinishingMetrics:
    def test_shot_conversion_excludes_penalties(self) -> None:
        """40 shots of which 5 were penalties leaves 35 open-play shots; 7
        non-penalty goals is 20%. Including penalties would credit a player for
        converting from twelve yards."""
        derived = compute_derived(
            stats(minutes=2700, shots=40, penalties_taken=5, non_penalty_goals=7, goals=11)
        )
        assert derived.shot_conversion == pytest.approx(20.0)

    def test_shot_quality_is_npxg_per_non_penalty_shot(self) -> None:
        derived = compute_derived(stats(minutes=2700, shots=40, penalties_taken=5, npxg=7.0))
        assert derived.shot_quality == pytest.approx(0.2)

    def test_shot_quality_is_absent_when_penalties_are_unknown(self) -> None:
        """Assuming zero penalties would inflate open-play chance quality."""
        derived = compute_derived(stats(minutes=2700, shots=40, npxg=7.0))
        assert derived.shot_quality is None

    def test_shot_accuracy_uses_all_shots(self) -> None:
        derived = compute_derived(stats(minutes=2700, shots=40, shots_on_target=16))
        assert derived.shot_accuracy == pytest.approx(40.0)


class TestGoalkeeperMetrics:
    def test_save_percentage_is_saves_over_shots_faced(self) -> None:
        """Shots faced is not carried directly; saves plus goals conceded
        reconstructs it exactly when both are present."""
        derived = compute_derived(stats(minutes=2700, saves=90, goals_conceded=30))
        assert derived.save_percentage == pytest.approx(75.0)

    def test_save_percentage_is_absent_without_goals_conceded(self) -> None:
        derived = compute_derived(stats(minutes=2700, saves=90))
        assert derived.save_percentage is None

    def test_clean_sheet_percentage_uses_appearances(self) -> None:
        derived = compute_derived(stats(minutes=2700, appearances=30, clean_sheets=12))
        assert derived.clean_sheet_percentage == pytest.approx(40.0)

    def test_outfield_player_has_no_goalkeeping_metrics(self) -> None:
        derived = compute_derived(stats(minutes=2700, goals=10))
        assert derived.saves_per90 is None
        assert derived.save_percentage is None


class TestAvailability:
    def test_available_lists_only_computable_metrics(self) -> None:
        derived = compute_derived(stats(minutes=900, goals=5))
        available = derived.available()
        assert DerivedMetric.GOALS_PER90 in available
        assert DerivedMetric.TACKLES_PER90 not in available

    def test_get_reads_by_enum(self) -> None:
        derived = compute_derived(stats(minutes=900, goals=9))
        assert derived.get(DerivedMetric.GOALS_PER90) == pytest.approx(0.9)


class TestAgainstTheMockDataset:
    """Every generated player must produce coherent derived metrics."""

    def test_no_percentage_metric_falls_outside_zero_to_one_hundred(self) -> None:
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=1, clubs_per_competition=4)
        records = provider.get_competition_stats("mock-comp-01", SEASON_ID)
        assert records

        for record in records:
            derived = compute_derived(record)
            for metric in PERCENTAGE_METRICS:
                value = derived.get(metric)
                if value is not None:
                    assert 0.0 <= value <= 100.0, f"{metric} = {value}"

    def test_rates_are_never_negative(self) -> None:
        from app.providers.mock import SEASON_ID, MockPerformanceProvider

        provider = MockPerformanceProvider(competitions=1, clubs_per_competition=4)
        for record in provider.get_competition_stats("mock-comp-01", SEASON_ID):
            derived = compute_derived(record)
            for metric in DerivedMetric:
                value = derived.get(metric)
                if value is not None:
                    assert value >= 0.0, f"{metric} = {value}"
