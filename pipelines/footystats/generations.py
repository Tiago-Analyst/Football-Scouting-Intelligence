"""Refresh generations: one attempt at a complete FootyStats universe.

THE BUG THIS EXISTS TO FIX
==========================

A full refresh is roughly 23,500 requests, about fourteen hours at the
account's rate limit. It cannot finish inside one GitHub job, so the fetch
checkpoints and `--resume` continues where the last run stopped.

That is exactly right for continuing an unfinished refresh, and exactly wrong
for starting a new one. The completed-player set lived in one flat directory
with no notion of *which* refresh it belonged to, so once a universe was
complete, every later run read the same progress file, found every player
already done, skipped all of them, and reported success.

The result: the first refresh worked, and the data then never changed again.
Nothing failed. Nothing warned. The site simply served the same season for as
long as the pipeline kept "succeeding".

THE MODEL
=========

A *generation* is one attempt at a complete universe. It owns its snapshots,
its progress, its roster, and its status:

    data/raw/footystats/generations/
        20260907T040000Z/
            metadata.json
            season-16504.jsonl.gz
            season-16504.progress.json
            ...

`--resume` continues the current generation. A generation that is already
complete is not resumed - a new one is created, and every player is fetched
again, because that is what a refresh is.

STATUSES
========

    IN_PROGRESS   Fetching. May take several runs.
    COMPLETE      Every expected player is on disk. Not yet checked.
    VALIDATED     Quality checks passed against it.
    PUBLISHED     Loaded into production and serving.
    FAILED        Abandoned. Never publishable; kept for inspection.

Only one generation may be IN_PROGRESS at a time. The published dataset is
untouched until a new generation reaches PUBLISHED, so a half-fetched
generation cannot replace a working season - which is the property the whole
design exists to protect.

TRANSITIONS, AND WHO MAKES THEM
===============================

    IN_PROGRESS -> COMPLETE     the fetch, when every expected player is on disk
    IN_PROGRESS -> FAILED       the fetch, for a structural reason only: a
                                refused key, an unreadable roster
    COMPLETE    -> VALIDATED    the workflow, after the staging load, identity
                                resolution, the quality report and the
                                independent analytics validation all passed
    VALIDATED   -> PUBLISHED    the promotion, in the same transaction as the
                                schema swap
    COMPLETE    -> PUBLISHED    also allowed: a promotion run by hand against a
                                generation nobody marked VALIDATED first
    PUBLISHED   -> VALIDATED    a rollback, which really does un-publish
    any         -> FAILED       a person, explicitly, through `--abandon`

What does NOT move a generation:

  - a validation failure. The generation stays COMPLETE; its snapshots are
    intact and the next run re-derives staging from them and tries again.
  - a promotion failure. The generation stays VALIDATED and the next run
    retries publication without refetching.
  - a missing cache. Nothing is created, resumed or failed automatically;
    see `verify_local_state` in `gate.py`.

CHECKPOINT REVISIONS
====================

`checkpoint_revision` counts the runs that saved progress for a generation.
It exists because the GitHub Actions cache is immutable: a key, once written,
is never overwritten, so a generation that grows over nineteen hourly runs
cannot be saved under one key nineteen times. Each run saves under
`footystats-gen-<id>-<revision>` and the restore asks for the newest key with
the `footystats-gen-<id>-` prefix - within that generation, never outside it.

The database holds the revision the last run reached. A restore that comes
back with an older one is reported and refused: resuming from it would refetch
what the newer checkpoint already had, and could not know which players the
failure ledger has since retired.

WHAT A TRANSIENT FAILURE DOES NOT DO
====================================

It does not reset the generation. One player's endpoint failing after retries
costs one player, not fourteen hours: they are recorded, the generation stays
IN_PROGRESS, and the next run retries them. A generation is only abandoned for
structural reasons - a corrupt checkpoint, unreadable metadata, or somebody
saying so explicitly.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GENERATIONS_DIR = REPO_ROOT / "data" / "raw" / "footystats" / "generations"

#: `20260907T040000Z`. Sorts chronologically as a string, which is what the
#: "latest generation" lookup relies on.
GENERATION_ID = "%Y%m%dT%H%M%SZ"
GENERATION_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")

METADATA_FILE = "metadata.json"


class GenerationStatus(StrEnum):
    """Where a generation is in its lifecycle."""

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        """Whether no further fetching will happen against it."""
        return self in {GenerationStatus.PUBLISHED, GenerationStatus.FAILED}

    @property
    def is_fetchable(self) -> bool:
        """Whether `--resume` should continue this one."""
        return self is GenerationStatus.IN_PROGRESS

    @property
    def is_publishable(self) -> bool:
        """Whether production may be loaded from it.

        COMPLETE is enough to *attempt* a load; the load's own verification
        decides whether it publishes. What must never happen is loading from
        IN_PROGRESS, which is a partial universe.
        """
        return self in {
            GenerationStatus.COMPLETE,
            GenerationStatus.VALIDATED,
            GenerationStatus.PUBLISHED,
        }


class GenerationError(RuntimeError):
    """The generation store is in a state nothing should proceed from."""


@dataclass
class GenerationMetadata:
    """What a generation knows about itself.

    Written after every checkpoint, so a run that is killed leaves a file
    describing what it had done rather than what it intended to do.
    """

    generation_id: str
    created_at: str
    last_updated_at: str
    status: str = GenerationStatus.IN_PROGRESS.value

    #: The roster this generation is trying to fetch. Its own, captured when
    #: the generation started and refreshable within it - never inherited from
    #: a previous generation, whose universe is a season out of date.
    total_expected_players: int = 0
    completed_players: int = 0
    failed_players: list[str] = field(default_factory=list)

    #: Competition ids whose roster is entirely on disk.
    competitions_complete: list[str] = field(default_factory=list)
    #: Every competition this generation expects, from its own roster fetch.
    competitions_expected: list[str] = field(default_factory=list)

    #: Whether the whole universe is on disk. Stored rather than derived so a
    #: reader of the file does not have to recompute the rule.
    complete: bool = False

    #: Set when the generation reached PUBLISHED.
    published_at: str | None = None
    #: Why, when the status is FAILED.
    failure_reason: str | None = None

    #: How many runs have saved progress for this generation. Bumped once per
    #: run that checkpoints, so the cache key each run saves under is new and
    #: the database can say which checkpoint is the latest. See the module
    #: docstring, CHECKPOINT REVISIONS.
    checkpoint_revision: int = 0

    @property
    def pending_players(self) -> int:
        return max(self.total_expected_players - self.completed_players, 0)

    @property
    def completion_pct(self) -> float:
        if self.total_expected_players <= 0:
            return 0.0
        return 100.0 * self.completed_players / self.total_expected_players


@dataclass
class Generation:
    """One generation on disk."""

    directory: pathlib.Path
    metadata: GenerationMetadata

    @property
    def generation_id(self) -> str:
        return self.metadata.generation_id

    @property
    def status(self) -> GenerationStatus:
        return GenerationStatus(self.metadata.status)

    # -- Paths inside this generation ---------------------------------------

    def snapshot_path(self, season_id: str) -> pathlib.Path:
        return self.directory / f"season-{season_id}.jsonl.gz"

    def progress_path(self, season_id: str) -> pathlib.Path:
        return self.directory / f"season-{season_id}.progress.json"

    def roster_path(self, season_id: str) -> pathlib.Path:
        """The roster this generation captured for one competition.

        Stored separately from the snapshot rather than only as its first line.
        A roster written once when the file was created cannot grow, and a
        league's roster does change mid-season - so a generation that fetched
        its roster in September would never discover a January signing.

        THE FILE FORMAT, AND WHY IT CHANGED
        -----------------------------------

        It held a list of player ids, which was enough to count what was
        expected and not enough to be the source of truth. The loader needs
        the whole record - the roster carries `club_team_id`, which is where a
        player's club comes from - so it went on reading the snapshot's
        immutable header, and the January signing this file exists to capture
        was expected, fetched, and then dropped on the way in because the
        header had never heard of them.

        So it holds the records now:

            {"players": [{...}, {...}]}

        A bare list is still read, as the ids of a generation written before
        this. Those generations keep working and simply cannot answer the
        richer question, which is the honest outcome for data that was never
        stored.
        """
        return self.directory / f"season-{season_id}.roster.json"

    def clubs_path(self, season_id: str) -> pathlib.Path:
        """The competition's clubs, as the provider listed them.

        Beside the roster rather than inside the snapshot, and for the same
        reason: a competition's clubs are not per-player data and the snapshot
        is append-only, so refetching them on a resume has nowhere to go in it.
        """
        return self.directory / f"season-{season_id}.clubs.json"

    @property
    def metadata_path(self) -> pathlib.Path:
        return self.directory / METADATA_FILE

    # -- Mutation ------------------------------------------------------------

    def save(self) -> None:
        self.metadata.last_updated_at = _now()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(
            json.dumps(asdict(self.metadata), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def set_status(self, status: GenerationStatus, *, reason: str | None = None) -> None:
        """Move to a new status, refusing moves that would lose the guarantee.

        The one that matters: nothing may become PUBLISHED without having been
        COMPLETE. Everything else about the design is defence in depth around
        that single rule.
        """
        if status is GenerationStatus.PUBLISHED and not self.metadata.complete:
            raise GenerationError(
                f"generation {self.generation_id} is not complete and cannot be published; "
                f"{self.metadata.pending_players} player(s) pending"
            )
        self.metadata.status = status.value
        if status is GenerationStatus.PUBLISHED:
            self.metadata.published_at = _now()
        if status is GenerationStatus.FAILED:
            self.metadata.failure_reason = reason
        self.save()

    def checkpoint(self) -> int:
        """Bump the revision and save. Returns the new revision.

        Once per run, after the run has done whatever fetching it will do.
        Not after every competition: a revision is the unit a cache is saved
        under, and a run saves once.
        """
        self.metadata.checkpoint_revision += 1
        self.save()
        return self.metadata.checkpoint_revision

    def abandon(self, reason: str) -> None:
        """Mark FAILED. Explicit, by a person, never by the pipeline guessing.

        The one route to FAILED that is not a structural fetch failure. What
        it is for: a generation whose cache has been lost and cannot be
        restored, where the honest choice is to say so and start again rather
        than to let a scheduled job quietly do it.
        """
        self.set_status(GenerationStatus.FAILED, reason=reason)

    def record_roster(self, season_id: str, players: Sequence[Mapping[str, Any] | str]) -> None:
        """Store this generation's expected players for one competition.

        Accepts the provider's roster records, or bare ids for a caller that
        has nothing else. Records are what make this file usable as the
        source of truth; ids alone leave the loader reading the snapshot
        header, which cannot grow.

        Called on every visit, not only the first. A roster fetched again
        mid-generation can only grow the expected universe: a player who has
        left is still a player whose season happened, and dropping them here
        would silently shrink the thing being measured.

        A record for a player already present replaces the earlier one - it is
        the same player, described more recently, and a mid-season transfer is
        exactly the update worth keeping.
        """
        merged: dict[str, dict[str, Any] | None] = {
            player_id: record for player_id, record in self._stored_roster(season_id)
        }
        for entry in players:
            if isinstance(entry, Mapping):
                player_id = entry.get("id")
                if player_id is None:
                    continue
                merged[str(player_id)] = dict(entry)
            else:
                merged.setdefault(str(entry), None)

        self.roster_path(season_id).write_text(
            json.dumps(
                {
                    # A player stored as a bare id stays a bare string. An
                    # `{"id": ...}` stub would read back as a roster record and
                    # carry none of what one is read for, which is worse than
                    # admitting the record was never captured.
                    "players": [
                        record if record is not None else player_id
                        for player_id, record in merged.items()
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if season_id not in self.metadata.competitions_expected:
            self.metadata.competitions_expected.append(season_id)
        self._recount()

    def _stored_roster(self, season_id: str) -> list[tuple[str, dict[str, Any] | None]]:
        """What is on disk, in insertion order, in either file format.

        `None` as the record means "an id was stored and nothing else", which
        is what a generation written before rosters carried records holds.
        """
        path = self.roster_path(season_id)
        if not path.exists():
            return []
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if isinstance(parsed, list):
            return [(str(entry), None) for entry in parsed]
        if isinstance(parsed, dict):
            rows = parsed.get("players")
            if isinstance(rows, list):
                stored: list[tuple[str, dict[str, Any] | None]] = []
                for row in rows:
                    if isinstance(row, Mapping) and row.get("id") is not None:
                        stored.append((str(row["id"]), dict(row)))
                    elif isinstance(row, str):
                        stored.append((row, None))
                return stored
        return []

    def expected_players(self, season_id: str) -> list[str]:
        return [player_id for player_id, _ in self._stored_roster(season_id)]

    def roster_records(self, season_id: str) -> list[dict[str, Any]]:
        """The roster as the provider sent it, for whoever needs more than ids.

        Empty for a generation whose roster was stored as ids alone. Empty
        rather than reconstructed: an `{"id": ...}` stub would look like a
        roster record and carry none of what one is read for.
        """
        return [record for _, record in self._stored_roster(season_id) if record is not None]

    def _recount(self) -> None:
        total = 0
        for season_id in self.metadata.competitions_expected:
            total += len(self.expected_players(season_id))
        self.metadata.total_expected_players = total

    def refresh_counts(self, *, completed: int, failed: list[str]) -> None:
        self.metadata.completed_players = completed
        self.metadata.failed_players = sorted(set(failed))
        self._recount()

    def mark_competition_complete(self, season_id: str) -> None:
        if season_id not in self.metadata.competitions_complete:
            self.metadata.competitions_complete.append(season_id)

    def mark_competition_incomplete(self, season_id: str) -> None:
        if season_id in self.metadata.competitions_complete:
            self.metadata.competitions_complete.remove(season_id)

    def evaluate_completeness(self) -> bool:
        """Whether every expected competition is finished.

        Conservative: a competition this generation has never visited counts
        against completeness, however much a previous generation fetched. The
        cost of being wrong is publishing a partial universe as if it were the
        season.
        """
        expected = set(self.metadata.competitions_expected)
        complete = set(self.metadata.competitions_complete)
        self.metadata.complete = bool(expected) and expected <= complete
        return self.metadata.complete


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_generation_id(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime(GENERATION_ID)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class GenerationStore:
    """Every generation on disk, and which one a run should use."""

    def __init__(self, root: pathlib.Path = GENERATIONS_DIR) -> None:
        self.root = root

    def all(self) -> list[Generation]:
        """Every readable generation, oldest first."""
        if not self.root.exists():
            return []
        found: list[Generation] = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or not GENERATION_ID_PATTERN.match(directory.name):
                continue
            generation = self._read(directory)
            if generation is not None:
                found.append(generation)
        return found

    def _read(self, directory: pathlib.Path) -> Generation | None:
        path = directory / METADATA_FILE
        if not path.exists():
            return None
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Unreadable metadata is a structural fault, not a transient one.
            # Reporting it as absent would let a new generation start beside a
            # broken one and hide the breakage; `current()` raises instead.
            raise GenerationError(f"{path} is unreadable; inspect it before refreshing") from None
        if not isinstance(parsed, dict):
            raise GenerationError(f"{path} does not contain an object")
        known = {f for f in GenerationMetadata.__dataclass_fields__}
        metadata = GenerationMetadata(**{k: v for k, v in parsed.items() if k in known})
        return Generation(directory=directory, metadata=metadata)

    def latest(self) -> Generation | None:
        generations = self.all()
        return generations[-1] if generations else None

    def in_progress(self) -> Generation | None:
        """The one generation still being fetched, if any."""
        open_ones = [g for g in self.all() if g.status.is_fetchable]
        if len(open_ones) > 1:
            raise GenerationError(
                "more than one generation is IN_PROGRESS: "
                + ", ".join(g.generation_id for g in open_ones)
                + ". Two concurrent fetches would interleave; resolve by hand."
            )
        return open_ones[0] if open_ones else None

    def latest_published(self) -> Generation | None:
        published = [g for g in self.all() if g.status is GenerationStatus.PUBLISHED]
        return published[-1] if published else None

    def create(self, *, now: datetime | None = None) -> Generation:
        """Start a new generation. Refuses while one is still open."""
        open_one = self.in_progress()
        if open_one is not None:
            raise GenerationError(
                f"generation {open_one.generation_id} is still IN_PROGRESS "
                f"({open_one.metadata.completion_pct:.1f}% complete). Finish or fail it "
                f"before starting another."
            )
        generation_id = new_generation_id(now)
        directory = self.root / generation_id
        if directory.exists():
            raise GenerationError(f"{directory} already exists")
        directory.mkdir(parents=True)
        stamp = _now()
        generation = Generation(
            directory=directory,
            metadata=GenerationMetadata(
                generation_id=generation_id, created_at=stamp, last_updated_at=stamp
            ),
        )
        generation.save()
        return generation

    def get(self, generation_id: str) -> Generation | None:
        """One generation by id, or None. Never the nearest one."""
        for generation in self.all():
            if generation.generation_id == generation_id:
                return generation
        return None

    def resolve(
        self,
        *,
        resume: bool,
        now: datetime | None = None,
        expected_id: str | None = None,
    ) -> Generation:
        """The generation this run should work on.

        The decision the whole module exists for:

        - an open generation is resumed, because it is unfinished;
        - anything else starts a new one, because the last refresh is done and
          a refresh that reuses a finished generation's progress fetches
          nothing at all.

        `resume=False` is an explicit request for a new generation and will
        still refuse to abandon an open one - use `--new-generation` semantics
        deliberately rather than by forgetting a flag.

        `expected_id` is what the database says the open generation is. When
        it is given, this returns that generation or raises: never another
        open one, never a new one. A runner whose disk disagrees with the
        database has restored the wrong cache or none, and either way the
        fetch must not proceed into a universe the database is not tracking.
        """
        open_one = self.in_progress()

        if expected_id is not None:
            if open_one is None:
                raise GenerationError(
                    f"generation {expected_id} is IN_PROGRESS in the database but its local "
                    f"checkpoint state could not be restored. Nothing was resumed and nothing "
                    f"was started. Recover by restoring its cache, or abandon it explicitly: "
                    f"python -m pipelines.footystats.generations --abandon {expected_id}"
                )
            if open_one.generation_id != expected_id:
                raise GenerationError(
                    f"the database expects generation {expected_id} and the disk holds "
                    f"{open_one.generation_id}. Refusing to resume into the wrong generation."
                )
            return open_one

        if open_one is not None:
            if not resume:
                raise GenerationError(
                    f"generation {open_one.generation_id} is IN_PROGRESS. Pass --resume to "
                    f"continue it, or fail it explicitly before starting a new one."
                )
            return open_one
        return self.create(now=now)


# ---------------------------------------------------------------------------
# Administrative entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """`python -m pipelines.footystats.generations --abandon <id> --reason "..."`.

    The one thing this does is the one thing the pipeline must never do on its
    own: give up on a generation. It marks the generation FAILED on disk and,
    when a database is reachable, in `fact_refresh_generation` - so the next
    gate sees nothing live and the next cadence run starts fresh.
    """
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--abandon", metavar="GENERATION_ID", help="Mark this generation FAILED.")
    parser.add_argument(
        "--reason",
        default="abandoned by an operator",
        help="Recorded against the generation. Say why.",
    )
    parser.add_argument("--list", action="store_true", help="Show every generation on disk.")
    args = parser.parse_args(argv)

    store = GenerationStore()

    if args.list:
        for generation in store.all():
            meta = generation.metadata
            print(
                f"{generation.generation_id}  {meta.status:<12} "
                f"rev {meta.checkpoint_revision:<4} "
                f"{meta.completed_players:>6}/{meta.total_expected_players:<6} players"
            )
        return 0

    if not args.abandon:
        parser.print_help()
        return 2

    generation = store.get(args.abandon)
    if generation is None:
        # Not on disk. It may still be live in the database - the cache-lost
        # case, which is the case this command exists for - so the database
        # record is updated on its own.
        print(f"generation {args.abandon} is not on disk; marking it FAILED in the database only.")
        from pipelines.footystats import publish_status

        if not publish_status.mark_failed(args.abandon, reason=args.reason):
            print("could not reach the database; nothing was changed")
            return 1
        return 0

    generation.abandon(args.reason)
    from pipelines.footystats import publish_status

    publish_status.record(generation)
    print(f"generation {args.abandon} is FAILED: {args.reason}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
