"""One generation is one attempt at a complete universe.

THE BUG
=======

A full FootyStats refresh is about fourteen hours of rate-limited fetching, so
it checkpoints and `--resume` continues it. The completed-player set lived in
one flat directory with no notion of which refresh it belonged to.

That is right for finishing an unfinished refresh and wrong for starting a new
one. Once a universe was complete, every later run read the same progress file,
found every player already done, skipped all of them, and reported success. The
first refresh worked and the data then never changed again - no failure, no
warning, the same season served for as long as the pipeline kept "succeeding".

These tests are the sequence from the brief, in order, plus the guarantees the
model has to keep while doing it.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest
from pipelines.footystats.generations import (
    Generation,
    GenerationError,
    GenerationStatus,
    GenerationStore,
)


@pytest.fixture
def store(tmp_path: pathlib.Path) -> GenerationStore:
    return GenerationStore(root=tmp_path / "generations")


def at(hour: int) -> dt.datetime:
    """A distinct, ordered timestamp, so generation ids differ."""
    return dt.datetime(2026, 9, 7, hour, 0, 0, tzinfo=dt.UTC)


def fetch_all(generation: Generation, season: str, players: list[str]) -> None:
    """Simulate a run that fetches every player in a competition."""
    generation.record_roster(season, players)
    generation.snapshot_path(season).write_bytes(b"")
    generation.progress_path(season).write_text(json.dumps(players), encoding="utf-8")
    generation.mark_competition_complete(season)
    generation.refresh_counts(completed=len(players), failed=[])
    generation.evaluate_completeness()
    generation.save()


# ---------------------------------------------------------------------------
# The sequence the brief asks for
# ---------------------------------------------------------------------------


class TestTheRefreshLifecycle:
    def test_the_whole_sequence(self, store: GenerationStore) -> None:
        # 1. First generation fetches A, B, C.
        first = store.resolve(resume=True, now=at(4))
        fetch_all(first, "16504", ["A", "B", "C"])

        assert first.status is GenerationStatus.IN_PROGRESS
        assert first.metadata.completed_players == 3

        # 2. It completes.
        assert first.evaluate_completeness() is True
        first.set_status(GenerationStatus.COMPLETE)

        # 3. It is published.
        first.set_status(GenerationStatus.VALIDATED)
        first.set_status(GenerationStatus.PUBLISHED)
        assert first.metadata.published_at is not None

        # 4. The next refresh creates a NEW generation.
        second = store.resolve(resume=True, now=at(8))
        assert second.generation_id != first.generation_id
        assert second.status is GenerationStatus.IN_PROGRESS

        # 5. A, B and C are unfetched here - the defect in one assertion.
        assert second.expected_players("16504") == []
        progress = second.progress_path("16504")
        assert not progress.exists(), (
            "the new generation inherited the previous one's completed players, "
            "so a refresh would skip every player it is meant to re-fetch"
        )

        # 6. A new player is discovered.
        second.record_roster("16504", ["A", "B", "C", "D"])
        assert second.expected_players("16504") == ["A", "B", "C", "D"]
        assert second.metadata.total_expected_players == 4

        # 7. The published generation is untouched throughout.
        republished = store._read(first.directory)
        assert republished is not None
        assert republished.status is GenerationStatus.PUBLISHED
        assert json.loads(first.progress_path("16504").read_text()) == ["A", "B", "C"]


class TestResumingAnIncompleteGeneration:
    def test_it_is_resumed_rather_than_replaced(self, store: GenerationStore) -> None:
        first = store.resolve(resume=True, now=at(4))
        first.record_roster("16504", ["A", "B", "C"])
        first.progress_path("16504").write_text(json.dumps(["A"]), encoding="utf-8")
        first.refresh_counts(completed=1, failed=[])
        first.save()

        again = store.resolve(resume=True, now=at(5))
        assert again.generation_id == first.generation_id
        assert json.loads(again.progress_path("16504").read_text()) == ["A"]

    def test_an_incomplete_generation_cannot_be_published(self, store: GenerationStore) -> None:
        """The rule everything else is defence around."""
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B", "C"])
        generation.refresh_counts(completed=1, failed=[])
        generation.evaluate_completeness()

        assert generation.metadata.complete is False
        with pytest.raises(GenerationError, match="not complete"):
            generation.set_status(GenerationStatus.PUBLISHED)

    def test_a_competition_never_visited_holds_it_incomplete(self, store: GenerationStore) -> None:
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A"])
        generation.record_roster("16544", ["B"])
        generation.mark_competition_complete("16504")

        assert generation.evaluate_completeness() is False

    def test_a_generation_with_no_roster_is_not_complete(self, store: GenerationStore) -> None:
        """Empty is not finished. It is a generation that has done nothing."""
        generation = store.resolve(resume=True, now=at(4))
        assert generation.evaluate_completeness() is False


class TestOnlyOneGenerationIsOpen:
    def test_a_second_cannot_start_while_one_is_in_progress(self, store: GenerationStore) -> None:
        """Two concurrent fetches would interleave into the same universe."""
        store.resolve(resume=True, now=at(4))
        with pytest.raises(GenerationError, match="IN_PROGRESS"):
            store.create(now=at(8))

    def test_resolving_without_resume_refuses_to_abandon_an_open_one(
        self, store: GenerationStore
    ) -> None:
        """Fourteen hours of fetching is not discarded by a forgotten flag."""
        store.resolve(resume=True, now=at(4))
        with pytest.raises(GenerationError, match="--resume"):
            store.resolve(resume=False, now=at(8))

    def test_two_open_generations_are_reported_rather_than_guessed_between(
        self, store: GenerationStore
    ) -> None:
        first = store.resolve(resume=True, now=at(4))
        first.set_status(GenerationStatus.COMPLETE)
        second = store.create(now=at(8))
        # Force the state that should be impossible.
        first.metadata.status = GenerationStatus.IN_PROGRESS.value
        first.save()

        with pytest.raises(GenerationError, match="more than one"):
            store.in_progress()
        assert second.status is GenerationStatus.IN_PROGRESS

    def test_a_failed_generation_does_not_block_the_next(self, store: GenerationStore) -> None:
        first = store.resolve(resume=True, now=at(4))
        first.set_status(GenerationStatus.FAILED, reason="corrupt checkpoint")

        second = store.resolve(resume=True, now=at(8))
        assert second.generation_id != first.generation_id
        assert first.metadata.failure_reason == "corrupt checkpoint"


class TestRostersBelongToTheirGeneration:
    def test_a_roster_can_grow_within_a_generation(self, store: GenerationStore) -> None:
        """A January signing must not be invisible to a September generation.

        The roster used to be the snapshot's first line, written once when the
        file was created, so a re-fetch could not add to it.
        """
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B"])
        generation.record_roster("16504", ["A", "B", "C"])

        assert generation.expected_players("16504") == ["A", "B", "C"]
        assert generation.metadata.total_expected_players == 3

    def test_a_player_who_left_is_still_expected(self, store: GenerationStore) -> None:
        """Their season happened. Dropping them shrinks what is being measured."""
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B"])
        generation.record_roster("16504", ["B"])

        assert generation.expected_players("16504") == ["A", "B"]

    def test_the_expected_total_spans_competitions(self, store: GenerationStore) -> None:
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B"])
        generation.record_roster("16544", ["C"])
        assert generation.metadata.total_expected_players == 3

    def test_a_new_generation_captures_its_own_roster(self, store: GenerationStore) -> None:
        first = store.resolve(resume=True, now=at(4))
        fetch_all(first, "16504", ["A", "B"])
        first.set_status(GenerationStatus.COMPLETE)
        first.set_status(GenerationStatus.PUBLISHED)

        second = store.resolve(resume=True, now=at(8))
        assert second.metadata.total_expected_players == 0, (
            "the new generation started with the old one's universe"
        )


class TestTransientFailuresDoNotResetAGeneration:
    def test_failed_players_are_recorded_and_the_generation_survives(
        self, store: GenerationStore
    ) -> None:
        """One player's endpoint failing costs one player, not fourteen hours."""
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B", "C"])
        generation.refresh_counts(completed=2, failed=["C"])
        generation.save()

        reread = store.in_progress()
        assert reread is not None
        assert reread.generation_id == generation.generation_id
        assert reread.status is GenerationStatus.IN_PROGRESS
        assert reread.metadata.failed_players == ["C"]
        assert reread.metadata.completed_players == 2

    def test_and_the_generation_is_not_complete_while_they_are_outstanding(
        self, store: GenerationStore
    ) -> None:
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B", "C"])
        generation.refresh_counts(completed=2, failed=["C"])
        assert generation.evaluate_completeness() is False

    def test_a_retry_that_succeeds_completes_it(self, store: GenerationStore) -> None:
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B", "C"])
        generation.refresh_counts(completed=2, failed=["C"])
        assert generation.evaluate_completeness() is False

        fetch_all(generation, "16504", ["A", "B", "C"])
        assert generation.metadata.complete is True
        assert generation.metadata.failed_players == []


