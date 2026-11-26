"""The published number of fetched players must not fall during a run.

It was the sum over the competitions the current run had walked past, so every
run restarted it near nought: 11,751 in the morning of 26 November, 11,088 that
evening, with nothing lost.
"""

from __future__ import annotations

import inspect
import json
import pathlib

from pipelines.footystats import ingest
from pipelines.footystats.generations import Generation, GenerationStore


def fetched(generation: Generation, season: str, roster: list[str], done: list[str]) -> None:
    generation.record_roster(season, roster)
    generation.snapshot_path(season).write_bytes(b"")
    generation.progress_path(season).write_text(json.dumps({"done": done}), encoding="utf-8")


def new_generation(tmp_path: pathlib.Path) -> Generation:
    return GenerationStore(root=tmp_path / "generations").create()


def test_every_competition_on_disk_counts_not_only_those_revisited(
    tmp_path: pathlib.Path,
) -> None:
    generation = new_generation(tmp_path)
    fetched(generation, "1", ["A", "B"], ["A", "B"])
    fetched(generation, "2", ["C", "D", "E"], ["C"])

    # What a run that has only re-walked the first competition now publishes.
    assert ingest.fetched_on_disk(generation) == 3


def test_a_player_who_left_the_roster_is_not_counted(tmp_path: pathlib.Path) -> None:
    generation = new_generation(tmp_path)
    fetched(generation, "1", ["A"], ["A", "gone"])

    assert ingest.fetched_on_disk(generation) == 1


def test_progress_without_a_snapshot_is_not_trusted(tmp_path: pathlib.Path) -> None:
    generation = new_generation(tmp_path)
    fetched(generation, "1", ["A"], ["A"])
    generation.snapshot_path("1").unlink()

    assert ingest.fetched_on_disk(generation) == 0


def test_the_run_publishes_the_count_from_disk() -> None:
    source = inspect.getsource(ingest.main)
    assert source.count("completed=fetched_on_disk(generation)") == 2
    assert "completed=sum(" not in source
