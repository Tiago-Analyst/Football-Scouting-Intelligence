"""Valuation history and transfers, read from the database.

These were the last two endpoints served by asking a provider rather than
reading what the pipeline loaded, and the gap was quiet: in demo mode the mock
provider knows only invented ids, so a real player's history came back empty
rather than wrong. Empty is the better failure and still the wrong answer.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimPlayer,
    FactMarketValue,
    FactTransfer,
)
from app.repositories.market_repository import market_value_history, transfers
from app.schemas.market import TransferType

pytestmark = pytest.mark.integration

SOURCE = "test_market"


def make_player(session: Session, key: str) -> DimPlayer:
    player = DimPlayer(
        full_name="History Haver",
        normalized_name="history haver",
        date_of_birth=dt.date(1998, 3, 3),
        nationality="Portugal",
    )
    session.add(player)
    session.flush()
    session.add(
        BridgePlayerSource(
            player_id=player.player_id,
            source=SOURCE,
            source_player_id=key,
            match_method="source_native_id",
            match_confidence=1.0,
            manual_override=False,
        )
    )
    session.flush()
    return player


class TestValuationHistory:
    def test_it_reads_what_was_loaded(self, db_session: Session) -> None:
        player = make_player(db_session, "mk1")
        for day, value in ((5, 300_000), (1, 100_000), (3, 200_000)):
            db_session.add(
                FactMarketValue(
                    player_id=player.player_id,
                    valued_on=dt.date(2026, 1, day),
                    market_value_eur=value,
                    source=SOURCE,
                )
            )
        db_session.flush()

        history = market_value_history(db_session, "mk1")
        assert [p.market_value_eur for p in history] == [100_000, 200_000, 300_000]

    def test_it_is_oldest_first_so_a_chart_reads_left_to_right(self, db_session: Session) -> None:
        player = make_player(db_session, "mk2")
        for day in (9, 2):
            db_session.add(
                FactMarketValue(
                    player_id=player.player_id,
                    valued_on=dt.date(2026, 2, day),
                    market_value_eur=day * 1000,
                    source=SOURCE,
                )
            )
        db_session.flush()

        dates = [p.valued_on for p in market_value_history(db_session, "mk2")]
        assert dates == sorted(dates)

    def test_an_unknown_key_is_empty_not_an_error(self, db_session: Session) -> None:
        """A player the site knows but no source bridge names - the endpoint
        should show an empty history, not fail the page."""
        assert market_value_history(db_session, "no-such-player") == []


class TestTransfers:
    def test_it_reads_what_was_loaded(self, db_session: Session) -> None:
        player = make_player(db_session, "tr1")
        db_session.add(
            FactTransfer(
                player_id=player.player_id,
                transfer_date=dt.date(2025, 7, 1),
                season="2025",
                from_club_name="Old Club",
                to_club_name="New Club",
                fee_eur=1_000_000,
                transfer_type=TransferType.UNKNOWN,
                source=SOURCE,
            )
        )
        db_session.flush()

        moves = transfers(db_session, "tr1")
        assert len(moves) == 1
        assert moves[0].from_club == "Old Club"
        assert moves[0].to_club == "New Club"
        assert moves[0].fee_eur == 1_000_000

    def test_most_recent_first(self, db_session: Session) -> None:
        player = make_player(db_session, "tr2")
        for year in (2023, 2026, 2024):
            db_session.add(
                FactTransfer(
                    player_id=player.player_id,
                    transfer_date=dt.date(year, 7, 1),
                    transfer_type=TransferType.UNKNOWN,
                    source=SOURCE,
                )
            )
        db_session.flush()

        years = [m.transfer_date.year for m in transfers(db_session, "tr2") if m.transfer_date]
        assert years == [2026, 2024, 2023]

    def test_an_undated_move_sorts_last_rather_than_vanishing(self, db_session: Session) -> None:
        """The Transfermarkt dataset carries transfers with no date. A career
        with a gap in it is more honest than one silently missing a move."""
        player = make_player(db_session, "tr3")
        db_session.add(
            FactTransfer(
                player_id=player.player_id,
                transfer_date=None,
                from_club_name="Somewhere",
                transfer_type=TransferType.UNKNOWN,
                source=SOURCE,
            )
        )
        db_session.add(
            FactTransfer(
                player_id=player.player_id,
                transfer_date=dt.date(2025, 1, 1),
                transfer_type=TransferType.UNKNOWN,
                source=SOURCE,
            )
        )
        db_session.flush()

        moves = transfers(db_session, "tr3")
        assert len(moves) == 2
        assert moves[-1].transfer_date is None


class TestAgainstTheLoadedData:
    def test_real_players_actually_have_history(self, db_session: Session) -> None:
        """The point of the change. Before it, every one of these came back
        empty because the mock provider knew only invented ids."""
        key = db_session.scalar(
            select(BridgePlayerSource.source_player_id)
            .join(FactMarketValue, FactMarketValue.player_id == BridgePlayerSource.player_id)
            .limit(1)
        )
        if key is None:
            pytest.skip("no loaded player has valuation history")

        assert market_value_history(db_session, key)

    def test_a_merged_player_resolves_through_any_of_their_sources(
        self, db_session: Session
    ) -> None:
        """A merged player carries a bridge row per source, all pointing at the
        same row, so either provider's id must find the same history."""
        player_id = db_session.scalar(
            select(BridgePlayerSource.player_id)
            .group_by(BridgePlayerSource.player_id)
            .having(func.count() > 1)
            .limit(1)
        )
        if player_id is None:
            pytest.skip("no player is known to more than one source")

        keys = db_session.scalars(
            select(BridgePlayerSource.source_player_id).where(
                BridgePlayerSource.player_id == player_id
            )
        ).all()
        histories = [len(market_value_history(db_session, key)) for key in keys]
        assert len(set(histories)) == 1, "the same player answered differently by source"