class TestCorruptState:
    def test_unreadable_metadata_stops_the_run(self, store: GenerationStore) -> None:
        """Rather than being treated as absent, which would start a new
        generation beside a broken one and hide the breakage."""
        generation = store.resolve(resume=True, now=at(4))
        generation.metadata_path.write_text("{not json", encoding="utf-8")

        with pytest.raises(GenerationError, match="unreadable"):
            store.all()

    def test_a_directory_without_metadata_is_ignored(self, store: GenerationStore) -> None:
        """A half-created directory is not a generation."""
        (store.root / "20260101T000000Z").mkdir(parents=True)
        assert store.all() == []

    def test_a_directory_that_is_not_a_generation_id_is_ignored(
        self, store: GenerationStore
    ) -> None:
        store.root.mkdir(parents=True, exist_ok=True)
        (store.root / "scratch").mkdir()
        (store.root / "scratch" / "metadata.json").write_text("{}", encoding="utf-8")
        assert store.all() == []


class TestProgressReporting:
    def test_completion_percentage(self, store: GenerationStore) -> None:
        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", [str(i) for i in range(100)])
        generation.refresh_counts(completed=68, failed=[])
        assert generation.metadata.completion_pct == pytest.approx(68.0)
        assert generation.metadata.pending_players == 32

    def test_an_empty_generation_reports_nought_rather_than_dividing(
        self, store: GenerationStore
    ) -> None:
        generation = store.resolve(resume=True, now=at(4))
        assert generation.metadata.completion_pct == 0.0

    def test_the_latest_published_generation_is_findable(self, store: GenerationStore) -> None:
        first = store.resolve(resume=True, now=at(4))
        fetch_all(first, "16504", ["A"])
        first.set_status(GenerationStatus.COMPLETE)
        first.set_status(GenerationStatus.PUBLISHED)
        store.resolve(resume=True, now=at(8))

        published = store.latest_published()
        assert published is not None
        assert published.generation_id == first.generation_id


