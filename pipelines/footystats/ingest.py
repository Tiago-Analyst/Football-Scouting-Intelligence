"""Fetch FootyStats into raw snapshots. Specification Phase 14.

Run from the repository root:

    python -m pipelines.footystats.ingest                    # every configured competition
    python -m pipelines.footystats.ingest --season 17146     # just one
    python -m pipelines.footystats.ingest --resume           # continue an interrupted run
    python -m pipelines.footystats.ingest --dry-run          # what it would fetch, and how long

Writes to `data/raw/footystats/snapshots/`, which is git-ignored.

---------------------------------------------------------------------------
WHY FETCHING IS SEPARATE FROM LOADING
---------------------------------------------------------------------------

The action statistics need one request per player. Across 47 competitions that
is roughly 25,000 requests, and at the account's 1,800 an hour a full run takes
about fourteen hours.

Fourteen hours inside a database transaction is not a plan. It holds locks for
half a day, keeps everything in memory, and loses the lot to one network blip
near the end.

So this stage does one thing: it fetches, and writes what it received to disk.
Loading reads those files, which makes the load fast, atomic and — because the
raw responses are still there — **reproducible without touching the API again**
(specification section 4: keep raw snapshots so transformations are
reproducible).

It also makes interruption survivable. Progress is recorded per player, so a run
that stops after nine hours resumes from where it stopped rather than from the
beginning.

---------------------------------------------------------------------------
WHAT IS STORED
---------------------------------------------------------------------------

One gzipped JSON-lines file per competition: the roster, then one line per
player carrying that player's complete `/player-stats` response. Complete, not
filtered to the season being ingested - a filtered snapshot is no longer the raw
response, and the point of keeping it is to be able to re-derive anything later
without asking the provider again.

Gzip because the responses repeat their field names 188 times per record and
compress by roughly an order of magnitude.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if TYPE_CHECKING:
    from pipelines.footystats.generations import Generation

SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "footystats" / "snapshots"

#: A competition's file is written whole at the end, but progress is flushed
#: this often so an interrupted run loses at most this many players' work.
CHECKPOINT_EVERY = 25


class Deadline:
    """When to stop of our own accord.

    A full refresh is roughly fourteen hours at the account's rate limit, and
    the GitHub job that drives it is capped at sixty minutes. Being killed at
    the cap is survivable but wasteful: the process dies mid-write, the
    progress file is as old as the last checkpoint, and - worse - a job killed
    by timeout is not guaranteed to persist a cache it created, so the work of
    the whole hour can be lost rather than merely truncated.

    So the run stops itself with time in hand, flushes, records where it got
    to, and exits successfully. The next run continues.
    """

    def __init__(self, minutes: float | None) -> None:
        # `None` means no limit; nought means already out of time. Written as
        # an explicit None check because `if minutes` treats the two the same,
        # and a caller passing 0 means the opposite of unlimited.
        self.limit_seconds = None if minutes is None else minutes * 60
        self.started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def expired(self) -> bool:
        return self.limit_seconds is not None and self.elapsed >= self.limit_seconds

    @property
    def remaining(self) -> float | None:
        if self.limit_seconds is None:
            return None
        return max(0.0, self.limit_seconds - self.elapsed)


@dataclass
class CompetitionResult:
    season_id: str
    name: str
    players: int = 0
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    seconds: float = 0.0
    error: str | None = None
    #: True when the run stopped here because it was running out of time,
    #: rather than because there was nothing left to fetch.
    stopped_early: bool = False
    #: Roster players still unfetched when this competition was left.
    pending: int = 0
    #: The players whose own endpoint failed after retries. Recorded rather
    #: than counted so the next run can say what it is retrying, and so a
    #: player failing every week can be told apart from a different player
    #: failing each week - the first is a broken record, the second is weather.
    failed_player_ids: list[str] = field(default_factory=list)
    #: True when the failure was one that will not fix itself: a rejected key,
    #: a provider refusing everything. Distinguished from a per-player error
    #: because the two need opposite handling.
    fatal: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.failed == 0

    @property
    def complete(self) -> bool:
        """Every player in the roster is in the snapshot.

        Separate from `ok`. A competition can finish cleanly with work left -
        that is what a graceful stop looks like - and it can be complete while
        having failed, which is a different problem and reported separately.
        """
        return self.error is None and self.pending == 0


@dataclass
class RunReport:
    started_at: str
    finished_at: str | None = None
    requests: int = 0
    competitions: list[CompetitionResult] = field(default_factory=list)
    #: Competitions this run never reached, because it ran out of time first.
    unvisited: int = 0
    stopped_early: bool = False

    @property
    def failed(self) -> bool:
        return any(not c.ok for c in self.competitions)

    @property
    def complete(self) -> bool:
        """Whether the whole requested refresh is now on disk.

        Conservative on purpose. A competition this run never reached is not
        known to be complete, whatever a previous run may have done, so it
        counts against completeness until a run actually looks at it. The cost
        of being wrong here is publishing a partial universe as if it were the
        season.
        """
        if self.unvisited:
            return False
        return bool(self.competitions) and all(c.complete for c in self.competitions)

    @property
    def pending(self) -> int:
        return sum(c.pending for c in self.competitions)

    @property
    def fatal(self) -> bool:
        """Whether the run hit something no later run will get past unaided."""
        return any(c.fatal for c in self.competitions)

    @property
    def fatal_reason(self) -> str | None:
        """What the fatal condition was, for the generation's record."""
        for competition in self.competitions:
            if competition.fatal:
                return competition.error
        return None

    @property
    def failed_player_ids(self) -> list[str]:
        """Every player whose endpoint failed, across the whole run."""
        return [pid for c in self.competitions for pid in c.failed_player_ids]

    @property
    def failed_count(self) -> int:
        return sum(c.failed for c in self.competitions)


