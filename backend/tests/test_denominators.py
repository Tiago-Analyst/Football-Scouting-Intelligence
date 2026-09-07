"""Every per-90 divides by the minutes its own metric belongs to.

THE DEFECT

`compute_derived` divided everything by recorded minutes - the minutes a
provider's detailed feed describes. That is right for the detailed feed and
wrong for goals, assists and goals conceded, which the provider computes over
time on the pitch.

The two figures agree for most players. Where they do not, the error is in the
same direction for every one of them, so it never looked like noise: on the
loaded data it produced goalkeepers conceding thirty goals per ninety minutes.

`pipelines.footystats.denominators` settled which is which against real stored
responses, by reproducing the provider's own published per-90. These tests
cover the routing that result is wired into.
"""

from __future__ import annotations

import pytest

from app.analytics.denominators import (
    CONFIRMED,
    DEFAULT,
    Denominator,
    denominator_for,
    is_confirmed,
    minutes_for,
)
from app.analytics.metrics import DerivedMetric, DerivedMetrics, compute_derived
from app.analytics.percentiles import PlayerMetrics
from app.schemas.canonical import PlayerSeasonStats, PositionGroup

PLAYING = 900
RECORDED = 450


def stats(**overrides: object) -> PlayerSeasonStats:
    """A player whose two minute figures differ by a factor of two.

    Chosen so a routing mistake is visible as a doubling rather than a rounding
    difference.
    """
    base: dict[str, object] = {
        "source_player_id": "p1",
        "season_id": "2026/27",
        "competition_id": "c1",
        "club_id": "club-1",
        "minutes": PLAYING,
        "recorded_minutes": RECORDED,
    }
    base.update(overrides)
    return PlayerSeasonStats(**base)  # type: ignore[arg-type]


class TestTheRoutingTable:
    @pytest.mark.parametrize(
        "metric",
        [
            DerivedMetric.GOALS_PER90,
            DerivedMetric.ASSISTS_PER90,
            DerivedMetric.GOALS_CONCEDED_PER90,
        ],
    )
    def test_the_headline_counters_divide_by_playing_minutes(self, metric: DerivedMetric) -> None:
        """Confirmed against real responses; see the validation report."""
        assert denominator_for(metric) is Denominator.PLAYING
        assert is_confirmed(metric)

    @pytest.mark.parametrize(
        "metric",
        [
            DerivedMetric.PASSES_PER90,
            DerivedMetric.TACKLES_PER90,
            DerivedMetric.INTERCEPTIONS_PER90,
            DerivedMetric.SHOTS_PER90,
            DerivedMetric.NPXG_PER90,
            DerivedMetric.XA_PER90,
        ],
    )
    def test_the_detailed_feed_divides_by_recorded_minutes(self, metric: DerivedMetric) -> None:
        assert denominator_for(metric) is Denominator.RECORDED
        assert is_confirmed(metric)

    def test_non_penalty_goals_follow_goals(self) -> None:
        """Inferred, not confirmed: it is goals minus penalties."""
        assert denominator_for(DerivedMetric.NON_PENALTY_GOALS_PER90) is Denominator.PLAYING
        assert not is_confirmed(DerivedMetric.NON_PENALTY_GOALS_PER90)

    def test_an_unnamed_metric_keeps_what_it_already_had(self) -> None:
        """So nothing moves without evidence.

        The default is the denominator the engine used for everything before
        this table existed, which means a metric nobody has tested behaves
        exactly as it did.
        """
        assert denominator_for("a_metric_nobody_has_tested") is DEFAULT
        assert DEFAULT is Denominator.RECORDED

    def test_a_confirmed_metric_is_never_also_inferred(self) -> None:
        from app.analytics.denominators import INFERRED

        assert not set(CONFIRMED) & set(INFERRED)


class TestChoosingTheDenominator:
    def test_a_playing_metric_gets_playing_minutes(self) -> None:
        assert (
            minutes_for(
                DerivedMetric.GOALS_PER90, playing_minutes=PLAYING, recorded_minutes=RECORDED
            )
            == PLAYING
        )

    def test_a_recorded_metric_gets_recorded_minutes(self) -> None:
        assert (
            minutes_for(
                DerivedMetric.PASSES_PER90, playing_minutes=PLAYING, recorded_minutes=RECORDED
            )
            == RECORDED
        )

    def test_a_missing_denominator_is_not_substituted(self) -> None:
        """The rule the whole project turns on: absent is not another figure.

        Borrowing the other denominator would produce a rate that looks right
        and is measured over the wrong football.
        """
        assert (
            minutes_for(DerivedMetric.PASSES_PER90, playing_minutes=PLAYING, recorded_minutes=None)
            is None
        )
        assert (
            minutes_for(DerivedMetric.GOALS_PER90, playing_minutes=None, recorded_minutes=RECORDED)
            is None
        )


