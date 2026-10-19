"""Merging every decided pair at once, and still refusing the same ones.

WHY THE BATCH EXISTS

`merge_player` issued five statements per player: two selects to detect a
collision, two updates, one delete. At the ~5,100 merges a real refresh plans,
that is ~25,000 sequential round trips to a database in another region. The step
ran for twenty minutes without finishing, while the load step moves ~900,000
rows into the same database in 178 seconds - because it moves them in sets.

`merge_all` issues four statements for the whole batch. `merge_player` is now a
batch of one, so `test_identity_merge` exercises this same code and every
guarantee it pins still holds.

WHAT A NAIVE BATCH WOULD GET WRONG

Two different FootyStats players can resolve to the same Transfermarkt player -
`resolve` decides each source player independently. The sequential loop caught
the second one's collision because the first one's rows were already there to
collide with. A batch that read the collision state once up front and decided
against that snapshot would not, and would write the merge the loop refused:
one competition-season on one player twice, with one of the two silently
discarded and no rule saying which.

That case is the first test here, and it is the reason the decisions accumulate
as they are made rather than being computed from a snapshot.
"""

from __future__ import annotations

import datetime as dt

import pytest
from pipelines.identity_resolution.resolve import PlannedMerge, merge_all
from pipelines.load.load_providers import _normalize
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

PERFORMANCE = "test_perf_batch"
IDENTITY = "test_ident_batch"


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


def plan(
    performance: DimPlayer, identity: DimPlayer, bridge_row: BridgePlayerSource
) -> PlannedMerge:
    return PlannedMerge(
        performance_player_id=performance.player_id,
        identity_player_id=identity.player_id,
        bridge_id=bridge_row.id,
        method="exact_name+dob",
        confidence=0.98,
    )


class TestItIsActuallyABatch:
    """The claim this change rests on, measured rather than asserted in prose.

    Twenty-five merges cost twenty-five times five statements before. If that
    came back - a stray per-row query slipped into the loop that plans, say -
    every test above would still pass and the step would be slow again, which
    is exactly how this went unnoticed until a sixty-minute job ran out of
    time.
    """

    def test_the_statement_count_does_not_grow_with_the_batch(self, db_session: Session) -> None:
        key = competition(db_session, f"{PERFORMANCE}:counted")
        plans = []
        for index in range(25):
            performance = make_player(db_session, f"Counted {index}", position=None)
            identity = make_player(db_session, f"Counted {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-count-{index}")
            bridge(db_session, identity, IDENTITY, f"t-count-{index}")
            stats(db_session, performance, key, str(2400 + index))
            plans.append(plan(performance, identity, performance_bridge))

        statements = _count_statements(db_session, lambda: merge_all(db_session, plans))

        # One select, one fact update, one bridge update, one delete.
        assert statements == 4, f"{statements} statements for 25 merges"

    def test_chunking_splits_the_writes_and_nothing_else(self, db_session: Session) -> None:
        key = competition(db_session, f"{PERFORMANCE}:counted-chunks")
        plans = []
        for index in range(10):
            performance = make_player(db_session, f"Split {index}", position=None)
            identity = make_player(db_session, f"Split {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-split-{index}")
            bridge(db_session, identity, IDENTITY, f"t-split-{index}")
            stats(db_session, performance, key, str(2500 + index))
            plans.append(plan(performance, identity, performance_bridge))

        from pipelines.identity_resolution import resolve as module

        original = module.MERGE_CHUNK
        module.MERGE_CHUNK = 3
        try:
            statements = _count_statements(db_session, lambda: merge_all(db_session, plans))
        finally:
            module.MERGE_CHUNK = original

        # The one collision select stays one; each write phase becomes four
        # chunks of ten at three per chunk. 1 + 4 + 4 + 4.
        assert statements == 13, f"{statements} statements across four chunks"


def _count_statements(session: Session, work) -> int:  # type: ignore[no-untyped-def]
    """Count statements the session issues while `work` runs."""
    from sqlalchemy import event

    counted = []

    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        counted.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        work()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return len(counted)


