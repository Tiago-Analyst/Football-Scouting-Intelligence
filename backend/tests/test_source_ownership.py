"""Data-quality checks on which source owns which fact.

Section 14 of the brief. These sit downstream of the purge fix in
`test_source_purge.py`: that one proves the loader cleans up after itself,
these prove the database says so afterwards. The distinction matters because
the symptom of a half-cleaned refresh is invisible from inside a load - every
row is well-formed, and only the shape of a player's history is wrong.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.load.load_providers import _normalize
from pipelines.quality.report import ownership_checks
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimPlayer,
    FactMarketValue,
    FactTransfer,
)
from app.schemas.canonical import PositionGroup

pytestmark = pytest.mark.integration

MARKET = "test_own_market"
PERF = "test_own_perf"


def by_name(session: Session) -> dict[str, object]:
    return {f"{c.entity}.{c.name}": c for c in ownership_checks(session)}


def make_player(session: Session, name: str) -> DimPlayer:
    player = DimPlayer(
        full_name=name,
        normalized_name=_normalize(name),
        date_of_birth=dt.date(1997, 2, 2),
        nationality="Portugal",
        position_group=PositionGroup.CB,
    )
    session.add(player)
    session.flush()
    return player


class TestTheChecksExist:
    def test_every_required_check_is_produced(self, db_session: Session) -> None:
        names = set(by_name(db_session))
        for required in (
            "fact_market_value.no_facts_from_a_source_that_loads_nothing",
            "fact_transfer.no_facts_from_a_source_that_loads_nothing",
            "fact_player_season_stats.no_facts_from_a_source_that_loads_nothing",
            "fact_market_value.no_orphaned_player_ids",
            "fact_transfer.no_orphaned_player_ids",
            "fact_market_value.no_duplicate_same_source_valuation",
            "bridge_player_source.no_mapping_to_a_missing_player",
        ):
            assert required in names, required

    def test_they_pass_on_the_loaded_database(self, db_session: Session) -> None:
        """The state a refresh should leave behind."""
        failing = [c for c in ownership_checks(db_session) if c.status == "fail"]
        assert failing == [], [f"{c.entity}.{c.name}: {c.detail}" for c in failing]


class TestStaleFactsFromAPurgedSource:
    def test_market_values_with_no_mappings_behind_them_fail(self, db_session: Session) -> None:
        """Exactly what the old purge left: rows whose source loads nobody.

        The player row survives a purge when another provider still knows them.
        Their market history used to survive with it, so the source had facts
        here and no bridge rows anywhere.
        """
        player = make_player(db_session, "Orphaned History Player")
        db_session.add(
            FactMarketValue(
                player_id=player.player_id,
                valued_on=dt.date(2025, 1, 1),
                market_value_eur=1_000_000,
                source=MARKET,
            )
        )
        db_session.flush()

        check = by_name(db_session)["fact_market_value.no_facts_from_a_source_that_loads_nothing"]
        assert check.status == "fail"
        assert MARKET in (check.detail or "")

    def test_transfers_with_no_mappings_behind_them_fail(self, db_session: Session) -> None:
        player = make_player(db_session, "Orphaned Transfer Player")
        db_session.add(
            FactTransfer(
                player_id=player.player_id,
                transfer_date=dt.date(2025, 1, 1),
                transfer_type="permanent",
                source=MARKET,
            )
        )
        db_session.flush()

        check = by_name(db_session)["fact_transfer.no_facts_from_a_source_that_loads_nothing"]
        assert check.status == "fail"

    def test_a_source_that_still_loads_players_passes(self, db_session: Session) -> None:
        """The same rows, with the bridge intact, are an ordinary load."""
        player = make_player(db_session, "Properly Loaded Player")
        db_session.add(
            BridgePlayerSource(
                player_id=player.player_id,
                source=MARKET,
                source_player_id="tm-77",
                match_method="source_native_id",
                match_confidence=1.0,
            )
        )
        db_session.add(
            FactMarketValue(
                player_id=player.player_id,
                valued_on=dt.date(2025, 1, 1),
                market_value_eur=1_000_000,
                source=MARKET,
            )
        )
        db_session.flush()

        check = by_name(db_session)["fact_market_value.no_facts_from_a_source_that_loads_nothing"]
        assert check.status != "fail"


class TestLegitimateHistoryIsNotFlagged:
    def test_several_valuations_on_several_dates_are_not_duplicates(
        self, db_session: Session
    ) -> None:
        """The thing that must never be 'cleaned up'.

        A market history is many observations of one player. Only the same
        source claiming the same player on the same date is a duplicate.
        """
        player = make_player(db_session, "Long History Player")
        db_session.add(
            BridgePlayerSource(
                player_id=player.player_id,
                source=MARKET,
                source_player_id="tm-88",
                match_method="source_native_id",
                match_confidence=1.0,
            )
        )
        for year, value in ((2023, 1_000_000), (2024, 2_000_000), (2025, 4_000_000)):
            db_session.add(
                FactMarketValue(
                    player_id=player.player_id,
                    valued_on=dt.date(year, 6, 1),
                    market_value_eur=value,
                    source=MARKET,
                )
            )
        db_session.flush()

        check = by_name(db_session)["fact_market_value.no_duplicate_same_source_valuation"]
        assert check.status != "fail"

    def test_two_sources_valuing_the_same_day_are_not_duplicates(self, db_session: Session) -> None:
        """Two providers disagreeing about one date is two opinions."""
        player = make_player(db_session, "Two Opinions Player")
        for source, source_id in ((MARKET, "tm-99"), (PERF, "fs-99")):
            db_session.add(
                BridgePlayerSource(
                    player_id=player.player_id,
                    source=source,
                    source_player_id=source_id,
                    match_method="source_native_id",
                    match_confidence=1.0,
                )
            )
            db_session.add(
                FactMarketValue(
                    player_id=player.player_id,
                    valued_on=dt.date(2025, 6, 1),
                    market_value_eur=1_000_000 if source == MARKET else 1_200_000,
                    source=source,
                )
            )
        db_session.flush()

        check = by_name(db_session)["fact_market_value.no_duplicate_same_source_valuation"]
        assert check.status != "fail"


class TestTheChecksAreInTheReport:
    def test_the_report_runs_them(self, db_session: Session) -> None:
        """A check nothing calls protects nothing."""
        from pipelines.quality.report import run

        names = {f"{c.entity}.{c.name}" for c in run(db_session)}
        assert "fact_market_value.no_orphaned_player_ids" in names
        assert "bridge_player_source.no_mapping_to_a_missing_player" in names
