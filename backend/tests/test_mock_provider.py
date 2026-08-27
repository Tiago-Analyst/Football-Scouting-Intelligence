"""MockPerformanceProvider.

Most of these are property tests over the whole generated dataset rather than
assertions about individual values. The dataset feeds percentiles, role scores
and similarity, so a single record with more completed passes than attempted
would produce a ratio above 1.0 and corrupt every distribution built on it.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

import pytest

from app.providers.base import UnknownEntityError
from app.providers.mock import SEASON_ID, MockPerformanceProvider
from app.schemas.canonical import (
    GOALKEEPER_METRICS,
    CanonicalMetric,
    PlayerIdentity,
    PlayerSeasonStats,
    PositionGroup,
)


@pytest.fixture(scope="module")
def provider() -> MockPerformanceProvider:
    return MockPerformanceProvider()


@pytest.fixture(scope="module")
def all_stats(provider: MockPerformanceProvider) -> list[PlayerSeasonStats]:
    records: list[PlayerSeasonStats] = []
    for competition in provider.get_competitions():
        records.extend(provider.get_competition_stats(competition.competition_id, SEASON_ID))
    return records


@pytest.fixture(scope="module")
def all_players(provider: MockPerformanceProvider) -> list[PlayerIdentity]:
    players: list[PlayerIdentity] = []
    for competition in provider.get_competitions():
        players.extend(provider.get_players(competition.competition_id, SEASON_ID))
    return players


@pytest.fixture(scope="module")
def by_group(
    all_players: list[PlayerIdentity], all_stats: list[PlayerSeasonStats]
) -> dict[PositionGroup, list[PlayerSeasonStats]]:
    group_of = {p.source_player_id: p.position_group for p in all_players}
    grouped: dict[PositionGroup, list[PlayerSeasonStats]] = defaultdict(list)
    for record in all_stats:
        grouped[group_of[record.source_player_id]].append(record)
    return grouped


@pytest.fixture(scope="module")
def limited() -> MockPerformanceProvider:
    """A provider that deliberately cannot supply two metrics."""
    return MockPerformanceProvider(
        competitions=1,
        clubs_per_competition=2,
        unavailable_metrics=frozenset({CanonicalMetric.PROGRESSIVE_PASSES, CanonicalMetric.XA}),
    )


class TestProviderIdentity:
    def test_declares_itself_as_mock(self, provider: MockPerformanceProvider) -> None:
        assert provider.info.is_mock is True

    def test_is_never_marked_validated(self, provider: MockPerformanceProvider) -> None:
        """Nothing here has been checked against a real source, because there is
        no real source. If this ever reads True, the UI would stop labelling
        fabricated figures as unverified."""
        assert provider.info.validated is False

    def test_notes_warn_the_data_is_fabricated(self, provider: MockPerformanceProvider) -> None:
        assert provider.info.notes
        assert "abricated" in provider.info.notes

    def test_offers_every_canonical_metric_by_default(
        self, provider: MockPerformanceProvider
    ) -> None:
        assert provider.info.available_metrics == frozenset(CanonicalMetric)


class TestDeterminism:
    def test_same_seed_produces_identical_data(self) -> None:
        a = MockPerformanceProvider(seed=99, competitions=1, clubs_per_competition=2)
        b = MockPerformanceProvider(seed=99, competitions=1, clubs_per_competition=2)
        assert a.get_competition_stats("mock-comp-01", SEASON_ID) == b.get_competition_stats(
            "mock-comp-01", SEASON_ID
        )

    def test_different_seed_produces_different_data(self) -> None:
        a = MockPerformanceProvider(seed=1, competitions=1, clubs_per_competition=2)
        b = MockPerformanceProvider(seed=2, competitions=1, clubs_per_competition=2)
        assert a.get_competition_stats("mock-comp-01", SEASON_ID) != b.get_competition_stats(
            "mock-comp-01", SEASON_ID
        )


class TestDatasetShape:
    def test_generates_all_competitions(self, provider: MockPerformanceProvider) -> None:
        assert len(provider.get_competitions()) == 4

    def test_every_player_has_exactly_one_stat_record(
        self, all_players: list[PlayerIdentity], all_stats: list[PlayerSeasonStats]
    ) -> None:
        assert len(all_players) == len(all_stats)
        assert len({s.source_player_id for s in all_stats}) == len(all_stats)

    def test_every_position_group_is_populated(self, all_players: list[PlayerIdentity]) -> None:
        """Percentiles are computed within position groups, so an empty group
        would leave a whole cohort unrankable."""
        counts = Counter(p.position_group for p in all_players)
        for group in PositionGroup:
            assert counts[group] >= 100, f"{group} has only {counts[group]} players"

    def test_stats_reference_real_clubs_and_competitions(
        self, provider: MockPerformanceProvider, all_stats: list[PlayerSeasonStats]
    ) -> None:
        competition_ids = {c.competition_id for c in provider.get_competitions()}
        club_ids = {
            club.club_id for cid in competition_ids for club in provider.get_clubs(cid, SEASON_ID)
        }
        for record in all_stats:
            assert record.competition_id in competition_ids
            assert record.club_id in club_ids

    def test_raw_position_maps_into_its_position_group(
        self, all_players: list[PlayerIdentity]
    ) -> None:
        from app.providers.mock import PROFILES

        for player in all_players:
            assert player.raw_position in PROFILES[player.position_group].raw_positions


class TestInternalConsistency:
    def test_no_record_violates_a_structural_constraint(
        self, all_stats: list[PlayerSeasonStats]
    ) -> None:
        violations = [
            (r.source_player_id, errors) for r in all_stats if (errors := r.consistency_errors())
        ]
        assert violations == [], violations[:5]

    @pytest.mark.parametrize(
        ("part", "whole"),
        [
            ("passes_completed", "passes"),
            ("successful_dribbles", "dribbles"),
            ("successful_tackles", "tackles"),
            ("duels_won", "duels"),
            ("aerial_duels_won", "aerial_duels"),
            ("shots_on_target", "shots"),
            ("accurate_crosses", "crosses"),
        ],
    )
    def test_every_derived_ratio_stays_within_zero_and_one(
        self, all_stats: list[PlayerSeasonStats], part: str, whole: str
    ) -> None:
        """A ratio above 1.0 is not merely wrong; it would rank a player above
        the theoretical maximum in a percentile distribution."""
        for record in all_stats:
            denominator = getattr(record, whole)
            if not denominator:
                continue
            ratio = getattr(record, part) / denominator
            assert 0.0 <= ratio <= 1.0, f"{record.source_player_id}: {part}/{whole}={ratio}"

    def test_minutes_never_exceed_ninety_per_appearance(
        self, all_stats: list[PlayerSeasonStats]
    ) -> None:
        for record in all_stats:
            assert record.minutes is not None and record.appearances is not None
            assert record.minutes <= record.appearances * 90


class TestPositionalRealism:
    """Guards against a generator change that silently destroys plausibility."""

    @staticmethod
    def _median_per90(records: list[PlayerSeasonStats], metric: str) -> float:
        values = [
            getattr(r, metric) * 90.0 / r.minutes
            for r in records
            if r.minutes and r.minutes >= 900 and getattr(r, metric) is not None
        ]
        return statistics.median(values) if values else 0.0

    def test_centre_backs_clear_more_than_forwards(self, by_group) -> None:
        assert self._median_per90(by_group[PositionGroup.CB], "clearances") > self._median_per90(
            by_group[PositionGroup.FORWARD], "clearances"
        )

    def test_forwards_shoot_more_than_centre_backs(self, by_group) -> None:
        assert self._median_per90(by_group[PositionGroup.FORWARD], "shots") > self._median_per90(
            by_group[PositionGroup.CB], "shots"
        )

    def test_wingers_cross_more_than_central_midfielders(self, by_group) -> None:
        assert self._median_per90(by_group[PositionGroup.WINGER], "crosses") > self._median_per90(
            by_group[PositionGroup.CM], "crosses"
        )

    def test_defensive_midfielders_pass_more_than_forwards(self, by_group) -> None:
        assert self._median_per90(by_group[PositionGroup.DM], "passes") > self._median_per90(
            by_group[PositionGroup.FORWARD], "passes"
        )

    def test_attacking_midfielders_create_more_than_centre_backs(self, by_group) -> None:
        assert self._median_per90(by_group[PositionGroup.AM], "key_passes") > self._median_per90(
            by_group[PositionGroup.CB], "key_passes"
        )

    @pytest.mark.parametrize(
        ("metric", "maximum"),
        [
            ("passes", 90.0),
            ("progressive_passes", 12.0),
            ("key_passes", 4.5),
            ("tackles", 5.5),
            ("shots", 7.0),
            ("npxg", 1.2),
        ],
    )
    def test_no_position_group_produces_implausible_output(
        self, by_group, metric: str, maximum: float
    ) -> None:
        """Checks the 99th percentile, not the maximum: a long tail is expected,
        an impossible one is not."""
        for group in PositionGroup:
            values = sorted(
                getattr(r, metric) * 90.0 / r.minutes
                for r in by_group[group]
                if r.minutes and r.minutes >= 900 and getattr(r, metric) is not None
            )
            if len(values) < 20:
                continue
            p99 = values[int(len(values) * 0.99) - 1]
            assert p99 <= maximum, f"{group.value} {metric} 99th pct = {p99:.2f}"

    def test_ability_variation_produces_a_usable_spread(self, by_group) -> None:
        """Similarity and role scoring need genuine variation. If every player
        landed on the same figure, ranking would be arbitrary."""
        values = sorted(
            r.progressive_passes * 90.0 / r.minutes
            for r in by_group[PositionGroup.DM]
            if r.minutes and r.minutes >= 900 and r.progressive_passes is not None
        )
        p10 = values[int(len(values) * 0.10)]
        p90 = values[int(len(values) * 0.90)]
        assert p90 > p10 * 1.6, f"insufficient spread: p10={p10:.2f} p90={p90:.2f}"


class TestSampleSizeCoverage:
    def test_all_three_sample_bands_are_represented(
        self, all_stats: list[PlayerSeasonStats]
    ) -> None:
        """The minutes rules cannot be exercised without players in each band."""
        bands = Counter()
        for record in all_stats:
            minutes = record.minutes or 0
            bands["full" if minutes >= 900 else "low" if minutes >= 450 else "insufficient"] += 1
        assert bands["full"] >= 100
        assert bands["low"] >= 20
        assert bands["insufficient"] >= 20


class TestGoalkeeperMetrics:
    def test_goalkeepers_have_goalkeeping_data(
        self, all_players: list[PlayerIdentity], provider: MockPerformanceProvider
    ) -> None:
        keepers = [p for p in all_players if p.position_group is PositionGroup.GK]
        assert keepers
        for keeper in keepers[:40]:
            record = provider.get_player_stats(keeper.source_player_id, SEASON_ID)
            assert record is not None
            assert record.saves is not None
            assert record.goals_conceded is not None

    def test_outfield_players_have_no_goalkeeping_data(
        self, all_players: list[PlayerIdentity], provider: MockPerformanceProvider
    ) -> None:
        """Absent, not zero: an outfield player has not kept zero clean sheets,
        the metric simply does not apply."""
        outfield = [p for p in all_players if p.position_group is not PositionGroup.GK]
        for player in outfield[:60]:
            record = provider.get_player_stats(player.source_player_id, SEASON_ID)
            assert record is not None
            for metric in GOALKEEPER_METRICS:
                assert record.get(metric) is None, f"{player.source_player_id} has {metric}"


class TestLookups:
    def test_unknown_player_returns_none(self, provider: MockPerformanceProvider) -> None:
        assert provider.get_player_stats("does-not-exist", SEASON_ID) is None

    def test_known_player_returns_their_record(
        self, provider: MockPerformanceProvider, all_players: list[PlayerIdentity]
    ) -> None:
        player = all_players[0]
        record = provider.get_player_stats(player.source_player_id, SEASON_ID)
        assert record is not None
        assert record.source_player_id == player.source_player_id

    @pytest.mark.parametrize(
        "call",
        ["get_seasons", "get_clubs", "get_players", "get_competition_stats"],
    )
    def test_unknown_competition_raises(self, provider: MockPerformanceProvider, call: str) -> None:
        method = getattr(provider, call)
        args = (
            ("no-such-competition",)
            if call == "get_seasons"
            else (
                "no-such-competition",
                SEASON_ID,
            )
        )
        with pytest.raises(UnknownEntityError):
            method(*args)

    def test_unknown_season_raises(self, provider: MockPerformanceProvider) -> None:
        with pytest.raises(UnknownEntityError):
            provider.get_players("mock-comp-01", "1999-2000")


class TestSimulatedUnavailability:
    """Lets the rest of the application be tested against a provider that
    cannot supply everything - the situation a real provider is likely to
    present."""

    def test_withheld_metrics_are_absent_from_declared_availability(
        self, limited: MockPerformanceProvider
    ) -> None:
        assert not limited.info.supports(CanonicalMetric.PROGRESSIVE_PASSES)
        assert not limited.info.supports(CanonicalMetric.XA)
        assert limited.info.supports(CanonicalMetric.TACKLES)

    def test_withheld_metrics_are_none_on_every_record(
        self, limited: MockPerformanceProvider
    ) -> None:
        """Declaring a metric unavailable while still returning a value would
        let a caller read data it was told did not exist."""
        records = limited.get_competition_stats("mock-comp-01", SEASON_ID)
        assert records
        for record in records:
            assert record.progressive_passes is None
            assert record.xa is None

    def test_withholding_applies_to_single_lookups_too(
        self, limited: MockPerformanceProvider
    ) -> None:
        players = limited.get_players("mock-comp-01", SEASON_ID)
        record = limited.get_player_stats(players[0].source_player_id, SEASON_ID)
        assert record is not None
        assert record.progressive_passes is None

    def test_other_metrics_are_unaffected(self, limited: MockPerformanceProvider) -> None:
        records = limited.get_competition_stats("mock-comp-01", SEASON_ID)
        assert any(r.passes is not None for r in records)
        assert any(r.tackles is not None for r in records)