class TestCollisionsWithinOneBatch:
    def test_the_second_claim_on_one_season_is_refused(self, db_session: Session) -> None:
        """The case a snapshot-based batch would write and the loop would not.

        Two performance players, one identity player, both carrying the same
        competition and season. Exactly one may move.
        """
        key = competition(db_session, f"{PERFORMANCE}:shared")
        target = make_player(db_session, "Joao Silva", position=PositionGroup.CM)
        bridge(db_session, target, IDENTITY, "t-shared")

        first = make_player(db_session, "Joao Silva", position=None)
        second = make_player(db_session, "Joao Silva", position=None)
        first_bridge = bridge(db_session, first, PERFORMANCE, "p-first")
        second_bridge = bridge(db_session, second, PERFORMANCE, "p-second")
        stats(db_session, first, key, "2024")
        stats(db_session, second, key, "2024")

        outcome = merge_all(
            db_session,
            [plan(first, target, first_bridge), plan(second, target, second_bridge)],
        )

        assert len(outcome.merged) == 1
        assert len(outcome.refused) == 1
        assert outcome.merged[0].performance_player_id == first.player_id
        assert outcome.refused[0].performance_player_id == second.player_id

        # One row for that competition-season, not two and not one overwriting
        # the other.
        held = db_session.execute(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .where(FactPlayerSeasonStats.player_id == target.player_id)
        ).scalar_one()
        assert held == 1

        # And the refused player is untouched: still there, still bridged to
        # itself. Deleting it would lose a season nobody decided to drop.
        assert db_session.get(DimPlayer, second.player_id) is not None
        db_session.refresh(second_bridge)
        assert second_bridge.player_id == second.player_id

    def test_two_claims_on_different_seasons_both_move(self, db_session: Session) -> None:
        """The accumulation must not refuse what does not actually collide."""
        one = competition(db_session, f"{PERFORMANCE}:c-one")
        two = competition(db_session, f"{PERFORMANCE}:c-two")
        target = make_player(db_session, "Ana Costa", position=PositionGroup.CM)
        bridge(db_session, target, IDENTITY, "t-two-seasons")

        first = make_player(db_session, "Ana Costa", position=None)
        second = make_player(db_session, "Ana Costa", position=None)
        first_bridge = bridge(db_session, first, PERFORMANCE, "p-one")
        second_bridge = bridge(db_session, second, PERFORMANCE, "p-two")
        stats(db_session, first, one, "2024")
        stats(db_session, second, two, "2024")

        outcome = merge_all(
            db_session,
            [plan(first, target, first_bridge), plan(second, target, second_bridge)],
        )

        assert len(outcome.merged) == 2
        assert outcome.refused == []
        held = db_session.execute(
            select(func.count())
            .select_from(FactPlayerSeasonStats)
            .where(FactPlayerSeasonStats.player_id == target.player_id)
        ).scalar_one()
        assert held == 2


class TestTheBatchDoesWhatTheLoopDid:
    def test_many_pairs_all_move_and_every_duplicate_goes(self, db_session: Session) -> None:
        key = competition(db_session, f"{PERFORMANCE}:many")
        plans = []
        performances = []
        identities = []
        for index in range(25):
            performance = make_player(db_session, f"Player {index}", position=None)
            identity = make_player(db_session, f"Player {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-many-{index}")
            bridge(db_session, identity, IDENTITY, f"t-many-{index}")
            stats(db_session, performance, key, str(2000 + index))
            plans.append(plan(performance, identity, performance_bridge))
            performances.append(performance)
            identities.append(identity)

        outcome = merge_all(db_session, plans)

        assert len(outcome.merged) == 25
        for performance, identity in zip(performances, identities, strict=True):
            assert db_session.get(DimPlayer, performance.player_id) is None
            moved = db_session.execute(
                select(FactPlayerSeasonStats.player_id).where(
                    FactPlayerSeasonStats.player_id == identity.player_id
                )
            ).all()
            assert len(moved) == 1

    def test_every_bridge_carries_the_method_and_confidence_it_was_given(
        self, db_session: Session
    ) -> None:
        """Per-row values, not one value applied to the batch.

        A single UPDATE is the obvious way to write a batch and the obvious way
        to get this wrong: every bridge would end up with whichever method the
        statement happened to name, and the provenance of every merge would be
        a copy of one of them.
        """
        key = competition(db_session, f"{PERFORMANCE}:provenance")
        plans = []
        bridges = []
        for index, (method, confidence) in enumerate(
            [("exact_name+dob", 0.99), ("surname+dob+club", 0.84), ("manual_override", 1.0)]
        ):
            performance = make_player(db_session, f"Prov {index}", position=None)
            identity = make_player(db_session, f"Prov {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-prov-{index}")
            bridge(db_session, identity, IDENTITY, f"t-prov-{index}")
            stats(db_session, performance, key, str(2100 + index))
            plans.append(
                PlannedMerge(
                    performance_player_id=performance.player_id,
                    identity_player_id=identity.player_id,
                    bridge_id=performance_bridge.id,
                    method=method,
                    confidence=confidence,
                )
            )
            bridges.append((performance_bridge, method, confidence))

        assert len(merge_all(db_session, plans).merged) == 3

        for bridge_row, method, confidence in bridges:
            db_session.refresh(bridge_row)
            assert bridge_row.match_method == method
            assert bridge_row.match_confidence == pytest.approx(confidence)


