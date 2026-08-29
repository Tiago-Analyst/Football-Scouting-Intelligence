"""The independent recomputation used to check the analytics engines.

This code exists to disagree with the engine when the engine is wrong, so it
has to be right on its own terms. Testing it against the engine would defeat
the point twice over - so it is tested against the definitions instead, and
then the two implementations are made to argue with each other over random
populations.
"""

from __future__ import annotations

import random

import pytest
from pipelines.quality.validate_analytics import (
    TOLERANCE,
    Check,
    Validation,
    independent_per90,
    independent_percentile,
    independent_weighted,
)

from app.analytics.percentiles import percentile_of


class TestPer90:
    def test_it_divides_by_the_minutes_the_statistics_cover(self) -> None:
        """Not minutes played. Where detailed coverage is partial - 13% of
        player-seasons - using the wrong denominator understates every rate."""
        assert independent_per90(10, 900, 1800) == pytest.approx(1.0)

    def test_it_falls_back_to_minutes_played(self) -> None:
        assert independent_per90(10, None, 900) == pytest.approx(1.0)

    def test_an_absent_total_stays_absent(self) -> None:
        """Absent is not zero: a player with no recorded passes has no pass
        rate, and calling it 0.0 would rank them below everyone who played."""
        assert independent_per90(None, 900, 900) is None

    def test_zero_minutes_yields_nothing_rather_than_dividing(self) -> None:
        assert independent_per90(5, 0, 0) is None

    def test_a_genuine_zero_is_a_rate_of_zero(self) -> None:
        """Nought goals in 900 minutes is a measurement, not a gap."""
        assert independent_per90(0, 900, 900) == pytest.approx(0.0)


class TestPercentile:
    def test_the_lowest_value_is_not_zero(self) -> None:
        """Mid-rank shares the percentile among ties, so the bottom value of a
        distinct population sits half a rank up rather than at the floor."""
        assert independent_percentile(1.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(12.5)

    def test_ties_share_a_percentile(self) -> None:
        """The many defenders with no shots on target must all rank together.
        Counting only values strictly below would pile them at zero and let one
        player with a single shot leap over the lot."""
        population = [0.0, 0.0, 0.0, 1.0]
        assert independent_percentile(0.0, population) == pytest.approx(37.5)

    def test_the_highest_value_is_not_a_hundred(self) -> None:
        assert independent_percentile(4.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(87.5)

    def test_a_value_above_everything_reaches_a_hundred(self) -> None:
        """Only a player outside the population they are measured against."""
        assert independent_percentile(9.0, [1.0, 2.0, 3.0, 4.0]) == pytest.approx(100.0)


class TestTheTwoImplementationsAgree:
    """The cross-check is only worth running if both sides are right.

    One bisects a sorted list, the other counts every comparison. They share no
    code and no off-by-one, so agreement across a few thousand random
    populations - heavy with ties, which is where percentile definitions
    usually part company - is real evidence about both.
    """

    def test_they_agree_on_random_populations(self) -> None:
        # S311: comparing two percentile implementations, not generating
        # anything anyone relies on being unguessable. Seeded so a
        # disagreement can be reproduced.
        rng = random.Random(20260829)  # noqa: S311
        for _ in range(2000):
            size = rng.randint(1, 40)
            # Small integer range on purpose: ties are the interesting case.
            population = [float(rng.randint(0, 5)) for _ in range(size)]
            value = float(rng.randint(0, 6))
            mine = independent_percentile(value, population)
            theirs = percentile_of(value, sorted(population))
            assert mine == pytest.approx(theirs, abs=1e-9)

    def test_they_agree_when_every_value_is_the_same(self) -> None:
        """Everyone tied should sit at the midpoint, not at either end."""
        population = [2.0] * 15
        assert independent_percentile(2.0, population) == pytest.approx(50.0)
        assert percentile_of(2.0, population) == pytest.approx(50.0)


class TestReportingADisagreement:
    def check(self, engine: float | None, independent: float | None) -> Check:
        return Check(
            player="Someone (CB)",
            subject="goals_per90",
            kind="per90",
            engine=engine,
            independent=independent,
            working="3 / 900 * 90",
        )

    def test_float_noise_is_not_a_disagreement(self) -> None:
        """The same number reached by dividing in a different order."""
        assert self.check(0.3, 0.3 + TOLERANCE / 2).agrees

    def test_a_real_difference_is(self) -> None:
        assert not self.check(0.3, 0.4).agrees

    def test_both_absent_agree(self) -> None:
        """Neither side could compute it, which is a matching answer."""
        assert self.check(None, None).agrees

    def test_one_absent_is_a_disagreement(self) -> None:
        """The engine producing a number where the recomputation cannot is
        exactly the failure worth catching - it means something was filled in."""
        assert not self.check(0.3, None).agrees
        assert not self.check(None, 0.3).agrees

    def test_failures_are_collected(self) -> None:
        validation = Validation()
        validation.add(self.check(0.3, 0.3))
        validation.add(self.check(0.3, 0.9))
        assert len(validation.checks) == 2
        assert len(validation.failures) == 1


class TestWeightedRecomputation:
    """The renormalisation is where a plausible wrong answer would come from."""

    def test_a_full_set_is_a_weighted_mean(self) -> None:
        parts = {"a": (50.0, 80.0), "b": (50.0, 40.0)}
        score, coverage, _ = independent_weighted(parts, 1.0)
        assert score == pytest.approx(60.0)
        assert coverage == pytest.approx(1.0)

    def test_weights_are_shared_out_again_over_what_is_present(self) -> None:
        """The point of renormalising. Without it the missing quarter would drag
        this to 60 and read as poor performance rather than absent data."""
        parts = {"a": (50.0, 80.0), "b": (25.0, 80.0), "c": (25.0, None)}
        score, coverage, working = independent_weighted(parts, 0.5)
        assert score == pytest.approx(80.0)
        assert coverage == pytest.approx(0.75)
        assert "renormalised over 75 of 100" in working

    def test_below_the_floor_nothing_is_produced(self) -> None:
        """A score from a subset is not comparable with one from the whole."""
        parts = {"a": (30.0, 90.0), "b": (70.0, None)}
        score, coverage, working = independent_weighted(parts, 0.8)
        assert score is None
        assert coverage == pytest.approx(0.3)
        assert "below the required" in working

    def test_exactly_at_the_floor_is_produced(self) -> None:
        parts = {"a": (80.0, 70.0), "b": (20.0, None)}
        score, _, _ = independent_weighted(parts, 0.8)
        assert score == pytest.approx(70.0)

    def test_nothing_present_yields_nothing(self) -> None:
        score, coverage, _ = independent_weighted({"a": (100.0, None)}, 0.0)
        assert score is None
        assert coverage == pytest.approx(0.0)

    def test_score_components_are_named_in_the_working(self) -> None:
        """A role mixes metric percentiles with whole intelligence scores. Saying
        how many of each went in is what makes the number checkable by hand."""
        parts = {"tackles_per90": (60.0, 50.0), "score:ball_security": (40.0, 70.0)}
        _, _, working = independent_weighted(parts, 1.0)
        assert "1 of them scores" in working
