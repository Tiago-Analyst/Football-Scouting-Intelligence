"""The data-quality coverage figure cannot pass 100%.

It printed 101%. The provider sometimes reports more detail-minutes than
played-minutes, `detailed_coverage_pct` keeps that raw on purpose, and the page
averaged the raw ratios - so a handful of 127% rows pulled the mean over the
only value a share can take. Each row is now capped before it is averaged, and
the rows that were capped are counted so nothing is hidden by it.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.load.load_providers import _normalize
from sqlalchemy.orm import Session

from app.models import DimCompetition, DimPlayer, DimSeason, FactPlayerSeasonStats
from app.schemas.canonical import PositionGroup
from app.services.quality_service import (
    average_detailed_coverage,
    seasons_recording_more_than_played,
)

pytestmark = pytest.mark.integration

SOURCE = "cap_perf"


def _season_row(session: Session, name: str, minutes: int, recorded: int, season: str) -> None:
    player = DimPlayer(
        full_name=name,
        normalized_name=_normalize(name),
        date_of_birth=dt.date(1999, 5, 5),
        nationality="Portugal",
        position_group=PositionGroup.CM,
    )
    session.add(player)
    if session.get(DimCompetition, f"{SOURCE}:c") is None:
        session.add(
            DimCompetition(
                competition_id=f"{SOURCE}:c",
                name="Cap League",
                country="Portugal",
                tier=1,
                source=SOURCE,
            )
        )
    if session.get(DimSeason, season) is None:
        session.add(DimSeason(season_id=season, name=season, start_year=2024, end_year=2025))
    session.flush()
    session.add(
        FactPlayerSeasonStats(
            player_id=player.player_id,
            competition_id=f"{SOURCE}:c",
            season_id=season,
            appearances=10,
            minutes=minutes,
            recorded_minutes=recorded,
            source=SOURCE,
        )
    )
    session.flush()


class TestTheAverageIsAShare:
    def test_rows_over_100_are_capped_and_counted(self, db_session: Session) -> None:
        before_count = seasons_recording_more_than_played(db_session)

        _season_row(db_session, "Cap Over", minutes=100, recorded=1_000_000, season="cap-1")
        # A row this far over would drag a raw mean to ~10 000%; capped, it is 100.
        average = average_detailed_coverage(db_session)

        assert average is not None
        assert average <= 100.0
        assert seasons_recording_more_than_played(db_session) == before_count + 1

    def test_a_row_at_exactly_100_is_not_counted_as_over(self, db_session: Session) -> None:
        before_count = seasons_recording_more_than_played(db_session)
        _season_row(db_session, "Cap Exact", minutes=900, recorded=900, season="cap-2")
        assert seasons_recording_more_than_played(db_session) == before_count
