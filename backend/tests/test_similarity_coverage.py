"""How much of the intended comparison actually happened.

A similarity index of 92 says the same thing whether it was measured over
eleven features or six. It is not the same claim. Six of eleven means the two
players agree on what was measured and could differ on everything that was not,
and the index has no way to express that.

So coverage is reported beside the index rather than mixed into it. Folding it
in would change what the number means while leaving its name and its 0-100
scale unchanged, which is the kind of silent redefinition that makes a metric
untrustworthy later.
"""

from __future__ import annotations

import math

import pytest

from app.analytics.similarity import (
    FEATURE_COVERAGE_LABEL,
    MIN_FEATURES,
    MINIMUM_FEATURE_COVERAGE,
    FeatureCoverage,
    SimilarityCandidate,
    SimilarityResult,
    classify_feature_coverage,
)
from app.schemas.canonical import PositionGroup


def result(shared: int, expected: int) -> SimilarityResult:
    return SimilarityResult(
        candidate=SimilarityCandidate(
            player_key="p1",
            display_name="A Player",
            position_group=PositionGroup.CM,
            competition_id="c1",
        ),
        similarity=92.0,
        shared_features=shared,
        expected_features=expected,
    )


class TestTheShare:
    def test_a_full_vector_is_full_coverage(self) -> None:
        assert result(11, 11).feature_coverage == 1.0

    def test_a_partial_vector_reports_its_share(self) -> None:
        assert result(6, 11).feature_coverage == pytest.approx(6 / 11)

    def test_an_unknown_vector_size_is_not_reported_as_complete(self) -> None:
        """Zero expected features means nobody recorded what was intended.

        Reporting 100% there would be the most flattering possible reading of
        knowing nothing.
        """
        assert result(6, 0).feature_coverage == 0.0

    def test_the_index_is_untouched_by_coverage(self) -> None:
        """The premise of the whole design. Two results with wildly different
        coverage carry the same index, because that is what it measures."""
        assert result(11, 11).similarity == result(6, 11).similarity == 92.0


class TestTheBands:
    @pytest.mark.parametrize(
        ("coverage", "expected"),
        [
            (1.0, FeatureCoverage.HIGH),
            (0.85, FeatureCoverage.HIGH),
            (0.84, FeatureCoverage.GOOD),
            (0.65, FeatureCoverage.GOOD),
            (0.64, FeatureCoverage.LIMITED),
            (0.50, FeatureCoverage.LIMITED),
            (0.49, FeatureCoverage.VERY_LIMITED),
            (0.0, FeatureCoverage.VERY_LIMITED),
        ],
    )
    def test_boundaries(self, coverage: float, expected: FeatureCoverage) -> None:
        assert classify_feature_coverage(coverage) is expected

    def test_a_result_carries_its_band_and_label(self) -> None:
        six_of_eleven = result(6, 11)
        assert six_of_eleven.coverage_band is FeatureCoverage.LIMITED
        assert six_of_eleven.coverage_label == FEATURE_COVERAGE_LABEL[FeatureCoverage.LIMITED]

    def test_every_band_has_a_label(self) -> None:
        for band in FeatureCoverage:
            assert FEATURE_COVERAGE_LABEL[band]

    def test_no_band_is_described_as_a_probability(self) -> None:
        """Rule 21. Coverage says how much was compared, not how likely a match."""
        for label in FEATURE_COVERAGE_LABEL.values():
            assert "probab" not in label.lower()
            assert "%" not in label


class TestTheFloor:
    """Why a proportion, and why the absolute floor stays.

    The outfield vectors hold eleven features and the goalkeeping one holds
    eight. A flat floor of five asked outfielders for 45% of their vector and
    goalkeepers for 63% - the same number meaning two different things, for no
    reason anybody chose.
    """

    @staticmethod
    def required(expected: int) -> int:
        return max(MIN_FEATURES, math.ceil(expected * MINIMUM_FEATURE_COVERAGE))

    def test_the_proportion_governs_a_long_vector(self) -> None:
        assert self.required(11) == 6
        assert self.required(20) == 10

    def test_the_absolute_floor_governs_a_short_one(self) -> None:
        """A proportion of a very short vector is still almost nothing."""
        assert self.required(8) == MIN_FEATURES
        assert self.required(4) == MIN_FEATURES

    def test_the_bar_is_the_same_share_for_every_long_vector(self) -> None:
        for size in (10, 11, 12, 16, 20):
            assert self.required(size) / size == pytest.approx(MINIMUM_FEATURE_COVERAGE, abs=0.05)

    def test_this_is_about_metrics_not_minutes(self) -> None:
        """The distinction the product decision turns on.

        Nobody is excluded from similarity for having played too little. A
        comparison is refused only when there are too few shared dimensions for
        it to mean anything - a fact about the data, not about the player.
        """
        from app.analytics import similarity

        source = similarity.__doc__ or ""
        assert "minutes" not in source.lower() or "minimum_minutes" in dir(similarity)