class TestStatusSemantics:
    @pytest.mark.parametrize(
        ("status", "publishable"),
        [
            (GenerationStatus.IN_PROGRESS, False),
            (GenerationStatus.FAILED, False),
            (GenerationStatus.COMPLETE, True),
            (GenerationStatus.VALIDATED, True),
            (GenerationStatus.PUBLISHED, True),
        ],
    )
    def test_only_finished_generations_may_be_loaded_from(
        self, status: GenerationStatus, publishable: bool
    ) -> None:
        assert status.is_publishable is publishable

    def test_only_an_open_generation_is_fetched(self) -> None:
        assert GenerationStatus.IN_PROGRESS.is_fetchable is True
        for other in GenerationStatus:
            if other is not GenerationStatus.IN_PROGRESS:
                assert other.is_fetchable is False


# ---------------------------------------------------------------------------
# The same guarantee, through `ingest_competition` rather than the store alone
# ---------------------------------------------------------------------------


class RosterProvider:
    """A roster that can change between generations, and always succeeds."""

    def __init__(self, players: list[str]) -> None:
        self.players = players
        self.fetched: list[str] = []

    def _roster(self, season_id: str) -> list[dict[str, object]]:
        return [{"id": p} for p in self.players]

    def _get(self, path: str, **params: object) -> object:
        player_id = str(params.get("player_id"))
        self.fetched.append(player_id)
        return {"data": {"id": player_id}}


