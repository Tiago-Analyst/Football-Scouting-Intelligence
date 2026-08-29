"""Merging two source rows into one player.

This is the only operation in the project that destroys a row, and the row it
destroys is one another table still points at. All three defects found here
were the same defect wearing different clothes: something pointing at the
duplicate was not moved before the duplicate was deleted, and the cascade took
it away in silence.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.identity_resolution.resolve import merge_player
from pipelines.load.load_providers import _normalize, purge, reconcile_contradictions
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactPlayerSeasonStats,
)
from app.schemas.canonical import PositionGroup

pytestmark = pytest.mark.integration

PERFORMANCE = "test_perf"
IDENTITY = "test_ident"

Pair = tuple[DimPlayer, DimPlayer, BridgePlayerSource, str]


def make_player(session: Session, name: str, *, position: PositionGroup | None) -> DimPlayer:
    player = DimPlayer(
        full_name=name,
        normalized_name=_normalize(name),
        date_of_birth=dt.date(1999, 5, 5),
        nationality="Portugal",
        position_group=position,
    )
    session.add(player)
    session.flush()
    return player


def bridge(session: Session, player: DimPlayer, source: str, source_id: str) -> BridgePlayerSource:
    row = BridgePlayerSource(
        player_id=player.player_id,
        source=source,
        source_player_id=source_id,
        match_method="source_native_id",
        match_confidence=1.0,
        manual_override=False,
    )
    session.add(row)
    session.flush()
    return row


def competition(session: Session, key: str) -> str:
    session.add(
        DimCompetition(
            competition_id=key,
            name=f"Competition {key}",
            country="Portugal",
            tier=1,
            source=PERFORMANCE,
        )
    )
    session.flush()
    return key


def season(session: Session, key: str) -> str:
    if session.get(DimSeason, key) is None:
        session.add(DimSeason(season_id=key, name=key, start_year=2024, end_year=2025))
        session.flush()
    return key


def stats(session: Session, player: DimPlayer, competition_id: str, season_id: str) -> None:
    session.add(
        FactPlayerSeasonStats(
            player_id=player.player_id,
            competition_id=competition_id,
            season_id=season(session, season_id),
            appearances=10,
            minutes=900,
            goals=3,
            source=PERFORMANCE,
        )
    )
    session.flush()


@pytest.fixture
def pair(db_session: Session) -> Pair:
    """One human being as two rows: performance without a position, identity with one."""
    performance = make_player(db_session, "Joao Silva", position=None)
    identity = make_player(db_session, "Joao Silva", position=PositionGroup.CM)
    performance_bridge = bridge(db_session, performance, PERFORMANCE, "p1")
    bridge(db_session, identity, IDENTITY, "t1")
    key = competition(db_session, f"{PERFORMANCE}:c1")
    stats(db_session, performance, key, "2024")
    return performance, identity, performance_bridge, key


class TestMerging:
    def test_the_statistics_move_and_the_duplicate_goes(
        self, db_session: Session, pair: Pair
    ) -> None:
        performance, identity, performance_bridge, _ = pair

        assert merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )

        moved = db_session.scalars(
            select(FactPlayerSeasonStats).where(
                FactPlayerSeasonStats.player_id == identity.player_id
            )
        ).all()
        assert len(moved) == 1
        assert db_session.get(DimPlayer, performance.player_id) is None

    def test_the_position_group_is_what_the_merge_buys(
        self, db_session: Session, pair: Pair
    ) -> None:
        """The whole point of the phase: statistics arrive without a usable
        position, and rankings are position-scoped. Before the merge the row
        carrying them cannot be ranked at all."""
        performance, identity, performance_bridge, _ = pair
        assert performance.position_group is None

        merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )

        row = db_session.scalars(
            select(DimPlayer)
            .join(FactPlayerSeasonStats, DimPlayer.player_id == FactPlayerSeasonStats.player_id)
            .where(FactPlayerSeasonStats.source == PERFORMANCE)
        ).first()
        assert row is not None
        assert row.position_group is PositionGroup.CM

    def test_the_bridge_survives_the_cascade(self, db_session: Session, pair: Pair) -> None:
        """Regression. `dim_player` cascades to `bridge_player_source`, so a
        caller that updated the bridge *after* the delete updated nothing and
        was told nothing - and the mapping back to the provider's id was gone.
        Losing it breaks nothing visibly; it just recreates the duplicate on the
        next run."""
        performance, identity, performance_bridge, _ = pair

        merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )

        surviving = db_session.scalars(
            select(BridgePlayerSource).where(BridgePlayerSource.source == PERFORMANCE)
        ).all()
        assert len(surviving) == 1
        assert surviving[0].source_player_id == "p1"
        assert surviving[0].player_id == identity.player_id
        assert surviving[0].match_confidence == pytest.approx(0.98)

    def test_a_bridge_that_cannot_be_moved_stops_the_merge(
        self, db_session: Session, pair: Pair
    ) -> None:
        """Refusing loudly beats deleting the duplicate and losing the mapping."""
        performance, identity, _, _ = pair
        with pytest.raises(RuntimeError, match="not repointed"):
            merge_player(
                db_session,
                performance.player_id,
                identity.player_id,
                bridge_id=-1,
                method="exact_name+dob",
                confidence=0.98,
            )

    def test_a_colliding_season_is_refused_rather_than_overwritten(
        self, db_session: Session, pair: Pair
    ) -> None:
        """Both rows carrying the same competition and season means merging
        would discard one of the two, and there is no rule saying which."""
        performance, identity, performance_bridge, key = pair
        stats(db_session, identity, key, "2024")

        assert not merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )
        assert db_session.get(DimPlayer, performance.player_id) is not None
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(FactPlayerSeasonStats)
                .where(FactPlayerSeasonStats.player_id == performance.player_id)
            )
            == 1
        )


class TestPurgingAfterAMerge:
    def test_purging_one_source_leaves_the_shared_identity_alone(
        self, db_session: Session, pair: Pair
    ) -> None:
        """Once merged, the performance bridge points at the identity row. A
        purge that deletes players through their bridge rows would take the
        other source's player with it - market values, transfers and all."""
        performance, identity, performance_bridge, _ = pair
        merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )

        purge(db_session, PERFORMANCE)
        db_session.flush()

        assert db_session.get(DimPlayer, identity.player_id) is not None
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(BridgePlayerSource)
                .where(BridgePlayerSource.source == IDENTITY)
            )
            == 1
        )

    def test_purging_removes_its_own_facts_and_bridge(
        self, db_session: Session, pair: Pair
    ) -> None:
        """Surviving the purge must not mean outliving the data it named."""
        performance, identity, performance_bridge, _ = pair
        merge_player(
            db_session,
            performance.player_id,
            identity.player_id,
            bridge_id=performance_bridge.id,
            method="exact_name+dob",
            confidence=0.98,
        )

        purge(db_session, PERFORMANCE)
        db_session.flush()

        for model, where in (
            (FactPlayerSeasonStats, FactPlayerSeasonStats.source == PERFORMANCE),
            (BridgePlayerSource, BridgePlayerSource.source == PERFORMANCE),
        ):
            assert db_session.scalar(select(func.count()).select_from(model).where(where)) == 0

    def test_an_unmerged_player_is_still_removed(self, db_session: Session) -> None:
        """The ordinary case must keep working: a player only this source knows
        has no reason to stay."""
        only_here = make_player(db_session, "Solo Player", position=None)
        bridge(db_session, only_here, PERFORMANCE, "p9")

        purge(db_session, PERFORMANCE)
        db_session.flush()

        assert db_session.get(DimPlayer, only_here.player_id) is None


