"""Dropping the market history of players the site never shows.

Four fifths of the loaded valuations belong to players in no covered
competition. Deleting them takes the database from 247 MB to 75 MB and costs
nothing, because nothing reads them.

The dangerous part is *when* it runs. Before identity resolution, no player has
both statistics and a market history - the two sources are still separate rows -
so "unused" means "all of it".
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.load.prune import prune, survey
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactTransfer,
)
from app.schemas.market import TransferType

pytestmark = pytest.mark.integration

SOURCE = "test_prune"


def player(session: Session, name: str, *, with_stats: bool) -> DimPlayer:
    row = DimPlayer(full_name=name, normalized_name=name.lower(), nationality="Portugal")
    session.add(row)
    session.flush()

    session.add(
        FactMarketValue(
            player_id=row.player_id,
            valued_on=dt.date(2026, 1, 1),
            market_value_eur=1_000_000,
            source=SOURCE,
        )
    )
    session.add(
        FactTransfer(
            player_id=row.player_id,
            transfer_date=dt.date(2025, 7, 1),
            transfer_type=TransferType.UNKNOWN,
            source=SOURCE,
        )
    )

    if with_stats:
        session.add(
            DimCompetition(
                competition_id=f"{SOURCE}:c1",
                name="A League",
                country="Portugal",
                tier=1,
                source=SOURCE,
            )
            if session.get(DimCompetition, f"{SOURCE}:c1") is None
            else DimCompetition(
                competition_id="unused", name="x", country="x", tier=1, source=SOURCE
            )
        )
        if session.get(DimSeason, "2026") is None:
            session.add(DimSeason(season_id="2026", name="2026", start_year=2026, end_year=2027))
        session.flush()
        session.add(
            FactPlayerSeasonStats(
                player_id=row.player_id,
                competition_id=f"{SOURCE}:c1",
                season_id="2026",
                appearances=10,
                minutes=900,
                source=SOURCE,
            )
        )
    session.flush()
    return row


class TestSurvey:
    def test_it_counts_what_nothing_reads(self, db_session: Session) -> None:
        shown = player(db_session, "Shown Player", with_stats=True)
        hidden = player(db_session, "Hidden Player", with_stats=False)

        report = survey(db_session)
        assert report.valuations_unused >= 1
        assert report.valuations_total > report.valuations_unused
        assert shown.player_id != hidden.player_id

    def test_a_database_with_no_overlap_is_not_safe_to_prune(self, db_session: Session) -> None:
        """Every valuation unused means identity resolution has not run, and
        pruning would delete the lot."""
        db_session.execute(FactPlayerSeasonStats.__table__.delete())
        db_session.flush()

        report = survey(db_session)
        assert not report.is_safe

    def test_an_empty_database_is_not_safe_either(self, db_session: Session) -> None:
        db_session.execute(FactMarketValue.__table__.delete())
        db_session.flush()
        assert not survey(db_session).is_safe


class TestPruning:
    def test_it_removes_only_the_unreachable_history(self, db_session: Session) -> None:
        shown = player(db_session, "Shown Player", with_stats=True)
        hidden = player(db_session, "Hidden Player", with_stats=False)

        prune(db_session)
        db_session.flush()

        def valuations(player_id: int) -> int:
            return (
                db_session.scalar(
                    select(func.count())
                    .select_from(FactMarketValue)
                    .where(FactMarketValue.player_id == player_id)
                )
                or 0
            )

        assert valuations(shown.player_id) == 1
        assert valuations(hidden.player_id) == 0

    def test_the_players_themselves_stay(self, db_session: Session) -> None:
        """The whole point of the restraint. Those 45,000 players are the pool
        identity resolution matches future ingests against, and a smaller pool
        is a lower match rate - quietly, because an unmatched player simply
        never appears."""
        hidden = player(db_session, "Hidden Player", with_stats=False)
        db_session.add(
            BridgePlayerSource(
                player_id=hidden.player_id,
                source="transfermarkt",
                source_player_id="tm-hidden",
                match_method="source_native_id",
                match_confidence=1.0,
                manual_override=False,
            )
        )
        db_session.flush()

        prune(db_session)
        db_session.flush()

        assert db_session.get(DimPlayer, hidden.player_id) is not None
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(BridgePlayerSource)
                .where(BridgePlayerSource.player_id == hidden.player_id)
            )
            == 1
        )

    def test_transfers_go_the_same_way_as_valuations(self, db_session: Session) -> None:
        hidden = player(db_session, "Hidden Player", with_stats=False)
        prune(db_session)
        db_session.flush()

        assert (
            db_session.scalar(
                select(func.count())
                .select_from(FactTransfer)
                .where(FactTransfer.player_id == hidden.player_id)
            )
            == 0
        )

    def test_running_it_twice_changes_nothing_the_second_time(self, db_session: Session) -> None:
        player(db_session, "Shown Player", with_stats=True)
        player(db_session, "Hidden Player", with_stats=False)

        prune(db_session)
        db_session.flush()
        again = prune(db_session)
        assert again == (0, 0)