class TestTheRatesThemselves:
    def test_goals_are_measured_over_time_on_the_pitch(self) -> None:
        metrics = compute_derived(stats(goals=10))
        assert metrics.goals_per90 == pytest.approx(10 * 90 / PLAYING)

    def test_passes_are_measured_over_recorded_minutes(self) -> None:
        metrics = compute_derived(stats(passes=450))
        assert metrics.passes_per90 == pytest.approx(450 * 90 / RECORDED)

    def test_a_keeper_conceding_is_measured_over_time_on_the_pitch(self) -> None:
        """The case that produced thirty goals per ninety on real data."""
        metrics = compute_derived(stats(goals_conceded=10, recorded_minutes=30))
        assert metrics.goals_conceded_per90 == pytest.approx(1.0)

    def test_both_minute_figures_are_carried(self) -> None:
        metrics = compute_derived(stats(goals=1))
        assert metrics.minutes == RECORDED
        assert metrics.playing_minutes == PLAYING

    def test_a_provider_with_one_figure_is_unaffected(self) -> None:
        """Most providers do not distinguish the two, and nothing changes."""
        metrics = compute_derived(stats(goals=10, passes=450, recorded_minutes=None))
        assert metrics.goals_per90 == pytest.approx(1.0)
        assert metrics.passes_per90 == pytest.approx(45.0)


class TestAbsentAndZeroDenominators:
    def test_no_recorded_minutes_leaves_detailed_rates_absent(self) -> None:
        metrics = compute_derived(stats(passes=100, recorded_minutes=0))
        assert metrics.passes_per90 is None

    def test_but_the_goalscoring_rates_survive(self) -> None:
        """A detailed feed covering nothing does not erase what they played."""
        metrics = compute_derived(stats(goals=5, recorded_minutes=0))
        assert metrics.goals_per90 == pytest.approx(0.5)

    def test_no_minutes_at_all_leaves_everything_absent(self) -> None:
        """Never a fabricated per-90. There is no denominator to divide by."""
        metrics = compute_derived(stats(goals=5, passes=100, minutes=0, recorded_minutes=0))
        assert metrics.goals_per90 is None
        assert metrics.passes_per90 is None


class TestEligibilityFollowsBothDenominators:
    """A minutes-based exclusion must not arrive through the back door."""

    def test_a_player_with_only_playing_minutes_is_still_rateable(self) -> None:
        record = PlayerMetrics(
            player_key="k",
            position_group=PositionGroup.GK,
            competition_id="c1",
            season_id="2026/27",
            metrics=DerivedMetrics(minutes=0, playing_minutes=900, goals_conceded_per90=1.2),
        )
        assert record.rateable_minutes == 900

    def test_a_player_with_only_recorded_minutes_is_still_rateable(self) -> None:
        record = PlayerMetrics(
            player_key="k",
            position_group=PositionGroup.CM,
            competition_id="c1",
            season_id="2026/27",
            metrics=DerivedMetrics(minutes=450, playing_minutes=None, passes_per90=40.0),
        )
        assert record.rateable_minutes == 450

    def test_a_player_with_neither_has_no_rate(self) -> None:
        record = PlayerMetrics(
            player_key="k",
            position_group=PositionGroup.CM,
            competition_id="c1",
            season_id="2026/27",
            metrics=DerivedMetrics(minutes=0, playing_minutes=0),
        )
        assert record.rateable_minutes is None

    def test_one_minute_is_enough_to_be_rateable(self) -> None:
        """Minutes band a figure. They do not decide who is compared."""
        record = PlayerMetrics(
            player_key="k",
            position_group=PositionGroup.CM,
            competition_id="c1",
            season_id="2026/27",
            metrics=DerivedMetrics(minutes=1, playing_minutes=1, passes_per90=90.0),
        )
        assert record.rateable_minutes == 1


class TestTheReportAndTheTableAgree:
    """The table is a claim about evidence; the report is the evidence.

    If someone edits one without the other, the routing stops being justified
    by anything - which is the failure mode this whole exercise exists to fix.
    """

    def test_every_confirmed_metric_appears_in_the_report(self) -> None:
        import pathlib

        report = pathlib.Path(__file__).resolve().parents[2] / "docs"
        report = report / "footystats_denominator_validation.md"
        if not report.exists():
            pytest.skip("the validation report has not been generated here")
        text = report.read_text(encoding="utf-8")

        for metric, denominator in CONFIRMED.items():
            assert f"`{metric}`" in text, f"{metric} is claimed confirmed and is not in the report"
            section = text.split(f"### `{metric}`")[1].split("###")[0]
            assert denominator.value in section, (
                f"the table routes {metric} to {denominator.value} and the report does not"
            )
            assert "CONFIRMED" in section, f"{metric} is claimed confirmed and the report is not"
