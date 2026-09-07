"""Refreshing one provider must not leave the previous load behind.

THE DEFECT THESE COVER

`purge` removed statistics by their `source` column but left market values and
transfers to the cascade from `dim_player`. That works only while a player
belongs to one provider. The moment identity resolution merges a player across
providers, their `dim_player` row survives a purge - it is shared - and their
market history survives with it. The next Transfermarkt load then inserted the
refreshed valuations *alongside* the stale ones.

`uq_market_value_point` did not catch it: it is `(player_id, valued_on,
source)`, so a valuation the provider moved to a different date is a different
row, not a conflict. The result was a market-value chart drawing a history
that never happened, from a source that had already corrected itself.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.load.load_providers import _normalize, purge
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimPlayer,
    FactMarketValue,
    FactTransfer,
)
from app.schemas.canonical import PositionGroup

pytestmark = pytest.mark.integration

MARKET = "test_market"
PERFORMANCE = "test_perf"


# ---------------------------------------------------------------------------
# Fixtures: one player both providers know about, which is the case that broke
# ---------------------------------------------------------------------------


def make_player(session: Session, name: str) -> DimPlayer:
    player = DimPlayer(
        full_name=name,
        normalized_name=_normalize(name),
        date_of_birth=dt.date(1998, 3, 12),
        nationality="Portugal",
        position_group=PositionGroup.CM,
    )
    session.add(player)
    session.flush()
    return player


def bridge(session: Session, player: DimPlayer, source: str, source_id: str) -> None:
    session.add(
        BridgePlayerSource(
            player_id=player.player_id,
            source=source,
            source_player_id=source_id,
            match_method="source_native_id",
            match_confidence=1.0,
        )
    )
    session.flush()


def market_value(
    session: Session, player: DimPlayer, source: str, on: dt.date, amount: int
) -> None:
    session.add(
        FactMarketValue(
            player_id=player.player_id,
            valued_on=on,
            market_value_eur=amount,
            source=source,
        )
    )
    session.flush()


def transfer(session: Session, player: DimPlayer, source: str, on: dt.date) -> None:
    session.add(
        FactTransfer(
            player_id=player.player_id,
            transfer_date=on,
            transfer_type="permanent",
            source=source,
        )
    )
    session.flush()


@pytest.fixture
def shared_player(db_session: Session) -> tuple[Session, DimPlayer]:
    """One logical player, known to both providers.

    This is precisely the state identity resolution produces, and precisely the
    state in which the cascade stopped being enough.
    """
    player = make_player(db_session, "Bruno Alves Ferreira")
    bridge(db_session, player, MARKET, "tm-1")
    bridge(db_session, player, PERFORMANCE, "fs-1")
    return db_session, player


class TestPurgingOneProvidersMarketData:
    def test_market_values_of_the_purged_source_are_removed(self, shared_player) -> None:
        session, player = shared_player
        market_value(session, player, MARKET, dt.date(2025, 1, 1), 4_000_000)
        market_value(session, player, MARKET, dt.date(2025, 6, 1), 5_000_000)

        purge(session, MARKET)
        session.flush()

        remaining = session.scalar(
            select(func.count())
            .select_from(FactMarketValue)
            .where(FactMarketValue.source == MARKET)
        )
        assert remaining == 0

    def test_transfers_of_the_purged_source_are_removed(self, shared_player) -> None:
        session, player = shared_player
        transfer(session, player, MARKET, dt.date(2024, 7, 1))

        purge(session, MARKET)
        session.flush()

        remaining = session.scalar(
            select(func.count()).select_from(FactTransfer).where(FactTransfer.source == MARKET)
        )
        assert remaining == 0

    def test_another_providers_rows_are_untouched(self, shared_player) -> None:
        """The half of the requirement a `DELETE FROM` would fail."""
        session, player = shared_player
        market_value(session, player, MARKET, dt.date(2025, 1, 1), 4_000_000)
        market_value(session, player, PERFORMANCE, dt.date(2025, 1, 1), 4_200_000)
        transfer(session, player, MARKET, dt.date(2024, 7, 1))
        transfer(session, player, PERFORMANCE, dt.date(2024, 7, 1))

        purge(session, MARKET)
        session.flush()

        survivors = session.scalars(
            select(FactMarketValue.source).where(FactMarketValue.player_id == player.player_id)
        ).all()
        assert survivors == [PERFORMANCE]

        transfers = session.scalars(
            select(FactTransfer.source).where(FactTransfer.player_id == player.player_id)
        ).all()
        assert transfers == [PERFORMANCE]

    def test_the_shared_player_survives(self, shared_player) -> None:
        """Purging a source removes its data, not the person.

        The other provider still knows them, so the identity has to outlive the
        refresh - otherwise every Transfermarkt run would delete the FootyStats
        half of every merged player.
        """
        session, player = shared_player
        purge(session, MARKET)
        session.flush()

        assert session.get(DimPlayer, player.player_id) is not None


class TestRefreshDoesNotAccumulateStaleHistory:
    def test_a_corrected_valuation_replaces_rather_than_joins_the_old_one(
        self, shared_player
    ) -> None:
        """The user-visible symptom: a chart drawing a history that never happened.

        The provider published a valuation on 1 March, then revised its own
        history so the same movement is dated 15 March. Before the fix both
        rows survived a refresh, because they differ on `valued_on` and so
        never violated the uniqueness constraint.
        """
        session, player = shared_player
        market_value(session, player, MARKET, dt.date(2025, 3, 1), 4_000_000)

        # A refresh: purge, then load what the provider says now.
        purge(session, MARKET)
        session.flush()
        market_value(session, player, MARKET, dt.date(2025, 3, 15), 4_000_000)

        rows = session.scalars(
            select(FactMarketValue.valued_on)
            .where(FactMarketValue.player_id == player.player_id)
            .order_by(FactMarketValue.valued_on)
        ).all()
        assert rows == [dt.date(2025, 3, 15)], "the superseded valuation survived the refresh"

    def test_legitimate_history_on_different_dates_is_kept(self, shared_player) -> None:
        """The thing that must NOT happen: deduplicating a real history.

        Two valuations on two dates are two observations, not a duplicate. The
        purge is scoped to a refresh of one source; within a load, distinct
        dates are distinct facts.
        """
        session, player = shared_player
        purge(session, MARKET)
        session.flush()
        market_value(session, player, MARKET, dt.date(2024, 1, 1), 3_000_000)
        market_value(session, player, MARKET, dt.date(2025, 1, 1), 4_000_000)
        market_value(session, player, MARKET, dt.date(2026, 1, 1), 6_000_000)

        count = session.scalar(
            select(func.count())
            .select_from(FactMarketValue)
            .where(FactMarketValue.player_id == player.player_id)
        )
        assert count == 3


class TestOneLogicalPlayerSurvivesRepeatedRefreshes:
    """Sections 2 and 3 together: refresh one provider, resolve, refresh again.

    The sequence the brief asks for. What must hold at the end is that the
    person is still one person, and that only the refreshed provider's rows
    were replaced.
    """

    def test_the_full_cycle(self, db_session: Session) -> None:
        session = db_session

        # Initial state: both providers loaded and already resolved into one.
        player = make_player(session, "Carlos Miguel Santos")
        bridge(session, player, MARKET, "tm-9")
        bridge(session, player, PERFORMANCE, "fs-9")
        market_value(session, player, MARKET, dt.date(2025, 1, 1), 2_000_000)
        market_value(session, player, PERFORMANCE, dt.date(2025, 1, 1), 2_100_000)

        # Refresh the market provider with a changed history.
        purge(session, MARKET)
        session.flush()
        bridge(session, player, MARKET, "tm-9")
        market_value(session, player, MARKET, dt.date(2025, 8, 1), 3_500_000)
        session.flush()

        # One logical player.
        assert (
            session.scalar(
                select(func.count())
                .select_from(DimPlayer)
                .where(DimPlayer.player_id == player.player_id)
            )
            == 1
        )

        # Stale market rows gone, refreshed rows present, other source intact.
        by_source = {
            source: date
            for source, date in session.execute(
                select(FactMarketValue.source, FactMarketValue.valued_on).where(
                    FactMarketValue.player_id == player.player_id
                )
            ).all()
        }
        assert by_source == {
            MARKET: dt.date(2025, 8, 1),
            PERFORMANCE: dt.date(2025, 1, 1),
        }

        # Both providers still know them, so the identity is still joinable.
        sources = set(
            session.scalars(
                select(BridgePlayerSource.source).where(
                    BridgePlayerSource.player_id == player.player_id
                )
            ).all()
        )
        assert sources == {MARKET, PERFORMANCE}