def snapshot_path(season_id: str) -> Path:
    return SNAPSHOT_DIR / f"season-{season_id}.jsonl.gz"


def progress_path(season_id: str) -> Path:
    return SNAPSHOT_DIR / f"season-{season_id}.progress.json"


def _read_progress(path: Path) -> set[str]:
    """Completed player ids from an explicit path.

    Accepts both shapes this file has had: the `{"done": [...]}` object it
    writes, and a bare list, which is what a generation's roster files look
    like and what a hand-written fixture tends to be. Reading both costs
    nothing; guessing wrong costs a re-fetch of a whole competition.
    """
    if not path.exists():
        return set()
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A truncated progress file means an interrupted write, not a reason to
        # refuse. Re-fetching a competition is slow, never wrong.
        return set()
    if isinstance(parsed, dict):
        return {str(p) for p in (parsed.get("done") or [])}
    if isinstance(parsed, list):
        return {str(p) for p in parsed}
    return set()


def _write_progress(path: Path, done: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"done": sorted(done), "at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )


def _load_progress(season_id: str) -> set[str]:
    """Which players this competition already has, in the flat layout."""
    return _read_progress(progress_path(season_id))


def _save_progress(season_id: str, done: set[str]) -> None:
    _write_progress(progress_path(season_id), done)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_clubs(provider: Any, season_id: str, generation: Generation | None, log: Any) -> None:
    """Store the competition's clubs alongside its roster.

    WHY THIS IS WORTH ONE MORE REQUEST

    The roster gives every player a `club_team_id` and nothing that turns it
    into a club. So the loader had no clubs to create, dropped the reference
    it could not resolve, and every FootyStats player arrived with no club at
    all: 3,442 of them unmatched, none carrying the one signal that separates
    two players with the same name and no date of birth.

    The matcher has scored club agreement all along - `exact_name+dob+club`
    reaches 1.00 - and could never see it from this side. One request per
    competition, once per generation, is what it costs to let it.

    Never fatal. A competition whose clubs cannot be fetched still has its
    players fetched; identity resolution then works from name, date of birth
    and nationality as it did before, which is worse than with clubs and much
    better than nothing.
    """
    if generation is None:
        return

    path = generation.clubs_path(season_id)
    if path.exists():
        return

    try:
        body = provider._get("/league-teams", season_id=season_id)
    except Exception as exc:  # the clubs are an enrichment, not the fetch
        log.warning("footystats_clubs_unavailable", season_id=season_id, error=type(exc).__name__)
        return

    rows = body.get("data") if isinstance(body, dict) else None
    clubs = [r for r in (rows or []) if isinstance(r, dict) and r.get("id") is not None]
    path.write_text(json.dumps({"clubs": clubs}, ensure_ascii=False), encoding="utf-8")
    log.info("footystats_clubs_recorded", season_id=season_id, clubs=len(clubs))


def ingest_competition(
    provider: Any,
    season_id: str,
    name: str,
    *,
    resume: bool,
    limit: int | None = None,
    deadline: Deadline | None = None,
    generation: Generation | None = None,
) -> CompetitionResult:
    """Fetch one competition's roster and every player's detail."""
    from app.core.logging import get_logger

    # Imported here with the logger, following this module's pattern: `app` is
    # only importable once the path setup at the bottom of the imports has run.
    from app.providers.footystats import FootyStatsAuthError

    log = get_logger(__name__)
    started = time.monotonic()
    result = CompetitionResult(season_id=season_id, name=name)

    # Inside a generation when one is supplied, which is how the pipeline runs
    # it. The flat-directory paths remain for direct calls and older tests, and
    # they are the layout whose progress state outlived the refresh it belonged
    # to - see `pipelines.footystats.generations`.
    target = generation.snapshot_path(season_id) if generation else snapshot_path(season_id)
    progress = generation.progress_path(season_id) if generation else progress_path(season_id)

    already = _read_progress(progress) if resume else set()
    if already and not target.exists():
        # Progress without a snapshot cannot be trusted; start over.
        already = set()

    try:
        roster = provider._roster(season_id)
    except FootyStatsAuthError as exc:
        # Fatal. The key is refused, so every competition after this one would
        # fail identically - and each attempt still costs the rate limiter's
        # wait, so carrying on would spend the run's whole budget discovering
        # the same thing 47 times.
        result.error = f"roster refused: {exc}"
        result.fatal = True
        result.seconds = time.monotonic() - started
        log.error("footystats_auth_failed", season_id=season_id)
        return result
    except Exception as exc:
        result.error = f"roster failed: {type(exc).__name__}"
        result.seconds = time.monotonic() - started
        log.error("footystats_roster_failed", season_id=season_id, error=result.error)
        return result

    player_ids = [str(row["id"]) for row in roster if row.get("id") is not None]
    if limit is not None:
        player_ids = player_ids[:limit]

    if generation is not None:
        # THE GENERATION'S OWN UNIVERSE, REFRESHED ON EVERY VISIT.
        #
        # The roster used to be the snapshot's first line, written once when
        # the file was created. A generation that started in September could
        # therefore never discover a January signing: the roster was fetched
        # again on resume and the newly-returned players had nowhere to be
        # recorded, so they were not part of what "complete" meant.
        #
        # `record_roster` merges rather than replaces, so a player who has
        # since left the club stays expected - their season happened, and
        # dropping them would quietly shrink the thing being measured.
        #
        # The records, not the ids. The roster carries `club_team_id`, which is
        # where a player's club comes from, so a file of ids left the loader
        # reading the snapshot's immutable header instead - and the January
        # signing this file exists to capture was expected, fetched, and then
        # dropped on the way in because the header had never heard of them.
        wanted = set(player_ids)
        generation.record_roster(
            season_id,
            [row for row in roster if row.get("id") is not None and str(row["id"]) in wanted],
        )
        player_ids = generation.expected_players(season_id) or player_ids

    _record_clubs(provider, season_id, generation, log)

    result.players = len(player_ids)

    # Append so a resumed run adds to what is already there.
    mode = "ab" if (resume and target.exists()) else "wb"
    target.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(target, mode) as handle:
        if mode == "wb":
            header = {"kind": "roster", "season_id": season_id, "data": roster}
            handle.write((json.dumps(header, ensure_ascii=False) + "\n").encode("utf-8"))

        done = set(already)
        for index, player_id in enumerate(player_ids, start=1):
            if player_id in done:
                result.skipped += 1
                continue
            # Checked before the request, not after: stopping with the write
            # already made and the progress file not yet updated would re-fetch
            # that player next time, which costs a request from a budget the
            # whole design exists to husband.
            if deadline is not None and deadline.expired():
                result.stopped_early = True
                break
            try:
                body = provider._get("/player-stats", player_id=player_id)
            except FootyStatsAuthError:
                # A key that worked for the roster and stops working mid-run -
                # revoked, or a quota exhausted for the period. Everything
                # already written stays written and progress is saved below;
                # what must not happen is grinding through the remaining
                # players collecting identical refusals.
                result.error = "authentication failed mid-competition"
                result.fatal = True
                log.error("footystats_auth_failed", season_id=season_id, player_id=player_id)
                break
            except Exception as exc:
                # Recoverable. One player's endpoint failed after the
                # provider's own retries; the rest of the roster is unaffected.
                # They stay out of `done`, so they count as pending, so the run
                # is incomplete and nothing is published - and the next run
                # retries exactly them.
                result.failed += 1
                result.failed_player_ids.append(player_id)
                log.warning(
                    "footystats_player_failed",
                    season_id=season_id,
                    player_id=player_id,
                    error=type(exc).__name__,
                )
                continue

            record = {
                "kind": "player",
                "player_id": player_id,
                "data": body.get("data"),
            }
            handle.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
            done.add(player_id)
            result.fetched += 1

            if index % CHECKPOINT_EVERY == 0:
                handle.flush()
                _write_progress(progress, done)
                log.info(
                    "footystats_ingest_progress",
                    season_id=season_id,
                    done=len(done),
                    of=len(player_ids),
                )

    _write_progress(progress, done)
    result.pending = len([p for p in player_ids if p not in done])
    result.seconds = time.monotonic() - started
    log.info(
        "footystats_competition_ingested",
        season_id=season_id,
        fetched=result.fetched,
        skipped=result.skipped,
        failed=result.failed,
        pending=result.pending,
        stopped_early=result.stopped_early,
        seconds=round(result.seconds, 1),
    )
    return result


def failure_ledger_path() -> Path:
    return SNAPSHOT_DIR / "failures.json"


def load_failure_ledger() -> dict[str, dict[str, object]]:
    """Players that have failed, and how often, across runs."""
    path = failure_ledger_path()
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A corrupt ledger is an inconvenience, not a reason to fail a fetch:
        # it records history about failures, it does not gate anything.
        return {}
    return parsed if isinstance(parsed, dict) else {}


def update_failure_ledger(report: RunReport, *, now: str | None = None) -> dict[str, dict]:
    """Fold this run's failures into the ledger, and clear the ones that healed.

    WHY THIS IS KEPT AT ALL

    A player whose endpoint fails is retried next run, and the run before that
    told nobody. A player whose endpoint fails *every* run is a broken record
    that will hold the universe incomplete forever, and is indistinguishable
    from transient weather unless somebody counts.

    So: a failure increments a count and stamps a date; a successful fetch
    removes the entry entirely. A player who appears here with a high count and
    a recent date is the case worth a human's attention, and
    `pipelines.quality` reads exactly that.
    """
    stamp = now or datetime.now(UTC).isoformat()
    ledger = load_failure_ledger()

    failed_now = set(report.failed_player_ids)
    for player_id in failed_now:
        entry = ledger.get(player_id) or {}
        ledger[player_id] = {
            "runs_failed": int(entry.get("runs_failed", 0)) + 1,
            "first_failed_at": entry.get("first_failed_at", stamp),
            "last_failed_at": stamp,
        }

    # Anything fetched this run is working again, whatever its history.
    for competition in report.competitions:
        if competition.fetched:
            for player_id in _load_progress(competition.season_id):
                if player_id not in failed_now:
                    ledger.pop(player_id, None)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    failure_ledger_path().write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    return ledger


def emit_completion(
    complete: bool,
    *,
    failed_count: int = 0,
    fatal: bool = False,
    generation_id: str | None = None,
) -> None:
    """Tell the caller whether the whole refresh is now on disk.

    Printed for a person, and appended to `$GITHUB_OUTPUT` for the workflow,
    which gates loading and publishing on it. Nothing downstream may run from a
    partial universe: the previous production data stays live until a complete
    one is ready, which is the whole reason fetching is separate from loading.

    `failed_count` and `fatal` travel with it so the workflow can say *why* a
    run was incomplete without parsing the log. Being short of time and being
    short of a working key produce the same `complete=false` and want very
    different summaries.
    """
    values = {
        "complete": "true" if complete else "false",
        "failed_count": str(failed_count),
        "fatal": "true" if fatal else "false",
    }
    if generation_id:
        values["generation_id"] = generation_id
    for key, value in values.items():
        print(f"{key}={value}")

    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def write_manifest(report: RunReport, generation: Generation | None = None) -> Path:
    """Record what was fetched, when, and the checksum of every file.

    A snapshot nobody can verify is a snapshot nobody should reload from.
    """
    entries = []
    for competition in report.competitions:
        path = (
            generation.snapshot_path(competition.season_id)
            if generation
            else snapshot_path(competition.season_id)
        )
        if path.exists():
            entries.append(
                {
                    "season_id": competition.season_id,
                    "name": competition.name,
                    "file": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "players": competition.players,
                    "fetched": competition.fetched,
                    "failed": competition.failed,
                    "failed_player_ids": competition.failed_player_ids,
                    "pending": competition.pending,
                    "complete": competition.complete,
                }
            )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        # The three questions a reader of this file actually has, answered at
        # the top rather than reconstructed by summing the entries below.
        "generation_id": generation.generation_id if generation else None,
        "complete": report.complete,
        "failed_count": report.failed_count,
        "failed_player_ids": report.failed_player_ids,
        "fatal": report.fatal,
        "competitions": entries,
        "note": (
            "Raw FootyStats responses. Kept so transformations are reproducible "
            "without calling the API again. Not redistributed."
        ),
    }
    target = (generation.directory if generation else SNAPSHOT_DIR) / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch FootyStats into raw snapshots.")
    parser.add_argument("--season", action="append", help="Only these season ids.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Continue the current refresh generation. Without it, an open "
            "generation is refused rather than abandoned."
        ),
    )
    parser.add_argument(
        "--only-resume",
        action="store_true",
        help=(
            "Continue an open generation and never start one. What the hourly "
            "continuation cron passes: it must not begin a fourteen-hour "
            "refresh every hour."
        ),
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help=(
            "Use the old single-directory layout instead of a generation. For "
            "one-off local fetches; the pipeline never passes it."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Players per competition; for testing."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be fetched and stop."
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=float,
        default=None,
        metavar="MINUTES",
        help=(
            "Stop cleanly after this long and exit 0, recording what is left. "
            "Set it below the job's own timeout: a killed process cannot flush, "
            "and a job killed by timeout is not guaranteed to persist its cache."
        ),
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings
    from app.core.logging import configure_logging, get_logger
    from app.providers.footystats import REQUESTS_PER_HOUR, FootyStatsProvider
    from pipelines.footystats import publish_status
    from pipelines.footystats.generations import (
        GenerationError,
        GenerationStatus,
        GenerationStore,
    )

    settings = get_settings()
    configure_logging(settings)
    log = get_logger(__name__)

    if not settings.footystats_configured:
        print(
            "No FOOTYSTATS_API_KEY is set. Nothing was fetched.",
            file=sys.stderr,
        )
        return 2

    provider = FootyStatsProvider(settings)
    competitions = provider.get_competitions()
    if args.season:
        wanted = {str(s) for s in args.season}
        competitions = [c for c in competitions if c.competition_id in wanted]
        if not competitions:
            print(f"No configured competition matches {sorted(wanted)}.", file=sys.stderr)
            return 2

    if args.dry_run:
        # One roster call plus one per player. The player count is only known
        # after the roster, so this estimates from a typical squad size rather
        # than pretending to know.
        typical = 500
        estimated = len(competitions) * (1 + typical)
        hours = estimated / REQUESTS_PER_HOUR
        print(f"{len(competitions)} competitions configured.")
        print(
            f"Roughly {estimated:,} requests at {REQUESTS_PER_HOUR}/hour: about {hours:.1f} hours."
        )
        print("\nCompetitions:")
        for competition in competitions:
            path = snapshot_path(competition.competition_id)
            state = "snapshot exists" if path.exists() else "not fetched"
            print(f"  {competition.competition_id:<7} {competition.name:<40} {state}")
        return 0

    # WHICH REFRESH THIS RUN BELONGS TO
    #
    # A generation is one attempt at a complete universe. Resolving it here is
    # what stops `--resume` doing the wrong thing after a refresh finishes:
    # progress belongs to a generation, so a finished one is never resumed and
    # a new one starts empty. See `pipelines.footystats.generations`.
    generation = None
    if not args.flat:
        try:
            store = GenerationStore()
            if args.only_resume:
                # Defence in depth behind the workflow gate. The gate decides
                # whether to run at all; this makes it impossible for a
                # continuation run to start a refresh even if it does run -
                # a fourteen-hour fetch begun by an hourly cron would be
                # expensive and silent.
                generation = store.in_progress()
                if generation is None:
                    print("No generation is in progress and --only-resume forbids starting one.")
                    return 0
            else:
                generation = store.resolve(resume=args.resume)
        except GenerationError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            return 1
        print(f"Generation {generation.generation_id} ({generation.status.value}).")
        log.info(
            "footystats_generation_resolved",
            generation_id=generation.generation_id,
            status=generation.status.value,
            completed=generation.metadata.completed_players,
            expected=generation.metadata.total_expected_players,
        )
    else:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    report = RunReport(started_at=datetime.now(UTC).isoformat())

    log.info("footystats_ingest_started", competitions=len(competitions), resume=args.resume)
    print(f"Fetching {len(competitions)} competitions. Ctrl-C is safe: --resume continues.\n")

    deadline = Deadline(args.max_runtime_minutes)
    if deadline.limit_seconds:
        print(f"Stopping cleanly after {args.max_runtime_minutes:.0f} minutes.\n")

    for position, competition in enumerate(competitions, start=1):
        if deadline.expired():
            # Everything from here is unvisited, and unvisited is not complete
            # however much a previous run may have fetched.
            report.unvisited = len(competitions) - position + 1
            report.stopped_early = True
            print(
                f"\nOut of time with {report.unvisited} competition(s) unvisited. "
                "Progress is saved; the next run continues."
            )
            break

        print(f"[{position}/{len(competitions)}] {competition.name} ({competition.competition_id})")
        result = ingest_competition(
            provider,
            competition.competition_id,
            competition.name,
            resume=args.resume,
            limit=args.limit,
            deadline=deadline,
            generation=generation,
        )
        report.competitions.append(result)
        if generation is not None:
            # After every competition, not only at the end. A run killed
            # between competitions should leave metadata describing what it
            # did rather than what it set out to do.
            if result.complete:
                generation.mark_competition_complete(result.season_id)
            else:
                generation.mark_competition_incomplete(result.season_id)
            generation.refresh_counts(
                completed=sum(c.fetched + c.skipped for c in report.competitions),
                failed=report.failed_player_ids,
            )
            generation.evaluate_completeness()
            generation.save()
            # Best-effort: the site cannot see the generation directory, so
            # progress is projected into the database for it to read. A
            # failure here is not a failed refresh.
            publish_status.record(generation)
        report.stopped_early = report.stopped_early or result.stopped_early
        if result.fatal:
            report.unvisited = len(competitions) - position
            print(f"    FATAL: {result.error}")
            print("\nStopping. This will not fix itself by trying the next competition.")
            break
        marker = "ok" if result.ok else "FAILED"
        pending = f", {result.pending} pending" if result.pending else ""
        print(
            f"    {marker}: {result.fetched} fetched, {result.skipped} already had, "
            f"{result.failed} failed{pending}, {result.seconds / 60:.1f} min"
        )

    report.finished_at = datetime.now(UTC).isoformat()
    manifest = write_manifest(report, generation)

    if generation is not None:
        generation.refresh_counts(
            completed=sum(c.fetched + c.skipped for c in report.competitions),
            failed=report.failed_player_ids,
        )
        # `report.complete` also accounts for competitions this run never
        # reached, which the generation's own bookkeeping cannot see.
        generation.metadata.complete = generation.evaluate_completeness() and report.complete
        if report.fatal:
            # Structural, not transient. The generation is abandoned rather
            # than left open to be resumed into the same wall - and a
            # transient player failure never reaches here, which is the whole
            # distinction: one player costs one player, not fourteen hours.
            generation.set_status(GenerationStatus.FAILED, reason=str(report.fatal_reason))
        elif generation.metadata.complete:
            generation.set_status(GenerationStatus.COMPLETE)
        else:
            generation.save()
        publish_status.record(generation)
    ledger = update_failure_ledger(report)
    persistent = {pid: e for pid, e in ledger.items() if int(e.get("runs_failed", 0)) >= 3}
    if persistent:
        print(
            f"\n{len(persistent)} player(s) have now failed three or more runs "
            f"running. These hold the universe incomplete and want looking at: "
            + ", ".join(sorted(persistent)[:10])
        )

    fetched = sum(c.fetched for c in report.competitions)
    failed = report.failed_count
    complete = report.complete

    print(f"\n{fetched:,} players fetched, {failed} failed.")
    if failed:
        sample = ", ".join(report.failed_player_ids[:10])
        more = "" if failed <= 10 else f" (+{failed - 10} more)"
        print(f"Failed players, which the next run retries: {sample}{more}")
    if complete:
        print("The requested refresh is COMPLETE.")
        print(
            "\nNext: python -m pipelines.load.load_providers --source footystats --replace --verify"
        )
    else:
        incomplete = sum(1 for c in report.competitions if not c.complete)
        print(
            f"The refresh is INCOMPLETE: {report.pending:,} player(s) pending across "
            f"{incomplete} competition(s), {report.unvisited} competition(s) unvisited."
        )
        print("Nothing should be loaded from a partial universe. Run again to continue.")
    print(f"Manifest: {manifest.relative_to(REPO_ROOT)}")

    emit_completion(
        complete,
        failed_count=failed,
        fatal=report.fatal,
        generation_id=generation.generation_id if generation else None,
    )

    log.info(
        "footystats_ingest_finished",
        fetched=fetched,
        failed=failed,
        complete=complete,
        pending=report.pending,
        stopped_early=report.stopped_early,
        fatal=report.fatal,
    )

    # WHAT THE EXIT CODE MEANS, AND WHAT IT DOES NOT
    #
    # Not "is the universe complete" - that is `complete`, emitted separately,
    # and it is what gates the load. Conflating the two made every partial run
    # look broken and hid the runs that really were.
    #
    # It used to return 1 whenever any player had failed, which is the same
    # mistake pointing the other way: one transient 500 on one player out of
    # twenty-three thousand turned a run that had saved an hour of good
    # progress into a red job. Those players are simply not in `done`, so they
    # are pending, so `complete` is false, so nothing is published and the next
    # run retries exactly them. That is the design working, not failing.
    #
    # So the exit code answers one question: did something happen that another
    # run will not get past on its own? A rejected key, or a competition whose
    # roster could not be read at all. Those need a person.
    if report.fatal:
        print("\nExiting non-zero: this run failed for a reason retrying will not fix.")
        return 1
    if any(c.error for c in report.competitions):
        print("\nExiting non-zero: at least one competition could not be read at all.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
