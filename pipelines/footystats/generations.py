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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

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
        """
        return self.directory / f"season-{season_id}.roster.json"

    @property
    def metadata_path(self) -> pathlib.Path:
        return self.directory / METADATA_FILE

    # -- Mutation ------------------------------------------------------------

    def save(self) -> None:
        self.metadata.last_updated_at = _now()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(
            json.dumps(asdict(self.metadata), indent=2, sort_keys=True), encoding="utf-8"
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

    def record_roster(self, season_id: str, player_ids: list[str]) -> None:
        """Store this generation's expected players for one competition.

        Called on every visit, not only the first. A roster fetched again
        mid-generation can only grow the expected universe: a player who has
        left is still a player whose season happened, and dropping them here
        would silently shrink the thing being measured.
        """
        path = self.roster_path(season_id)
        known: list[str] = []
        if path.exists():
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(parsed, list):
                    known = [str(p) for p in parsed]
            except (OSError, json.JSONDecodeError):
                known = []

        merged = list(dict.fromkeys([*known, *(str(p) for p in player_ids)]))
        path.write_text(json.dumps(merged, indent=0), encoding="utf-8")

        if season_id not in self.metadata.competitions_expected:
            self.metadata.competitions_expected.append(season_id)
        self._recount()

    def expected_players(self, season_id: str) -> list[str]:
        path = self.roster_path(season_id)
        if not path.exists():
            return []
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [str(p) for p in parsed] if isinstance(parsed, list) else []

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

    def resolve(self, *, resume: bool, now: datetime | None = None) -> Generation:
        """The generation this run should work on.

        The decision the whole module exists for:

        - an open generation is resumed, because it is unfinished;
        - anything else starts a new one, because the last refresh is done and
          a refresh that reuses a finished generation's progress fetches
          nothing at all.

        `resume=False` is an explicit request for a new generation and will
        still refuse to abandon an open one - use `--new-generation` semantics
        deliberately rather than by forgetting a flag.
        """
        open_one = self.in_progress()
        if open_one is not None:
            if not resume:
                raise GenerationError(
                    f"generation {open_one.generation_id} is IN_PROGRESS. Pass --resume to "
                    f"continue it, or fail it explicitly before starting a new one."
                )
            return open_one
        return self.create(now=now)