class TestContradictions:
    """Observed in real FootyStats data: one shot, two shots on target."""

    def test_both_halves_are_blanked_not_one(self) -> None:
        """Keeping either number would be picking one at random and presenting
        the guess as measurement."""
        row: dict[str, object] = {"shots": 1, "shots_on_target": 2}
        assert reconcile_contradictions(row) == ["shots_on_target>shots"]
        assert row == {"shots": None, "shots_on_target": None}

    def test_consistent_rows_are_untouched(self) -> None:
        row: dict[str, object] = {
            "shots": 5,
            "shots_on_target": 2,
            "passes": 40,
            "passes_completed": 40,
        }
        assert reconcile_contradictions(row) == []
        assert row["shots"] == 5
        assert row["passes_completed"] == 40

    def test_absence_is_not_a_contradiction(self) -> None:
        """`None` means unknown, and unknown cannot exceed anything."""
        row: dict[str, object] = {
            "shots": None,
            "shots_on_target": 3,
            "duels": 4,
            "duels_won": None,
        }
        assert reconcile_contradictions(row) == []
        assert row["shots_on_target"] == 3

    def test_every_containment_pair_is_checked(self) -> None:
        """Each pair mirrors a CHECK constraint. One left out is a load that
        fails in the database instead of being reported here."""
        row: dict[str, object] = {
            "passes": 1,
            "passes_completed": 2,
            "shots": 1,
            "shots_on_target": 2,
            "duels": 1,
            "duels_won": 2,
            "aerial_duels": 1,
            "aerial_duels_won": 2,
            "goals": 1,
            "non_penalty_goals": 2,
            "minutes": 1,
            "recorded_minutes": 2,
        }
        assert len(reconcile_contradictions(row)) == 6
        assert all(value is None for value in row.values())