class TestTheIngestHonoursGenerations:
    """The store can be right while the fetch still reads the old progress.

    These drive `ingest_competition` itself, which is where the skipping
    actually happened.
    """

    def test_a_new_generation_refetches_every_player(self, store: GenerationStore) -> None:
        from pipelines.footystats.ingest import ingest_competition

        first = store.resolve(resume=True, now=at(4))
        provider = RosterProvider(["A", "B", "C"])
        result = ingest_competition(provider, "16504", "Test", resume=True, generation=first)
        assert sorted(provider.fetched) == ["A", "B", "C"]
        assert result.complete is True

        first.mark_competition_complete("16504")
        first.evaluate_completeness()
        first.set_status(GenerationStatus.COMPLETE)
        first.set_status(GenerationStatus.PUBLISHED)

        # A new generation, the same three players, and a fourth.
        second = store.resolve(resume=True, now=at(8))
        again = RosterProvider(["A", "B", "C", "D"])
        ingest_competition(again, "16504", "Test", resume=True, generation=second)

        assert sorted(again.fetched) == ["A", "B", "C", "D"], (
            "the new generation skipped players the previous one had fetched"
        )

    def test_resuming_the_same_generation_skips_what_it_has(self, store: GenerationStore) -> None:
        """The behaviour that must survive: within one generation, resume works."""
        from pipelines.footystats.ingest import ingest_competition

        generation = store.resolve(resume=True, now=at(4))
        first = RosterProvider(["A", "B", "C"])
        ingest_competition(first, "16504", "Test", resume=True, generation=generation)

        second = RosterProvider(["A", "B", "C"])
        result = ingest_competition(second, "16504", "Test", resume=True, generation=generation)
        assert second.fetched == []
        assert result.skipped == 3

    def test_a_mid_generation_roster_addition_is_fetched(self, store: GenerationStore) -> None:
        """A January signing, discovered while the generation is still open."""
        from pipelines.footystats.ingest import ingest_competition

        generation = store.resolve(resume=True, now=at(4))
        ingest_competition(
            RosterProvider(["A", "B"]), "16504", "Test", resume=True, generation=generation
        )

        grown = RosterProvider(["A", "B", "C"])
        result = ingest_competition(grown, "16504", "Test", resume=True, generation=generation)
        assert grown.fetched == ["C"]
        assert result.complete is True
        assert generation.expected_players("16504") == ["A", "B", "C"]

    def test_snapshots_are_written_inside_the_generation(self, store: GenerationStore) -> None:
        from pipelines.footystats.ingest import ingest_competition

        generation = store.resolve(resume=True, now=at(4))
        ingest_competition(
            RosterProvider(["A"]), "16504", "Test", resume=True, generation=generation
        )
        assert generation.snapshot_path("16504").exists()
        assert generation.progress_path("16504").exists()
        assert generation.snapshot_path("16504").parent == generation.directory

    def test_a_published_generation_is_not_written_to_by_a_later_run(
        self, store: GenerationStore
    ) -> None:
        """The published dataset stays usable while the next one is fetched."""
        from pipelines.footystats.ingest import ingest_competition

        first = store.resolve(resume=True, now=at(4))
        ingest_competition(RosterProvider(["A"]), "16504", "Test", resume=True, generation=first)
        first.mark_competition_complete("16504")
        first.evaluate_completeness()
        first.set_status(GenerationStatus.COMPLETE)
        first.set_status(GenerationStatus.PUBLISHED)
        before = first.snapshot_path("16504").read_bytes()

        second = store.resolve(resume=True, now=at(8))
        ingest_competition(
            RosterProvider(["A", "B"]), "16504", "Test", resume=True, generation=second
        )

        assert first.snapshot_path("16504").read_bytes() == before
        assert store.latest_published().generation_id == first.generation_id


