"""Converting the flat snapshot directory into a generation. Once.

The flat layout had no notion of which refresh a snapshot belonged to, which is
the defect generations exist to fix. Its files are still the basis of the
published dataset, so they are worth keeping - but keeping them as a *supported*
layout means the loader understands two, and two layouts is how one of them
quietly stops being tested.

So the migration converts, verifies, and retires. These cover the conversion
and, more importantly, the refusals: the ways it could destroy the only copy of
fourteen hours of fetching.
"""

from __future__ import annotations

import gzip
import json
import pathlib

import pytest
from pipelines.footystats.generations import GenerationStatus, GenerationStore
from pipelines.footystats.migrate_snapshots import MARKER, migrate, survey


def write_snapshot(
    directory: pathlib.Path,
    season: str,
    roster: list[str] | None,
    fetched: list[str],
) -> None:
    """A flat-layout competition. `roster=None` writes no header at all."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"season-{season}.jsonl.gz"
    with gzip.open(path, "wb") as handle:
        if roster is not None:
            header = {
                "kind": "roster",
                "season_id": season,
                "data": [{"id": p} for p in roster],
            }
            handle.write((json.dumps(header) + "\n").encode("utf-8"))
        for player in fetched:
            handle.write(
                (json.dumps({"kind": "player", "player_id": player, "data": {}}) + "\n").encode(
                    "utf-8"
                )
            )
    (directory / f"season-{season}.progress.json").write_text(
        json.dumps({"done": fetched}), encoding="utf-8"
    )


@pytest.fixture
def flat(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "snapshots"


@pytest.fixture
def store(tmp_path: pathlib.Path) -> GenerationStore:
    return GenerationStore(root=tmp_path / "generations")


@pytest.fixture(autouse=True)
def projection_cleanup():  # type: ignore[no-untyped-def]
    """Remove rows the migration committed.

    `migrate` projects its result so `/data-quality` knows where the published
    dataset came from, and that projection opens its own session and commits.
    It therefore escapes any test transaction, and a leftover generation is
    something the next test - and the running site - will report as real.

    Scoped to what these tests add: deleting everything would remove the row
    describing the dataset actually being served.
    """
    from sqlalchemy import text

    from app.core.database import get_engine

    def ids() -> set[str]:
        try:
            with get_engine().connect() as connection:
                return {
                    row[0]
                    for row in connection.execute(
                        text("SELECT generation_id FROM fact_refresh_generation")
                    )
                }
        except Exception:
            # No database configured is a normal state for these tests.
            return set()

    before = ids()
    yield
    added = ids() - before
    if added:
        with get_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM fact_refresh_generation WHERE generation_id = ANY(:ids)"),
                {"ids": list(added)},
            )


class TestReadingTheFlatLayout:
    def test_a_finished_competition_reads_as_complete(self, flat: pathlib.Path) -> None:
        write_snapshot(flat, "1", ["A", "B"], ["A", "B"])
        assert survey(flat)[0].complete is True

    def test_an_unfinished_one_does_not(self, flat: pathlib.Path) -> None:
        write_snapshot(flat, "1", ["A", "B", "C"], ["A"])
        assert survey(flat)[0].complete is False

    def test_an_empty_roster_is_complete(self, flat: pathlib.Path) -> None:
        """The provider answered and said there is nothing to fetch.

        Two of the configured competitions really do return `"data": []`.
        Treating that as unfinished marked a fully fetched universe as failed
        on the strength of two competitions that never had anything in them.
        """
        write_snapshot(flat, "1", [], [])
        season = survey(flat)[0]
        assert season.roster == []
        assert season.complete is True

    def test_an_unreadable_header_is_not_complete(self, flat: pathlib.Path) -> None:
        """Different from an empty roster: nothing is known about what should
        be there, so nothing can be said about whether it all arrived."""
        write_snapshot(flat, "1", None, ["A"])
        season = survey(flat)[0]
        assert season.roster is None
        assert season.complete is False

    def test_an_absent_directory_reads_as_nothing(self, tmp_path: pathlib.Path) -> None:
        assert survey(tmp_path / "nowhere") == []


class TestTheMigration:
    def test_it_reports_before_it_acts(self, flat: pathlib.Path, store: GenerationStore) -> None:
        write_snapshot(flat, "1", ["A", "B"], ["A", "B"])
        code, summary = migrate(apply=False, flat_dir=flat, store=store)

        assert code == 0
        assert "Re-run with --apply" in summary
        assert store.all() == [], "a dry run created a generation"
        assert (flat / "season-1.jsonl.gz").exists()

    def test_a_complete_universe_becomes_a_published_generation(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        """It is the dataset currently being served."""
        write_snapshot(flat, "1", ["A", "B"], ["A", "B"])
        write_snapshot(flat, "2", ["C"], ["C"])

        code, _ = migrate(apply=True, flat_dir=flat, store=store)
        assert code == 0

        generation = store.latest()
        assert generation is not None
        assert generation.status is GenerationStatus.PUBLISHED
        assert generation.metadata.complete is True
        assert generation.metadata.total_expected_players == 3
        assert sorted(generation.metadata.competitions_expected) == ["1", "2"]

    def test_an_incomplete_one_is_failed_rather_than_left_open(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        """Not IN_PROGRESS.

        Resuming a fetch interrupted under the old layout would carry the
        leftovers of one universe into another. The honest move is to let the
        next scheduled refresh start cleanly.
        """
        write_snapshot(flat, "1", ["A", "B", "C"], ["A"])

        migrate(apply=True, flat_dir=flat, store=store)
        generation = store.latest()

        assert generation is not None
        assert generation.status is GenerationStatus.FAILED
        assert "not resumable" in (generation.metadata.failure_reason or "")
        assert store.in_progress() is None

    def test_the_snapshots_move_and_the_rosters_are_reconstructed(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        write_snapshot(flat, "1", ["A", "B"], ["A", "B"])
        migrate(apply=True, flat_dir=flat, store=store)

        generation = store.latest()
        assert generation is not None
        assert generation.snapshot_path("1").exists()
        assert generation.progress_path("1").exists()
        assert generation.expected_players("1") == ["A", "B"]

    def test_the_flat_directory_is_retired_with_an_explanation(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        write_snapshot(flat, "1", ["A"], ["A"])
        migrate(apply=True, flat_dir=flat, store=store)

        assert list(flat.iterdir()) == [flat / MARKER]
        marker = (flat / MARKER).read_text(encoding="utf-8")
        assert store.latest().generation_id in marker
        assert "no longer read by the loader" in marker


class TestWhatItRefusesToDo:
    def test_it_will_not_run_twice(self, flat: pathlib.Path, store: GenerationStore) -> None:
        write_snapshot(flat, "1", ["A"], ["A"])
        migrate(apply=True, flat_dir=flat, store=store)

        code, summary = migrate(apply=True, flat_dir=flat, store=store)
        assert code == 0
        assert "Already migrated" in summary
        assert len(store.all()) == 1

    def test_it_will_not_run_while_a_generation_is_open(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        """Two half-assembled universes is the state nothing can recover from."""
        write_snapshot(flat, "1", ["A"], ["A"])
        store.create()

        code, summary = migrate(apply=True, flat_dir=flat, store=store)
        assert code == 1
        assert "IN_PROGRESS" in summary
        assert (flat / "season-1.jsonl.gz").exists(), "it deleted files anyway"

    def test_it_copies_and_verifies_before_deleting_anything(
        self, flat: pathlib.Path, store: GenerationStore
    ) -> None:
        """The property that matters most: the flat files are the only copy of
        fourteen hours of rate-limited fetching."""
        import inspect

        from pipelines.footystats import migrate_snapshots

        source = inspect.getsource(migrate_snapshots.migrate)
        copy_at = source.index("shutil.copy2")
        checksum_at = source.index("_sha256(target)")
        delete_at = source.index("source.unlink()")
        assert copy_at < checksum_at < delete_at, (
            "the migration deletes before it has verified the copy"
        )

    def test_nothing_is_lost_when_the_universe_is_empty(
        self, tmp_path: pathlib.Path, store: GenerationStore
    ) -> None:
        code, summary = migrate(apply=True, flat_dir=tmp_path / "nowhere", store=store)
        assert code == 0
        assert "Nothing to migrate" in summary
        assert store.all() == []


class TestTheGenerationFormatIsCanonical:
    def test_the_loader_prefers_a_generation(self) -> None:
        """And warns when it has to fall back, rather than doing it silently."""
        import inspect

        from pipelines.load import load_providers

        source = inspect.getsource(load_providers.build_loader)
        assert "_newest_loadable_generation" in source
        assert "::warning::" in source
        assert "migrate_snapshots" in source
