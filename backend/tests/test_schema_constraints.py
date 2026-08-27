"""Database constraints.

The section 24 quality rules are enforced by the schema itself, not only by the
loader. That matters because the loader is not the only thing that will ever
write here: a migration, a manual fix or a future pipeline could all introduce
an impossible value, and a CHECK constraint is the one guard none of them can
bypass.

Each test asserts the database *rejects* bad data, so a dropped constraint fails
the suite rather than silently allowing corruption.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
)

pytestmark = pytest.mark.integration

COMPETITION = "test:comp"
CLUB = "test:club"
SEASON = "test:2026-2027"


@pytest.fixture
def seeded(db_session: Session) -> Session:
    """Minimal reference data so facts have something to point at."""
    # Flushed in dependency order. These models declare foreign keys but no
    # relationships, and the ORM derives its insert ordering from relationships,
    # so it will not reorder these for us.
    db_session.add(
        DimCompetition(competition_id=COMPETITION, name="Test League", country="X", source="test")
    )
    db_session.add(DimSeason(season_id=SEASON, name="2026/27", start_year=2026, end_year=2027))
    db_session.flush()

    db_session.add(DimClub(club_id=CLUB, name="Test FC", competition_id=COMPETITION, source="test"))
    db_session.flush()
    return db_session


def _player(session: Session, **overrides: object) -> DimPlayer:
    player = DimPlayer(
        full_name=overrides.pop("full_name", "Test Player"),  # type: ignore[arg-type]
        normalized_name=overrides.pop("normalized_name", "test player"),  # type: ignore[arg-type]
        **overrides,  # type: ignore[arg-type]
    )
    session.add(player)
    session.flush()
    return player


class TestPlayerConstraints:
    def test_valid_player_is_accepted(self, seeded: Session) -> None:
        player = _player(seeded, height_cm=182, current_market_value_eur=4_000_000)
        assert player.player_id is not None

    @pytest.mark.parametrize("height", [18, 139, 221, 300])
    def test_implausible_height_is_rejected(self, seeded: Session, height: int) -> None:
        """The Transfermarkt snapshot really does contain 18cm players. The
        loader drops those, and this makes the database refuse them too."""
        with pytest.raises(IntegrityError):
            _player(seeded, height_cm=height)

    def test_absent_height_is_allowed(self, seeded: Session) -> None:
        assert _player(seeded, height_cm=None).height_cm is None

    def test_negative_market_value_is_rejected(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            _player(seeded, current_market_value_eur=-1)

    def test_absurd_birth_date_is_rejected(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            _player(seeded, date_of_birth=date(1850, 1, 1))


class TestBridgeConstraints:
    def test_one_source_id_maps_to_one_player(self, seeded: Session) -> None:
        """Without this, a re-run would split one career across two players."""
        first = _player(seeded)
        second = _player(seeded, full_name="Other")
        seeded.add(
            BridgePlayerSource(
                player_id=first.player_id,
                source="test",
                source_player_id="p1",
                match_method="source_native_id",
                match_confidence=1.0,
            )
        )
        seeded.flush()
        seeded.add(
            BridgePlayerSource(
                player_id=second.player_id,
                source="test",
                source_player_id="p1",
                match_method="source_native_id",
                match_confidence=1.0,
            )
        )
        with pytest.raises(IntegrityError):
            seeded.flush()

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_confidence_outside_zero_to_one_is_rejected(
        self, seeded: Session, confidence: float
    ) -> None:
        player = _player(seeded)
        seeded.add(
            BridgePlayerSource(
                player_id=player.player_id,
                source="test",
                source_player_id="p9",
                match_method="fuzzy",
                match_confidence=confidence,
            )
        )
        with pytest.raises(IntegrityError):
            seeded.flush()


class TestSeasonStatsConstraints:
    def _stats(
        self, session: Session, player: DimPlayer, **metrics: object
    ) -> FactPlayerSeasonStats:
        row = FactPlayerSeasonStats(
            player_id=player.player_id,
            club_id=CLUB,
            competition_id=COMPETITION,
            season_id=SEASON,
            source="test",
            **metrics,  # type: ignore[arg-type]
        )
        session.add(row)
        session.flush()
        return row

    def test_absent_metric_stays_null_and_is_not_coerced_to_zero(self, seeded: Session) -> None:
        """The central rule, checked at the storage layer: an unsupplied metric
        must round-trip as NULL, not as 0."""
        row = self._stats(seeded, _player(seeded), minutes=1800)
        seeded.refresh(row)
        assert row.minutes == 1800
        assert row.tackles is None
        assert row.xg is None

    def test_genuine_zero_is_preserved(self, seeded: Session) -> None:
        row = self._stats(seeded, _player(seeded), tackles=0)
        seeded.refresh(row)
        assert row.tackles == 0

    @pytest.mark.parametrize("metric", ["minutes", "goals", "shots", "tackles", "saves"])
    def test_negative_counts_are_rejected(self, seeded: Session, metric: str) -> None:
        with pytest.raises(IntegrityError):
            self._stats(seeded, _player(seeded), **{metric: -1})

    def test_completed_passes_cannot_exceed_attempted(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            self._stats(seeded, _player(seeded), passes=100, passes_completed=101)

    def test_shots_on_target_cannot_exceed_shots(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            self._stats(seeded, _player(seeded), shots=10, shots_on_target=11)

    def test_duels_won_cannot_exceed_duels(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            self._stats(seeded, _player(seeded), duels=50, duels_won=51)

    def test_minutes_cannot_exceed_time_available(self, seeded: Session) -> None:
        with pytest.raises(IntegrityError):
            self._stats(seeded, _player(seeded), appearances=2, minutes=900)

    def test_partial_data_does_not_trip_subset_checks(self, seeded: Session) -> None:
        """A provider supplying only one side of a pair must not be rejected;
        an unknown value cannot contradict anything."""
        row = self._stats(seeded, _player(seeded), passes_completed=500)
        assert row.passes is None

    def test_duplicate_player_competition_season_is_rejected(self, seeded: Session) -> None:
        player = _player(seeded)
        self._stats(seeded, player, minutes=900)
        with pytest.raises(IntegrityError):
            self._stats(seeded, player, minutes=1000)


class TestMarketValueConstraints:
    def test_negative_valuation_is_rejected(self, seeded: Session) -> None:
        player = _player(seeded)
        seeded.add(
            FactMarketValue(
                player_id=player.player_id,
                valued_on=date(2026, 1, 1),
                market_value_eur=-5,
                source="test",
            )
        )
        with pytest.raises(IntegrityError):
            seeded.flush()

    def test_one_valuation_per_player_date_and_source(self, seeded: Session) -> None:
        player = _player(seeded)
        for _ in range(2):
            seeded.add(
                FactMarketValue(
                    player_id=player.player_id,
                    valued_on=date(2026, 1, 1),
                    market_value_eur=1000,
                    source="test",
                )
            )
        with pytest.raises(IntegrityError):
            seeded.flush()


class TestDataQualityConstraints:
    def test_only_known_statuses_are_accepted(self, db_session: Session) -> None:
        db_session.add(FactDataQuality(source="test", entity="x", check_name="c", status="maybe"))
        with pytest.raises(IntegrityError):
            db_session.flush()

    @pytest.mark.parametrize("status", ["pass", "warn", "fail"])
    def test_valid_statuses_are_accepted(self, db_session: Session, status: str) -> None:
        row = FactDataQuality(
            source="test", entity="x", check_name="c", status=status, record_count=3
        )
        db_session.add(row)
        db_session.flush()
        assert row.id is not None
