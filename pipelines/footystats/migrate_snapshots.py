"""Move the flat snapshot directory into a refresh generation. One time.

    python -m pipelines.footystats.migrate_snapshots            # report
    python -m pipelines.footystats.migrate_snapshots --apply

WHY
===

Snapshots used to live in one directory with no notion of which refresh they
belonged to, which is the defect `generations.py` exists to fix. Those files
are still the basis of the currently published dataset, so they are worth
keeping - but keeping them means the loader has to understand two layouts, and
two layouts is how one of them quietly stops being tested.

So this converts the flat directory into a generation and the flat layout
becomes history rather than an alternative.

WHAT IT PRODUCES
================

A generation whose id is derived from the newest snapshot's timestamp, so it
sorts before anything a future refresh creates and reads as what it is: the
state of the world when it was fetched.

Its roster files are reconstructed from each snapshot's header - the roster the
fetch recorded when it created the file - and its progress files carry over
unchanged. That is enough for the generation to know its own universe and
report honestly whether it is complete.

WHAT IT REFUSES TO DO
=====================

Run twice, run while a generation is open, or delete anything before the copy
has been verified. Every file is checksummed after the move; a mismatch aborts
and leaves both copies in place.

STATUS
======

The migrated generation is marked PUBLISHED when it is complete, because it is
the dataset currently being served. An incomplete one is marked FAILED with a
reason rather than left IN_PROGRESS: resuming a fetch that was interrupted
under the old layout would mix two universes, and the honest move is to let the
next scheduled refresh start cleanly.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipelines.footystats.generations import (
    Generation,
    GenerationMetadata,
    GenerationStatus,
    GenerationStore,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FLAT_DIR = REPO_ROOT / "data" / "raw" / "footystats" / "snapshots"
MARKER = "MIGRATED_TO_GENERATION.txt"


@dataclass
class Season:
    """One competition's files in the flat layout."""

    season_id: str
    snapshot: Path
    progress: Path | None
    #: `None` when the snapshot carries no readable roster header, which means
    #: the fetch never got that far. An empty list is different: the provider
    #: answered and said the competition has no players.
    roster: list[str] | None
    fetched: list[str]

    @property
    def complete(self) -> bool:
        """Every player the provider listed is on disk.

        An empty roster counts as complete. Two of the configured competitions
        return `"data": []` - the fetch succeeded and there was nothing to
        fetch - and treating that as unfinished would have marked a fully
        fetched universe as failed on the strength of two competitions that
        never had anything in them.

        An unreadable header is not complete, because nothing is known about
        what should be there.
        """
        if self.roster is None:
            return False
        return set(self.roster) <= set(self.fetched)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_roster(snapshot: Path) -> list[str] | None:
    """The roster the fetch recorded in the snapshot's first line.

    `None` when there is no readable header - the fetch never recorded what it
    was going to fetch. Distinct from an empty list, which is the provider
    saying the competition has no players.
    """
    try:
        with gzip.open(snapshot, "rt", encoding="utf-8") as handle:
            first = handle.readline()
    except (OSError, EOFError):
        return None
    try:
        parsed = json.loads(first)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or parsed.get("kind") != "roster":
        return None
    rows = parsed.get("data") or []
    return [str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id") is not None]


def _read_progress(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(parsed, dict):
        return [str(p) for p in (parsed.get("done") or [])]
    if isinstance(parsed, list):
        return [str(p) for p in parsed]
    return []


def survey(directory: Path = FLAT_DIR) -> list[Season]:
    """What the flat directory holds, read rather than assumed."""
    if not directory.exists():
        return []
    seasons: list[Season] = []
    for snapshot in sorted(directory.glob("season-*.jsonl.gz")):
        season_id = snapshot.name[len("season-") : -len(".jsonl.gz")]
        progress = directory / f"season-{season_id}.progress.json"
        seasons.append(
            Season(
                season_id=season_id,
                snapshot=snapshot,
                progress=progress if progress.exists() else None,
                roster=_read_roster(snapshot),
                fetched=_read_progress(progress if progress.exists() else None),
            )
        )
    return seasons


def generation_id_for(seasons: list[Season]) -> str:
    """Derived from the newest snapshot, so the id says when it was fetched."""
    newest = max((s.snapshot.stat().st_mtime for s in seasons), default=None)
    when = datetime.fromtimestamp(newest, UTC) if newest else datetime.now(UTC)
    return when.strftime("%Y%m%dT%H%M%SZ")


def migrate(
    *,
    apply: bool,
    flat_dir: Path = FLAT_DIR,
    store: GenerationStore | None = None,
) -> tuple[int, str]:
    """Convert the flat directory. Returns an exit code and a summary."""
    store = store or GenerationStore()

    # The marker first. After a migration the directory is empty of snapshots,
    # so the emptiness check below would otherwise answer "nothing to migrate"
    # - true, and less useful than saying where everything went.
    if (flat_dir / MARKER).exists():
        return 0, "Already migrated; the marker file says where the files went."

    seasons = survey(flat_dir)
    if not seasons:
        return 0, f"No flat snapshots at {flat_dir}. Nothing to migrate."

    open_generation = store.in_progress()
    if open_generation is not None:
        return 1, (
            f"Generation {open_generation.generation_id} is IN_PROGRESS. Migrating now "
            f"would leave two universes half-assembled; finish or fail it first."
        )

    generation_id = generation_id_for(seasons)
    directory = store.root / generation_id
    if directory.exists():
        return 1, f"{directory} already exists; refusing to write into it."

    complete = [s for s in seasons if s.complete]
    total_expected = sum(len(s.roster or []) for s in seasons)
    total_fetched = sum(len(s.fetched) for s in seasons)
    all_complete = len(complete) == len(seasons) and bool(seasons)

    summary = (
        f"{len(seasons)} competition(s), {total_fetched:,} of {total_expected:,} players "
        f"fetched, {len(complete)} complete.\n"
        f"Would become generation {generation_id}, status "
        f"{'PUBLISHED' if all_complete else 'FAILED (incomplete)'}."
    )
    if not apply:
        return 0, summary + "\n\nRe-run with --apply."

    directory.mkdir(parents=True)
    stamp = datetime.now(UTC).isoformat()
    generation = Generation(
        directory=directory,
        metadata=GenerationMetadata(
            generation_id=generation_id, created_at=stamp, last_updated_at=stamp
        ),
    )
    generation.save()

    # -- Copy, verify, then remove. Never the other way round ----------------
    moved: list[tuple[Path, Path]] = []
    for season in seasons:
        target = generation.snapshot_path(season.season_id)
        shutil.copy2(season.snapshot, target)
        if _sha256(target) != _sha256(season.snapshot):
            shutil.rmtree(directory)
            return 1, (
                f"Checksum mismatch copying {season.snapshot.name}. Nothing was removed; "
                f"the partial generation has been deleted."
            )
        moved.append((season.snapshot, target))

        if season.progress is not None:
            shutil.copy2(season.progress, generation.progress_path(season.season_id))
        generation.record_roster(season.season_id, season.roster or [])
        if season.complete:
            generation.mark_competition_complete(season.season_id)

    generation.refresh_counts(completed=total_fetched, failed=[])
    generation.evaluate_completeness()

    if all_complete:
        # It is the dataset currently being served.
        generation.set_status(GenerationStatus.PUBLISHED)
    else:
        # Not IN_PROGRESS. Resuming a fetch interrupted under the old layout
        # would mix the leftovers of one universe into another; the honest
        # move is to let the next scheduled refresh start cleanly.
        generation.set_status(
            GenerationStatus.FAILED,
            reason="migrated from the flat layout while incomplete; not resumable",
        )

    # -- Retire the flat directory -------------------------------------------
    for source, _ in moved:
        source.unlink()
    for leftover in ("manifest.json", "failures.json"):
        path = flat_dir / leftover
        if path.exists():
            shutil.copy2(path, directory / leftover)
            path.unlink()
    for progress in flat_dir.glob("season-*.progress.json"):
        progress.unlink()

    (flat_dir / MARKER).write_text(
        "\n".join(
            [
                "These snapshots were migrated into a refresh generation.",
                "",
                f"    generation : {generation_id}",
                f"    status     : {generation.metadata.status}",
                f"    migrated   : {stamp}",
                f"    location   : data/raw/footystats/generations/{generation_id}/",
                "",
                "The flat layout is no longer read by the loader. It had no notion of",
                "which refresh a snapshot belonged to, which meant a completed refresh",
                "was resumed forever and the data never changed again. See",
                "pipelines/footystats/generations.py.",
                "",
                "This file is left behind so the directory explains itself rather than",
                "looking like something that failed.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Tell the site where the published dataset came from. Without this the
    # /data-quality panel would report no generation at all until the next
    # refresh, which is true of the database and false of the world.
    from pipelines.footystats import publish_status

    publish_status.record(generation)

    return 0, (
        f"Migrated {len(seasons)} competition(s) into generation {generation_id} "
        f"({generation.metadata.status}).\n"
        f"The flat directory now holds only {MARKER}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the migration.")
    args = parser.parse_args(argv)

    code, summary = migrate(apply=args.apply)
    print(summary, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
