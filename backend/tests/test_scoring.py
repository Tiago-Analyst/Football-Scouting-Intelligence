"""Score utilities and sample-size rules."""

from __future__ import annotations

import pytest

from app.analytics.sample import (
    FULL_SAMPLE_MINUTES,
    LOW_SAMPLE_MINUTES,
    SAMPLE_BAND_COPY,
    SampleBand,
    classify_minutes,
    is_rankable,
)
from app.analytics.scoring import (
    ScoreComponent,
    clamp_score,
    invert_percentile,
    normalise_weights,
    weighted_score,
)


class TestClampScore:
    @pytest.mark.parametrize(
        ("given", "expected"), [(-5, 0.0), (0, 0.0), (50, 50.0), (100, 100.0), (100.0000001, 100.0)]
    )
    def test_holds_inside_range(self, given: float, expected: float) -> None:
        """Section 24 requires scores in 0-100; drift past 100 would trip a
        database check constraint at load time."""
        assert clamp_score(given) == expected


class TestInvertPercentile:
    def test_flips_the_scale(self) -> None:
        assert invert_percentile(10) == 90.0
        assert invert_percentile(90) == 10.0

    def test_the_midpoint_is_unchanged(self) -> None:
        assert invert_percentile(50) == 50.0

    def test_absence_propagates_rather_than_becoming_perfect(self) -> None:
        """Inverting an unknown to 100 would make missing data look like elite
        performance on every inverse metric."""
        assert invert_percentile(None) is None

    def test_out_of_range_input_is_clamped_first(self) -> None:
        assert invert_percentile(120) == 0.0
        assert invert_percentile(-20) == 100.0


class TestWeightedScore:
    def test_combines_components_by_weight(self) -> None:
        result = weighted_score(
            [
                ScoreComponent("a", 0.5, 80.0),
                ScoreComponent("b", 0.5, 60.0),
            ]
        )
        assert result.score == pytest.approx(70.0)
        assert result.coverage == pytest.approx(1.0)

    def test_uneven_weights_are_respected(self) -> None:
        result = weighted_score(
            [
                ScoreComponent("a", 0.75, 100.0),
                ScoreComponent("b", 0.25, 0.0),
            ]
        )
        assert result.score == pytest.approx(75.0)

    def test_weights_need_not_sum_to_one(self) -> None:
        """Configuration expresses weights as percentages; they are normalised
        so a file that adds to 99 does not rescale every score."""
        result = weighted_score([ScoreComponent("a", 45, 80.0), ScoreComponent("b", 55, 60.0)])
        assert result.score == pytest.approx(0.45 * 80 + 0.55 * 60)

    def test_a_missing_component_disables_the_score_by_default(self) -> None:
        """Strict by default: a score built from whatever happened to be
        available is not comparable with one built from the full set."""
        result = weighted_score([ScoreComponent("a", 0.5, 80.0), ScoreComponent("b", 0.5, None)])
        assert result.score is None
        assert result.missing == ["b"]
        assert result.coverage == pytest.approx(0.5)

    def test_partial_scoring_is_possible_but_must_be_asked_for(self) -> None:
        result = weighted_score(
            [ScoreComponent("a", 0.8, 90.0), ScoreComponent("b", 0.2, None)],
            min_coverage=0.75,
        )
        assert result.score == pytest.approx(90.0)
        assert result.coverage == pytest.approx(0.8)
        assert result.missing == ["b"]

    def test_remaining_weights_are_renormalised(self) -> None:
        """Without renormalisation a missing 20% component would subtract a
        fifth from every score and look like poor performance."""
        result = weighted_score(
            [
                ScoreComponent("a", 0.4, 100.0),
                ScoreComponent("b", 0.4, 50.0),
                ScoreComponent("c", 0.2, None),
            ],
            min_coverage=0.5,
        )
        assert result.score == pytest.approx(75.0)

    def test_coverage_travels_with_the_result(self) -> None:
        result = weighted_score(
            [ScoreComponent("a", 0.7, 80.0), ScoreComponent("b", 0.3, None)],
            min_coverage=0.5,
        )
        assert result.coverage == pytest.approx(0.7)
        assert result.is_available

    def test_no_components_yields_no_score(self) -> None:
        result = weighted_score([])
        assert result.score is None
        assert result.coverage == 0.0

    def test_non_positive_total_weight_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            weighted_score([ScoreComponent("a", 0.0, 50.0)])

    def test_component_values_are_clamped(self) -> None:
        result = weighted_score([ScoreComponent("a", 1.0, 150.0)])
        assert result.score == 100.0


class TestExplainability:
    def test_contributions_sum_to_the_score(self) -> None:
        """A ranking has to be justifiable line by line, so the parts must add
        up to the whole."""
        components = [
            ScoreComponent("progression", 0.45, 94.0),
            ScoreComponent("security", 0.30, 88.0),
            ScoreComponent("creation", 0.25, 70.0),
        ]
        result = weighted_score(components)
        assert result.score is not None
        assert sum(value for _, value in result.contributions()) == pytest.approx(result.score)

    def test_contributions_name_every_available_component(self) -> None:
        result = weighted_score([ScoreComponent("a", 0.5, 80.0), ScoreComponent("b", 0.5, 60.0)])
        assert [name for name, _ in result.contributions()] == ["a", "b"]

    def test_missing_components_do_not_contribute(self) -> None:
        result = weighted_score(
            [ScoreComponent("a", 0.5, 80.0), ScoreComponent("b", 0.5, None)],
            min_coverage=0.5,
        )
        assert [name for name, _ in result.contributions()] == ["a"]


class TestNormaliseWeights:
    def test_scales_to_one(self) -> None:
        assert normalise_weights({"a": 45, "b": 55}) == pytest.approx({"a": 0.45, "b": 0.55})

    def test_handles_weights_that_do_not_add_up(self) -> None:
        normalised = normalise_weights({"a": 30, "b": 30, "c": 30})
        assert sum(normalised.values()) == pytest.approx(1.0)

    def test_rejects_non_positive_totals(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            normalise_weights({"a": 0})


class TestSampleBands:
    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [
            (3000, SampleBand.FULL),
            (FULL_SAMPLE_MINUTES, SampleBand.FULL),
            (FULL_SAMPLE_MINUTES - 1, SampleBand.LOW),
            (LOW_SAMPLE_MINUTES, SampleBand.LOW),
            (LOW_SAMPLE_MINUTES - 1, SampleBand.INSUFFICIENT),
            (0, SampleBand.INSUFFICIENT),
        ],
    )
    def test_bands_are_correct_at_the_boundaries(self, minutes: int, expected: SampleBand) -> None:
        assert classify_minutes(minutes) is expected

    def test_unknown_minutes_are_treated_as_insufficient(self) -> None:
        """Without knowing the sample, keeping the player out of rankings is the
        safe assumption."""
        assert classify_minutes(None) is SampleBand.INSUFFICIENT

    def test_every_band_has_an_explanation(self) -> None:
        for band in SampleBand:
            assert SAMPLE_BAND_COPY[band]


class TestRankability:
    def test_a_full_season_is_rankable(self) -> None:
        assert is_rankable(2500)

    def test_a_small_sample_is_excluded_by_default(self) -> None:
        assert not is_rankable(200)

    def test_the_bar_can_be_lowered_deliberately(self) -> None:
        """The spec requires users to be able to include small samples on
        purpose - but never by accident."""
        assert is_rankable(200, minimum_minutes=90)

    def test_unknown_minutes_are_never_rankable(self) -> None:
        assert not is_rankable(None)
        assert not is_rankable(None, minimum_minutes=0)
