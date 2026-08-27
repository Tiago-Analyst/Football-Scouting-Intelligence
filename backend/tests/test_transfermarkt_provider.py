"""TransfermarktDatasetProvider, against the real snapshot.

Marked `snapshot` and skipped when the archive is absent: the archive is
218 MB and is not downloaded in CI. Run
`python -m pipelines.transfermarkt.download` from the repository root first.

The assertions worth having here are the ones that catch a mapping quietly
inventing information - a substituted field, a guessed transfer type, an
impossible value passed through.
"""

from __future__ import annotations

import pytest

from app.providers.market_base import MarketDataUnavailableError
from app.providers.transfermarkt import (
    DEFAULT_TABLES_DIR,
    MAX_HEIGHT_CM,
    MIN_HEIGHT_CM,
    REQUIRED_TABLES,
    TransfermarktDatasetProvider,
    _load_position_mapping,
)
from app.schemas.canonical import PositionGroup
from app.schemas.market import TransferType

pytestmark = pytest.mark.snapshot

SNAPSHOT_PRESENT = all((DEFAULT_TABLES_DIR / f"{name}.csv.gz").exists() for name in REQUIRED_TABLES)
requires_snapshot = pytest.mark.skipif(
    not SNAPSHOT_PRESENT,
    reason="Transfermarkt snapshot not downloaded; run pipelines.transfermarkt.download",
)


@pytest.fixture(scope="module")
def provider() -> TransfermarktDatasetProvider:
    return TransfermarktDatasetProvider()


@pytest.fixture(scope="module")
def players(provider: TransfermarktDatasetProvider) -> list:
    return provider.get_players()


@pytest.fixture(scope="module")
def transfers(provider: TransfermarktDatasetProvider, players: list) -> list:
    """The first player in the sample who actually has transfer records."""
    for player in players[:1500]:
        records = provider.get_transfers(player.source_player_id)
        if records:
            return records
    pytest.fail("no player with transfers found in the sample")


class TestPositionMappingConfig:
    """Runs without the snapshot: the config file is committed."""

    def test_every_configured_label_maps_to_a_real_group(self) -> None:
        mapping = _load_position_mapping()
        assert mapping
        for label, group in mapping.items():
            assert isinstance(group, PositionGroup), label

    def test_all_eight_position_groups_are_reachable(self) -> None:
        """A group with no source label would be permanently empty, leaving that
        cohort unrankable."""
        assert set(_load_position_mapping().values()) == set(PositionGroup)


@requires_snapshot
class TestProviderIdentity:
    def test_is_not_mock_and_is_validated(self, provider: TransfermarktDatasetProvider) -> None:
        """Validated is True here precisely because the schema was profiled and
        the mapping written against observed files."""
        info = provider.info
        assert info.is_mock is False
        assert info.validated is True

    def test_records_licence_and_source(self, provider: TransfermarktDatasetProvider) -> None:
        info = provider.info
        assert info.licence == "CC0-1.0"
        assert info.source_url and "dcaribou" in info.source_url


@requires_snapshot
class TestMissingSnapshot:
    def test_absent_tables_raise_rather_than_returning_empty(self, tmp_path) -> None:
        """An empty result set would look like 'no players exist', which is
        indistinguishable from a successful read of nothing."""
        with pytest.raises(MarketDataUnavailableError):
            TransfermarktDatasetProvider(tables_dir=tmp_path)


@requires_snapshot
class TestPlayerMapping:
    def test_loads_the_full_player_set(self, players: list) -> None:
        assert len(players) > 40_000

    def test_names_are_normalised_for_identity_resolution(self, players: list) -> None:
        for player in players[:500]:
            assert player.normalized_name == player.normalized_name.lower()
            assert "  " not in player.normalized_name

    def test_accented_names_fold(self, players: list) -> None:
        accented = [p for p in players if any(ch in p.full_name for ch in "áéíóúüñçãõ")]
        assert accented, "expected accented names in a European dataset"
        for player in accented[:50]:
            assert not any(ch in player.normalized_name for ch in "áéíóúüñçãõ")

    def test_secondary_nationality_is_never_populated(self, players: list) -> None:
        """The source has no such field. Country of birth is a different fact
        and must not be substituted for it."""
        assert all(p.secondary_nationality is None for p in players)

    def test_every_height_is_plausible_or_absent(self, players: list) -> None:
        for player in players:
            if player.height_cm is not None:
                assert MIN_HEIGHT_CM <= player.height_cm <= MAX_HEIGHT_CM

    def test_implausible_heights_are_recorded_not_silently_dropped(
        self, provider: TransfermarktDatasetProvider, players: list
    ) -> None:
        issues = [i for i in provider.quality_issues() if i.field == "height_in_cm"]
        assert issues, "the snapshot contains sub-20cm heights; they must be reported"
        for issue in issues:
            assert issue.entity == "player"
            assert "treated as unknown" in issue.reason

    def test_position_groups_are_mapped_for_almost_every_player(self, players: list) -> None:
        mapped = sum(1 for p in players if p.position_group is not None)
        assert mapped / len(players) > 0.95

    def test_unmapped_players_are_exactly_those_without_a_sub_position(self, players: list) -> None:
        """The source writes the literal string 'Missing'; treating it as a real
        label would create a bogus position group."""
        for player in players:
            if player.position_group is None:
                assert player.raw_sub_position is None

    def test_market_value_is_absent_rather_than_zero_when_unreported(self, players: list) -> None:
        assert any(p.market_value_eur is None for p in players)
        assert all(p.market_value_eur != 0 for p in players)

    def test_contract_expiry_is_optional(self, players: list) -> None:
        """Only about 63% of players carry one; code consuming it must handle
        absence."""
        with_contract = sum(1 for p in players if p.contract_expires is not None)
        assert 0 < with_contract < len(players)


@requires_snapshot
class TestClubsAndCompetitions:
    def test_club_country_is_derived_from_its_competition(
        self, provider: TransfermarktDatasetProvider
    ) -> None:
        clubs = provider.get_clubs()
        assert clubs
        assert any(c.country for c in clubs)

    def test_competitions_are_loaded(self, provider: TransfermarktDatasetProvider) -> None:
        competitions = provider.get_competitions()
        assert competitions
        assert all(c.source_competition_id and c.name for c in competitions)


@requires_snapshot
class TestMarketValueHistory:
    def test_history_is_returned_oldest_first(
        self, provider: TransfermarktDatasetProvider, players: list
    ) -> None:
        for player in players[:400]:
            history = provider.get_market_value_history(player.source_player_id)
            if len(history) > 1:
                dates = [point.valued_on for point in history]
                assert dates == sorted(dates)
                return
        pytest.fail("no player with multiple valuations found in the sample")

    def test_unknown_player_returns_empty_history(
        self, provider: TransfermarktDatasetProvider
    ) -> None:
        assert provider.get_market_value_history("999999999") == []


@requires_snapshot
class TestTransfers:
    def test_type_is_always_unknown(self, transfers: list) -> None:
        """The source cannot distinguish loan from permanent, and fee does not
        stand in for it. Asserting UNKNOWN keeps that honest."""
        assert all(t.transfer_type is TransferType.UNKNOWN for t in transfers)

    def test_fees_are_non_negative_when_present(self, transfers: list) -> None:
        assert all(t.fee_eur is None or t.fee_eur >= 0 for t in transfers)

    def test_unknown_player_returns_no_transfers(
        self, provider: TransfermarktDatasetProvider
    ) -> None:
        assert provider.get_transfers("999999999") == []
