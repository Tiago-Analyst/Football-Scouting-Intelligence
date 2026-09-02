"""Score utilities and sample-size rules."""

from __future__ import annotations

import pytest

from app.analytics.sample import (
    DEVELOPING_SAMPLE_MINUTES,
    ESTABLISHED_SAMPLE_MINUTES,
    LOW_SAMPLE_MINUTES,
    SAMPLE_BAND_COPY,
    SAMPLE_BAND_LABEL,
    SampleBand,
    can_rate,
    classify_minutes,
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
    """Bands describe how much football is behind a figure. They exclude nobody."""

    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [
            (3000, SampleBand.ESTABLISHED),
            (ESTABLISHED_SAMPLE_MINUTES, SampleBand.ESTABLISHED),
            (ESTABLISHED_SAMPLE_MINUTES - 1, SampleBand.DEVELOPING),
            (DEVELOPING_SAMPLE_MINUTES, SampleBand.DEVELOPING),
            (DEVELOPING_SAMPLE_MINUTES - 1, SampleBand.LOW),
            (LOW_SAMPLE_MINUTES, SampleBand.LOW),
            (LOW_SAMPLE_MINUTES - 1, SampleBand.VERY_LOW),
            (1, SampleBand.VERY_LOW),
            (0, SampleBand.VERY_LOW),
        ],
    )
    def test_bands_are_correct_at_the_boundaries(self, minutes: int, expected: SampleBand) -> None:
        assert classify_minutes(minutes) is expected

    def test_unknown_minutes_band_as_the_weakest_claim(self) -> None:
        """Not knowing the sample is a reason to claim less, not to hide anyone."""
        assert classify_minutes(None) is SampleBand.VERY_LOW

    def test_every_band_has_a_label_and_an_explanation(self) -> None:
        for band in SampleBand:
            assert SAMPLE_BAND_LABEL[band]
            assert SAMPLE_BAND_COPY[band]


class TestEligibilityIsArithmeticOnly:
    """The product decision this file exists to hold.

    Every player is searchable, ranked, scored and comparable whatever their
    minutes. The only thing that can keep a figure out is that it cannot be
    computed - a per-90 needs something to divide by - and that is a fact about
    division, not a judgement about who has played enough.

    This replaced `is_rankable`, whose default excluded anyone under 450
    minutes. Four matches into a season that emptied entire competitions.
    """

    @pytest.mark.parametrize("minutes", [1, 12, 100, 179, 450, 900, 3000])
    def test_anyone_who_played_at_all_has_a_rate(self, minutes: int) -> None:
        assert can_rate(minutes)

    def test_a_one_minute_player_is_eligible(self) -> None:
        assert can_rate(1)
        assert classify_minutes(1) is SampleBand.VERY_LOW

    def test_no_denominator_means_no_rate(self) -> None:
        """Not an exclusion on merit: there is nothing to divide by.

        The alternative is fabricating a value, which is what N/A exists to
        avoid.
        """
        assert not can_rate(0)
        assert not can_rate(None)

    def test_a_floor_can_still_be_asked_for(self) -> None:
        """The specification requires a deliberate floor to be possible.

        Nothing passes one by default, which is the difference that matters.
        """
        assert can_rate(200, at_least=90)
        assert not can_rate(200, at_least=450)
        assert not can_rate(None, at_least=0)
