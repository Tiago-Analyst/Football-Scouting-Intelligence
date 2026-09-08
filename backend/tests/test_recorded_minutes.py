"""Recorded minutes are the provider's number, not ours.

THE DEFECT

Two rules, agreeing with each other and both wrong. A database constraint said
`recorded_minutes <= minutes`, and the provider mapping clamped down to satisfy
it. Both encoded a true statement about football - the statistics cannot
describe more minutes than were played - and a false one about this provider.

The denominator validation established, against FootyStats' own published
per-90 fields, that its detailed metrics divide by the recorded figure
*including where that figure is the larger one*. One sampled player has 326
played minutes and 416 recorded, and their detailed rates reproduce only when
divided by 416. Clamping 416 to 326 inflates every detailed per-90 that player
has by 28% - a silent corruption produced by a rule written to prevent one.

WHAT THESE COVER

That the raw value survives the provider, survives the database, and is
reported rather than hidden. And the separation the fix depends on: how much
football a player played is one question, how much of it the provider described
in detail is another, and they now have separate answers.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.coverage import (
    CoverageBand,
    classify_coverage,
    coverage_display_pct,
    detailed_coverage_pct,
    minutes_are_inconsistent,
)
from app.analytics.sample import SampleBand, classify_minutes

# ---------------------------------------------------------------------------
# The canonical value
# ---------------------------------------------------------------------------


class TestNothingClampsTheProviderValue:
    @pytest.mark.parametrize(
        ("minutes", "recorded"),
        [
            (1800, 900),  # ordinary: detail covers half
            (900, 900),  # equal
            (326, 416),  # the real case that motivated this
            (1800, 9999),  # absurd, and still the provider's number
            (0, 90),  # no minutes played, detail recorded anyway
        ],
    )
    def test_both_figures_survive_unchanged(self, minutes: int, recorded: int) -> None:
        from app.schemas.canonical import PlayerSeasonStats

        stats = PlayerSeasonStats(
            source_player_id="p",
            season_id="2026/27",
            competition_id="c",
            club_id="club",
            minutes=minutes,
            recorded_minutes=recorded,
        )
        assert (stats.minutes, stats.recorded_minutes) == (minutes, recorded)


# ---------------------------------------------------------------------------
# The database
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTheDatabaseAcceptsIt:
    def test_recorded_above_played_is_storable(self, db_session: Session) -> None:
        """The literal case from the brief: 326 played, 416 recorded."""
        db_session.execute(
            text("""
                INSERT INTO fact_player_season_stats
                    (player_id, competition_id, season_id, minutes, recorded_minutes, source)
                SELECT p.player_id, c.competition_id, s.season_id, 326, 416, 'test_unclamped'
                FROM dim_player p, dim_competition c, dim_season s
                LIMIT 1
            """)
        )
        db_session.flush()
        row = db_session.execute(
            text(
                "SELECT minutes, recorded_minutes FROM fact_player_season_stats "
                "WHERE source = 'test_unclamped'"
            )
        ).one()
        assert row == (326, 416)

    def test_the_old_constraint_is_gone(self, db_session: Session) -> None:
        present = db_session.execute(
            text(
                "SELECT count(*) FROM pg_constraint WHERE conname = "
                "'ck_fact_player_season_stats_recorded_minutes_within_minutes'"
            )
        ).scalar()
        assert present == 0

    def test_negative_minutes_are_still_refused(self, db_session: Session) -> None:
        """Dropping the editorial rule does not drop the arithmetic ones.

        A negative minute count is not a provider opinion worth preserving; it
        is corrupt, and the database should go on saying so.
        """
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.execute(
                text("""
                    INSERT INTO fact_player_season_stats
                        (player_id, competition_id, season_id, minutes, recorded_minutes, source)
                    SELECT p.player_id, c.competition_id, s.season_id, 90, -5, 'test_negative'
                    FROM dim_player p, dim_competition c, dim_season s
                    LIMIT 1
                """)
            )
            db_session.flush()


# ---------------------------------------------------------------------------
# Coverage above 100%
# ---------------------------------------------------------------------------


class TestCoverageAboveOneHundred:
    def test_the_raw_ratio_is_not_capped(self) -> None:
        """Data quality needs the real number."""
        assert detailed_coverage_pct(416, 326) == pytest.approx(127.6, abs=0.1)

    def test_the_displayed_figure_is(self) -> None:
        """ "127% Excellent coverage" reads as a broken site. It is not."""
        assert coverage_display_pct(detailed_coverage_pct(416, 326)) == 100.0

    def test_an_ordinary_ratio_passes_through_untouched(self) -> None:
        raw = detailed_coverage_pct(300, 1200)
        assert raw == pytest.approx(25.0)
        assert coverage_display_pct(raw) == pytest.approx(25.0)

    def test_the_discrepancy_is_flagged(self) -> None:
        assert minutes_are_inconsistent(416, 326) is True
        assert minutes_are_inconsistent(300, 1200) is False
        assert minutes_are_inconsistent(900, 900) is False

    def test_absent_figures_flag_nothing(self) -> None:
        """Unknown is not a discrepancy."""
        assert minutes_are_inconsistent(None, 900) is False
        assert minutes_are_inconsistent(900, None) is False
        assert coverage_display_pct(None) is None

    def test_a_capped_figure_bands_as_excellent(self) -> None:
        """Rather than falling through a comparison it was never meant to fail."""
        assert classify_coverage(coverage_display_pct(127.6)) is CoverageBand.EXCELLENT


# ---------------------------------------------------------------------------
# Two questions, two answers
# ---------------------------------------------------------------------------


class TestSampleBandMeasuresFootballPlayed:
    def test_it_uses_minutes_played(self) -> None:
        """The example from the brief: a full season, thinly recorded.

        1,200 minutes played is an established sample whatever the provider
        managed to record about it. Banding on recorded minutes made this
        player look like a 300-minute cameo, which is a statement about
        FootyStats wearing the name of a statement about the player.
        """
        assert classify_minutes(1200) is SampleBand.ESTABLISHED
        assert classify_minutes(300) is SampleBand.LOW

    @pytest.mark.parametrize(
        ("minutes", "band"),
        [
            (0, SampleBand.VERY_LOW),
            (1, SampleBand.VERY_LOW),
            (179, SampleBand.VERY_LOW),
            (180, SampleBand.LOW),
            (449, SampleBand.LOW),
            (450, SampleBand.DEVELOPING),
            (899, SampleBand.DEVELOPING),
            (900, SampleBand.ESTABLISHED),
            (3000, SampleBand.ESTABLISHED),
        ],
    )
    def test_the_boundaries(self, minutes: int, band: SampleBand) -> None:
        assert classify_minutes(minutes) is band

    def test_the_two_concepts_can_disagree_completely(self) -> None:
        """Which is the whole reason they are two fields."""
        played, recorded = 1200, 300
        assert classify_minutes(played) is SampleBand.ESTABLISHED
        assert classify_coverage(detailed_coverage_pct(recorded, played)) is CoverageBand.LIMITED

    def test_and_in_the_other_direction(self) -> None:
        played, recorded = 326, 416
        assert classify_minutes(played) is SampleBand.LOW
        assert (
            classify_coverage(coverage_display_pct(detailed_coverage_pct(recorded, played)))
            is CoverageBand.EXCELLENT
        )


@pytest.mark.integration
class TestTheViewBandsOnPlayedMinutes:
    def test_no_players_band_disagrees_with_their_played_minutes(self) -> None:
        """Asserted against the loaded universe, not a constructed record."""
        from app.core.config import get_settings
        from app.services.analytics_service import build_view

        view = build_view(get_settings())
        offenders = [
            (record.player_key, record.stats.minutes, record.sample_band.value)
            for record in view.players.values()
            if record.sample_band is not classify_minutes(record.stats.minutes)
        ]
        assert offenders == [], offenders[:5]


class TestDatesAreNotInvolved:
    """Guard against a plausible future confusion: bands are minutes, not time."""

    def test_the_band_function_takes_minutes_only(self) -> None:
        assert classify_minutes(900) is SampleBand.ESTABLISHED
        with pytest.raises(TypeError):
            classify_minutes(dt.date(2026, 1, 1))  # type: ignore[arg-type]