# ---------------------------------------------------------------------------
# The projection the site reads
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTheDatabaseProjection:
    """The generation lives on disk; the site cannot see that disk.

    The fetch runs in CI with its snapshots in the job cache, and the API runs
    elsewhere. Reading the generation directory from the serving layer would
    show full progress in development and nothing at all in production, which
    is worse than showing nothing in both.
    """

    def test_it_records_and_updates_one_row_per_generation(
        self, store: GenerationStore, db_session
    ) -> None:  # type: ignore[no-untyped-def]
        from pipelines.footystats.publish_status import record
        from sqlalchemy import text

        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", ["A", "B", "C", "D"])
        generation.refresh_counts(completed=2, failed=["C"])
        generation.save()

        assert record(generation) is True

        rows = db_session.execute(
            text(
                "SELECT status, total_expected_players, completed_players, failed_players, "
                "complete FROM fact_refresh_generation WHERE generation_id = :g"
            ),
            {"g": generation.generation_id},
        ).all()
        assert rows == [("IN_PROGRESS", 4, 2, 1, False)]

        # Progress moves; the row is updated rather than duplicated.
        generation.refresh_counts(completed=4, failed=[])
        generation.mark_competition_complete("16504")
        generation.evaluate_completeness()
        generation.set_status(GenerationStatus.COMPLETE)
        assert record(generation) is True

        rows = db_session.execute(
            text(
                "SELECT status, completed_players, failed_players, complete "
                "FROM fact_refresh_generation WHERE generation_id = :g"
            ),
            {"g": generation.generation_id},
        ).all()
        assert rows == [("COMPLETE", 4, 0, True)]

    def test_it_records_a_count_rather_than_the_failed_player_ids(
        self, store: GenerationStore, db_session
    ) -> None:  # type: ignore[no-untyped-def]
        """A public page has no reason to name which players a provider
        failed to return."""
        from sqlalchemy import inspect

        from app.models import FactRefreshGeneration

        columns = {c.key for c in inspect(FactRefreshGeneration).columns}
        assert "failed_players" in columns
        assert not any("id" in c and "failed" in c for c in columns if c != "generation_id")

    def test_the_service_reads_it_back(self, store: GenerationStore, db_session) -> None:  # type: ignore[no-untyped-def]
        from pipelines.footystats.publish_status import record

        from app.services import quality_service as svc

        generation = store.resolve(resume=True, now=at(4))
        generation.record_roster("16504", [str(i) for i in range(100)])
        generation.refresh_counts(completed=68, failed=[])
        generation.save()
        record(generation)

        status = svc.refresh_status(db_session)
        assert status is not None
        assert status.state == "In progress"
        assert status.current is not None
        assert status.current.completion_pct == pytest.approx(68.0)
        assert status.published is None

    def test_nothing_recorded_means_no_panel(self, db_session) -> None:  # type: ignore[no-untyped-def]
        """Rather than an empty progress bar implying a stalled refresh."""
        from sqlalchemy import text

        from app.services import quality_service as svc

        db_session.execute(text("DELETE FROM fact_refresh_generation"))
        db_session.flush()
        assert svc.refresh_status(db_session) is None
