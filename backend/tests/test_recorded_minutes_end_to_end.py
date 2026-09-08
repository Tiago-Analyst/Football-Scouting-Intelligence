"""326 played, 416 recorded, all the way to PostgreSQL.

WHY A SEPARATE END-TO-END TEST

The un-clamping was done in three places and undone in a fourth. The provider
mapping stopped clamping, the database constraint was dropped, the coverage
display was taught to cap - and `CONTAINMENT_PAIRS` in the loader still held
`("recorded_minutes", "minutes")`, which does not clamp but *nulls both
halves*.

So the provider's 326/416 survived the mapping, survived the schema, and was
discarded on the way in. Every per-90 for that player became N/A, and every
unit test upstream still passed because each one only checked its own stage.

This walks the whole path in one test, which is the only shape that would have
caught it.
"""

from __future__ import annotations

import pytest
from pipelines.load.load_providers import reconcile_contradictions
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.footystats import FootyStatsProvider

#: The real record that motivated all of this.
PLAYED = 326
RECORDED = 416


@pytest.fixture
def provider() -> FootyStatsProvider:
    """Built here rather than borrowed from the provider test module, so this
    file stands on its own."""
    from app.providers.footystats_mapping import load_mapping

    from .conftest import build_settings
    from .test_footystats_provider import COMPETITIONS, POSITIONS

    return FootyStatsProvider(
        build_settings(footystats_api_key="a-test-key"),
        mapping=load_mapping(),
        competitions=COMPETITIONS,
        position_mapping=POSITIONS,
    )


class TestStageOneTheProviderMapping:
    def test_the_raw_response_survives_it(self, provider: FootyStatsProvider) -> None:
        from .test_footystats_provider import roster_row, stub

        row = roster_row(1)
        row["minutes_played_overall"] = PLAYED
        row["detailed"]["detailed_minutes_played_recorded_overall"] = RECORDED
        stub(provider, player_stats={"data": [row]})

        record = provider.get_player_stats("1", "17146")
        assert record is not None
        assert (record.minutes, record.recorded_minutes) == (PLAYED, RECORDED)


class TestStageTwoTheCanonicalRecord:
    def test_it_holds_both_figures(self) -> None:
        from app.schemas.canonical import PlayerSeasonStats

        stats = PlayerSeasonStats(
            source_player_id="p",
            season_id="2026/27",
            competition_id="c",
            club_id="club",
            minutes=PLAYED,
            recorded_minutes=RECORDED,
        )
        assert (stats.minutes, stats.recorded_minutes) == (PLAYED, RECORDED)


class TestStageThreeTheLoader:
    def test_reconciliation_leaves_them_alone(self) -> None:
        """The stage that was destroying them."""
        row: dict[str, object] = {"minutes": PLAYED, "recorded_minutes": RECORDED}
        assert reconcile_contradictions(row) == []
        assert row == {"minutes": PLAYED, "recorded_minutes": RECORDED}

    def test_the_pair_is_not_configured_at_all(self) -> None:
        """Asserted on the configuration, not only on its effect: a future
        edit that re-adds the pair should fail here with an obvious reason."""
        from pipelines.load.load_providers import CONTAINMENT_PAIRS

        assert ("recorded_minutes", "minutes") not in CONTAINMENT_PAIRS
        assert ("minutes", "recorded_minutes") not in CONTAINMENT_PAIRS

    def test_the_genuine_pairs_are_still_configured(self) -> None:
        """Removing one pair must not have removed the rest."""
        from pipelines.load.load_providers import CONTAINMENT_PAIRS

        for pair in (
            ("passes_completed", "passes"),
            ("shots_on_target", "shots"),
            ("duels_won", "duels"),
            ("aerial_duels_won", "aerial_duels"),
            ("non_penalty_goals", "goals"),
        ):
            assert pair in CONTAINMENT_PAIRS, pair


@pytest.mark.integration
class TestStageFourPostgreSQL:
    def test_the_row_stores_and_reads_back_unchanged(self, db_session: Session) -> None:
        import datetime as dt

        from pipelines.load.load_providers import _normalize

        from app.models import DimCompetition, DimPlayer, DimSeason
        from app.schemas.canonical import PositionGroup

        competition = DimCompetition(
            competition_id="test:e2e-minutes", name="E2E Test League", source="test"
        )
        season = DimSeason(
            season_id="test:e2e-2026", name="2026/27", start_year=2026, end_year=2027
        )
        player = DimPlayer(
            full_name="End To End Minutes Player",
            normalized_name=_normalize("End To End Minutes Player"),
            date_of_birth=dt.date(1997, 1, 1),
            nationality="Portugal",
            position_group=PositionGroup.CM,
        )
        db_session.add_all([competition, season, player])
        db_session.flush()

        db_session.execute(
            text("""
                INSERT INTO fact_player_season_stats
                    (player_id, competition_id, season_id, minutes, recorded_minutes, source)
                VALUES (:p, :c, :s, :played, :recorded, 'test_e2e')
            """),
            {
                "p": player.player_id,
                "c": competition.competition_id,
                "s": season.season_id,
                "played": PLAYED,
                "recorded": RECORDED,
            },
        )
        db_session.flush()

        row = db_session.execute(
            text(
                "SELECT minutes, recorded_minutes FROM fact_player_season_stats "
                "WHERE player_id = :p"
            ),
            {"p": player.player_id},
        ).one()

        assert row == (PLAYED, RECORDED), "no clamp, no null, no rejection"


class TestStageFiveWhatTheEngineDoesWithIt:
    def test_the_detailed_rates_divide_by_the_larger_figure(self) -> None:
        """Which is the whole reason the value had to survive."""
        from app.analytics.metrics import compute_derived
        from app.schemas.canonical import PlayerSeasonStats

        metrics = compute_derived(
            PlayerSeasonStats(
                source_player_id="p",
                season_id="2026/27",
                competition_id="c",
                club_id="club",
                minutes=PLAYED,
                recorded_minutes=RECORDED,
                passes=416,
                goals=4,
            )
        )
        # Detailed metric over recorded minutes: 416 / 416 * 90.
        assert metrics.passes_per90 == pytest.approx(90.0)
        # Headline counter over played minutes: 4 / 326 * 90.
        assert metrics.goals_per90 == pytest.approx(4 * 90 / PLAYED)

    def test_and_nothing_reads_as_absent(self) -> None:
        """The symptom of the bug: both minute counts gone, so every per-90
        for that player was N/A."""
        from app.analytics.metrics import compute_derived
        from app.schemas.canonical import PlayerSeasonStats

        metrics = compute_derived(
            PlayerSeasonStats(
                source_player_id="p",
                season_id="2026/27",
                competition_id="c",
                club_id="club",
                minutes=PLAYED,
                recorded_minutes=RECORDED,
                passes=416,
                goals=4,
            )
        )
        assert metrics.minutes == RECORDED
        assert metrics.playing_minutes == PLAYED
        assert metrics.passes_per90 is not None
        assert metrics.goals_per90 is not None
