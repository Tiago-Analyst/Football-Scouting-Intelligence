"""Detailed-stat coverage: the gap between playing and being recorded.

Two minute counts, and they are not the same thing. Time on the pitch is one;
the minutes the provider's detailed counts actually describe is another, and it
is routinely smaller. Every per-90 divides by the second, which is correct and
completely invisible - a player's numbers simply look thin and nothing on the
page says why.

These pin the arithmetic of publishing that gap, and in particular the three
places where nought and unknown must not be confused.
"""

from __future__ import annotations

import pytest

from app.analytics.coverage import (
    COVERAGE_BAND_COPY,
    COVERAGE_BAND_LABEL,
    CoverageBand,
    classify_coverage,
    detailed_coverage_pct,
)


class TestTheShare:
    def test_recorded_below_played(self) -> None:
        assert detailed_coverage_pct(1180, 1420) == pytest.approx(83.098, abs=0.01)

    def test_recorded_equals_played(self) -> None:
        assert detailed_coverage_pct(1420, 1420) == 100.0

    def test_nothing_recorded_for_a_player_who_played(self) -> None:
        """Nought is a measurement here, not a gap in our knowledge.

        The provider recorded no detail for someone who was on the pitch, which
        is exactly what a reader should see when every per-90 reads N/A.
        """
        assert detailed_coverage_pct(0, 900) == 0.0
        assert classify_coverage(0.0) is CoverageBand.LIMITED

    def test_a_missing_recorded_figure_is_unknown_not_nought(self) -> None:
        """The distinction that matters most.

        Reporting 0% here would assert something the provider never told us,
        and it would look identical to the case above - which is a real
        measurement.
        """
        assert detailed_coverage_pct(None, 900) is None
        assert classify_coverage(None) is None

    def test_no_minutes_means_no_share_to_take(self) -> None:
        """Undefined, not zero. Dividing by nought fabricates a figure."""
        assert detailed_coverage_pct(0, 0) is None
        assert detailed_coverage_pct(120, 0) is None
        assert detailed_coverage_pct(120, None) is None

    def test_an_impossible_share_is_reported_rather_than_hidden(self) -> None:
        """More recorded than played should not happen.

        Clamping it to 100% would turn a provider anomaly into a tidy-looking
        number, and nobody would ever find it.
        """
        assert detailed_coverage_pct(1000, 900) == pytest.approx(111.1, abs=0.1)


class TestTheBands:
    @pytest.mark.parametrize(
        ("pct", "expected"),
        [
            (100.0, CoverageBand.EXCELLENT),
            (90.0, CoverageBand.EXCELLENT),
            (89.9, CoverageBand.GOOD),
            (75.0, CoverageBand.GOOD),
            (74.9, CoverageBand.PARTIAL),
            (50.0, CoverageBand.PARTIAL),
            (49.9, CoverageBand.LIMITED),
            (0.0, CoverageBand.LIMITED),
        ],
    )
    def test_boundaries(self, pct: float, expected: CoverageBand) -> None:
        assert classify_coverage(pct) is expected

    def test_every_band_can_be_explained(self) -> None:
        for band in CoverageBand:
            assert COVERAGE_BAND_LABEL[band]
            assert COVERAGE_BAND_COPY[band]

    def test_the_bands_do_not_exclude_anybody(self) -> None:
        """There is deliberately no `is_usable` here.

        Coverage describes how complete the record is. It is not a gate, and
        adding one would quietly remove players the product exists to show.
        """
        import app.analytics.coverage as module

        assert not [
            name for name in dir(module) if name.startswith(("is_", "eligible", "excluded", "min_"))
        ]
