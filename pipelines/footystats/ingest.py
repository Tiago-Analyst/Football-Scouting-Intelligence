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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
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


def snapshot_path(season_id: str) -> Path:
    return SNAPSHOT_DIR / f"season-{season_id}.jsonl.gz"


def progress_path(season_id: str) -> Path:
    return SNAPSHOT_DIR / f"season-{season_id}.progress.json"


def _load_progress(season_id: str) -> set[str]:
    """Which players this competition already has. Empty when starting fresh."""
    path = progress_path(season_id)
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("done") or [])
    except (OSError, json.JSONDecodeError):
        # A truncated progress file means an interrupted write, not a reason to
        # refuse. Re-fetching a competition is slow, never wrong.
        return set()


def _save_progress(season_id: str, done: set[str]) -> None:
    progress_path(season_id).write_text(
        json.dumps({"done": sorted(done), "at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_competition(
    provider: Any,
    season_id: str,
    name: str,
    *,
    resume: bool,
    limit: int | None = None,
    deadline: Deadline | None = None,
) -> CompetitionResult:
    """Fetch one competition's roster and every player's detail."""
    from app.core.logging import get_logger

    log = get_logger(__name__)
    started = time.monotonic()
    result = CompetitionResult(season_id=season_id, name=name)

    target = snapshot_path(season_id)
    already = _load_progress(season_id) if resume else set()
    if already and not target.exists():
        # Progress without a snapshot cannot be trusted; start over.
        already = set()

    try:
        roster = provider._roster(season_id)
    except Exception as exc:
        result.error = f"roster failed: {type(exc).__name__}"
        result.seconds = time.monotonic() - started
        log.error("footystats_roster_failed", season_id=season_id, error=result.error)
        return result

    player_ids = [str(row["id"]) for row in roster if row.get("id") is not None]
    if limit is not None:
        player_ids = player_ids[:limit]
    result.players = len(player_ids)

    # Append so a resumed run adds to what is already there.
    mode = "ab" if (resume and target.exists()) else "wb"
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

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
            except Exception as exc:
                result.failed += 1
                log.warning(
                    "footystats_player_failed",
                    season_id=season_id,
                    player_id=player_id,
                    error=type(exc).__name__,
                )
                continue

            record = {"kind": "player", "player_id": player_id, "data": body.get("data")}
            handle.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))
            done.add(player_id)
            result.fetched += 1

            if index % CHECKPOINT_EVERY == 0:
                handle.flush()
                _save_progress(season_id, done)
                log.info(
                    "footystats_ingest_progress",
                    season_id=season_id,
                    done=len(done),
                    of=len(player_ids),
                )

    _save_progress(season_id, done)
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


def emit_completion(complete: bool) -> None:
    """Tell the caller whether the whole refresh is now on disk.

    Printed for a person, and appended to `$GITHUB_OUTPUT` for the workflow,
    which gates loading and publishing on it. Nothing downstream may run from a
    partial universe: the previous production data stays live until a complete
    one is ready, which is the whole reason fetching is separate from loading.
    """
    value = "true" if complete else "false"
    print(f"complete={value}")

    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"complete={value}\n")


def write_manifest(report: RunReport) -> Path:
    """Record what was fetched, when, and the checksum of every file.

    A snapshot nobody can verify is a snapshot nobody should reload from.
    """
    entries = []
    for competition in report.competitions:
        path = snapshot_path(competition.season_id)
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
                }
            )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "competitions": entries,
        "note": (
            "Raw FootyStats responses. Kept so transformations are reproducible "
            "without calling the API again. Not redistributed."
        ),
    }
    target = SNAPSHOT_DIR / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch FootyStats into raw snapshots.")
    parser.add_argument("--season", action="append", help="Only these season ids.")
    parser.add_argument("--resume", action="store_true", help="Continue an interrupted run.")
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
        )
        report.competitions.append(result)
        report.stopped_early = report.stopped_early or result.stopped_early
        marker = "ok" if result.ok else "FAILED"
        pending = f", {result.pending} pending" if result.pending else ""
        print(
            f"    {marker}: {result.fetched} fetched, {result.skipped} already had, "
            f"{result.failed} failed{pending}, {result.seconds / 60:.1f} min"
        )

    report.finished_at = datetime.now(UTC).isoformat()
    manifest = write_manifest(report)

    fetched = sum(c.fetched for c in report.competitions)
    failed = sum(c.failed for c in report.competitions)
    complete = report.complete

    print(f"\n{fetched:,} players fetched, {failed} failed.")
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

    emit_completion(complete)

    log.info(
        "footystats_ingest_finished",
        fetched=fetched,
        failed=failed,
        complete=complete,
        pending=report.pending,
        stopped_early=report.stopped_early,
    )

    # A graceful stop is a success. The distinction a caller needs is not "did
    # it finish" but "is the universe complete", and that is `complete`, not
    # the exit code. Conflating them would make every partial run look broken
    # and hide the runs that really are.
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