class TestTheParameterCeiling:
    def test_a_batch_wider_than_one_statement_is_split_and_still_whole(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PostgreSQL binds at most 65,535 parameters per statement.

        The widest statement here binds four per merge, so the real ceiling is
        ~16,000 against the ~5,100 a refresh plans - near enough that one good
        season of new competitions would hit it, as a protocol error naming
        none of this. `MERGE_CHUNK` is lowered rather than building a batch of
        sixteen thousand players: the behaviour under test is the splitting, not
        the size.
        """
        monkeypatch.setattr("pipelines.identity_resolution.resolve.MERGE_CHUNK", 3)

        key = competition(db_session, f"{PERFORMANCE}:chunked")
        plans = []
        pairs = []
        for index in range(10):  # four chunks, the last one short
            performance = make_player(db_session, f"Chunk {index}", position=None)
            identity = make_player(db_session, f"Chunk {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-chunk-{index}")
            bridge(db_session, identity, IDENTITY, f"t-chunk-{index}")
            stats(db_session, performance, key, str(2200 + index))
            plans.append(plan(performance, identity, performance_bridge))
            pairs.append((performance, identity, performance_bridge))

        outcome = merge_all(db_session, plans)

        assert len(outcome.merged) == 10
        for performance, identity, performance_bridge in pairs:
            assert db_session.get(DimPlayer, performance.player_id) is None
            db_session.refresh(performance_bridge)
            assert performance_bridge.player_id == identity.player_id
            moved = db_session.execute(
                select(func.count())
                .select_from(FactPlayerSeasonStats)
                .where(FactPlayerSeasonStats.player_id == identity.player_id)
            ).scalar_one()
            assert moved == 1

    def test_the_guard_counts_across_chunks(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One bad bridge in a later chunk must still stop everything.

        Summing rowcounts and comparing once is the point: a per-chunk check
        would pass the first chunk, and a per-chunk delete would already have
        destroyed its duplicates by the time the bad chunk was reached.
        """
        monkeypatch.setattr("pipelines.identity_resolution.resolve.MERGE_CHUNK", 2)

        key = competition(db_session, f"{PERFORMANCE}:chunkguard")
        plans = []
        survivors = []
        for index in range(4):
            performance = make_player(db_session, f"Guard {index}", position=None)
            identity = make_player(db_session, f"Guard {index}", position=PositionGroup.CM)
            performance_bridge = bridge(db_session, performance, PERFORMANCE, f"p-guard-{index}")
            bridge(db_session, identity, IDENTITY, f"t-guard-{index}")
            stats(db_session, performance, key, str(2300 + index))
            plans.append(plan(performance, identity, performance_bridge))
            survivors.append(performance)

        # Break a bridge in the final chunk, after two full chunks have moved.
        plans[-1] = PlannedMerge(
            performance_player_id=plans[-1].performance_player_id,
            identity_player_id=plans[-1].identity_player_id,
            bridge_id=-1,
            method="exact_name+dob",
            confidence=0.9,
        )

        with pytest.raises(RuntimeError, match="not repointed"):
            merge_all(db_session, plans)

        # Nothing was deleted: the guard runs before any delete, so the earlier
        # chunks' duplicates are all still there for the rollback to restore.
        for performance in survivors:
            assert db_session.get(DimPlayer, performance.player_id) is not None

        db_session.rollback()


class TestRefusingLoudly:
    def test_one_unmovable_bridge_stops_the_whole_batch(self, db_session: Session) -> None:
        """Nothing is committed, so refusing the batch loses nothing.

        The loop checked one row at a time and raised on the first bad one,
        having already written the merges before it. The batch checks the total
        inside the same open transaction, which is strictly stronger: the caller
        rolls back and no duplicate is deleted without its mapping moved.
        """
        key = competition(db_session, f"{PERFORMANCE}:unmovable")
        good_performance = make_player(db_session, "Good One", position=None)
        good_identity = make_player(db_session, "Good One", position=PositionGroup.CM)
        good_bridge = bridge(db_session, good_performance, PERFORMANCE, "p-good")
        bridge(db_session, good_identity, IDENTITY, "t-good")
        stats(db_session, good_performance, key, "2024")

        bad_performance = make_player(db_session, "Bad One", position=None)
        bad_identity = make_player(db_session, "Bad One", position=PositionGroup.CM)
        bridge(db_session, bad_identity, IDENTITY, "t-bad")
        stats(db_session, bad_performance, key, "2025")

        with pytest.raises(RuntimeError, match="not repointed"):
            merge_all(
                db_session,
                [
                    plan(good_performance, good_identity, good_bridge),
                    PlannedMerge(
                        performance_player_id=bad_performance.player_id,
                        identity_player_id=bad_identity.player_id,
                        bridge_id=-1,  # no such bridge
                        method="exact_name+dob",
                        confidence=0.9,
                    ),
                ],
            )

        # The message says how many of how many, because "a bridge was not
        # repointed" in a batch of five thousand is not a diagnosis.
        db_session.rollback()

    def test_an_empty_batch_touches_nothing(self, db_session: Session) -> None:
        before = db_session.execute(select(func.count()).select_from(DimPlayer)).scalar_one()
        outcome = merge_all(db_session, [])
        assert outcome.merged == []
        assert outcome.refused == []
        after = db_session.execute(select(func.count()).select_from(DimPlayer)).scalar_one()
        assert before == after
