"""MockMarketProvider.

The property that matters beyond determinism: demo market data must line up
with demo performance data. Two unrelated fabricated datasets would make every
recruitment feature that relates output to price untestable.
"""

from __future__ import annotations

import pytest

from app.providers.market_mock import MockMarketProvider
from app.providers.mock import REFERENCE_DATE, MockPerformanceProvider
from app.schemas.market import TransferType


@pytest.fixture(scope="module")
def provider() -> MockMarketProvider:
    return MockMarketProvider()


@pytest.fixture(scope="module")
def players(provider: MockMarketProvider) -> list:
    return provider.get_players()


class TestProviderIdentity:
    def test_declares_itself_mock_and_unvalidated(self, provider: MockMarketProvider) -> None:
        info = provider.info
        assert info.is_mock is True
        assert info.validated is False

    def test_carries_no_licence_because_there_is_no_source(
        self, provider: MockMarketProvider
    ) -> None:
        assert provider.info.licence is None


class TestCoherenceWithPerformanceData:
    def test_player_ids_match_the_performance_universe(self, players: list) -> None:
        performance = MockPerformanceProvider()
        performance_ids = {
            p.source_player_id
            for competition in performance.get_competitions()
            for p in performance.get_players(competition.competition_id, "2026-2027")
        }
        market_ids = {p.source_player_id for p in players}
        assert market_ids == performance_ids

    def test_clubs_and_competitions_match(self, provider: MockMarketProvider) -> None:
        performance = MockPerformanceProvider()
        performance_clubs = {
            club.club_id
            for competition in performance.get_competitions()
            for club in performance.get_clubs(competition.competition_id, "2026-2027")
        }
        assert {c.source_club_id for c in provider.get_clubs()} == performance_clubs

    def test_valuations_track_ability(self, players: list) -> None:
        """Not a strict ordering - age and minutes also move the price - but the
        top ability decile must be worth more than the bottom, or the market
        module cannot exercise value-versus-output features."""
        from app.providers.mock import build_dataset

        quality = build_dataset().player_quality
        ranked = sorted(players, key=lambda p: quality[p.source_player_id])
        tenth = max(1, len(ranked) // 10)
        bottom = [p.market_value_eur or 0 for p in ranked[:tenth]]
        top = [p.market_value_eur or 0 for p in ranked[-tenth:]]
        assert sum(top) / len(top) > sum(bottom) / len(bottom) * 3


class TestDeterminism:
    def test_same_seed_produces_identical_valuations(self) -> None:
        a = MockMarketProvider(competitions=1, clubs_per_competition=2)
        b = MockMarketProvider(competitions=1, clubs_per_competition=2)
        assert a.get_players() == b.get_players()

    def test_history_is_stable_across_calls(
        self, provider: MockMarketProvider, players: list
    ) -> None:
        pid = players[0].source_player_id
        assert provider.get_market_value_history(pid) == provider.get_market_value_history(pid)


class TestPlayers:
    def test_every_player_has_a_valuation(self, players: list) -> None:
        assert players
        assert all(p.market_value_eur and p.market_value_eur > 0 for p in players)

    def test_names_are_normalised(self, players: list) -> None:
        assert all(p.normalized_name == p.normalized_name.lower() for p in players)

    def test_filtering_by_competition_narrows_the_result(
        self, provider: MockMarketProvider, players: list
    ) -> None:
        subset = provider.get_players(competition_id="mock-comp-01")
        assert 0 < len(subset) < len(players)
        assert all(p.current_competition_id == "mock-comp-01" for p in subset)

    def test_younger_players_are_not_systematically_cheaper_than_veterans(
        self, players: list
    ) -> None:
        """A 21-year-old should not be priced below a 34-year-old of equal
        ability, or the age filters in recruitment would surface nonsense."""
        young = [p.market_value_eur or 0 for p in players if (p.age_at(REFERENCE_DATE) or 0) <= 22]
        old = [p.market_value_eur or 0 for p in players if (p.age_at(REFERENCE_DATE) or 0) >= 33]
        assert young and old
        assert sum(young) / len(young) > sum(old) / len(old)


class TestHistoryAndTransfers:
    def test_history_ends_at_the_current_valuation(
        self, provider: MockMarketProvider, players: list
    ) -> None:
        player = players[0]
        history = provider.get_market_value_history(player.source_player_id)
        assert history
        assert history[-1].market_value_eur == player.market_value_eur

    def test_history_is_ordered_oldest_first(
        self, provider: MockMarketProvider, players: list
    ) -> None:
        history = provider.get_market_value_history(players[0].source_player_id)
        dates = [point.valued_on for point in history]
        assert dates == sorted(dates)

    def test_unknown_player_yields_nothing(self, provider: MockMarketProvider) -> None:
        assert provider.get_market_value_history("nope") == []
        assert provider.get_transfers("nope") == []

    def test_loans_carry_no_fee(self, provider: MockMarketProvider, players: list) -> None:
        for player in players[:300]:
            for record in provider.get_transfers(player.source_player_id):
                if record.transfer_type is TransferType.LOAN:
                    assert record.fee_eur is None

    def test_transfers_are_ordered_oldest_first(
        self, provider: MockMarketProvider, players: list
    ) -> None:
        for player in players[:300]:
            records = provider.get_transfers(player.source_player_id)
            if len(records) > 1:
                dates = [r.transfer_date for r in records]
                assert dates == sorted(dates)  # type: ignore[type-var]
                return
