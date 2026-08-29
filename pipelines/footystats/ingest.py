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

    @property
    def ok(self) -> bool:
        return self.error is None and self.failed == 0


@dataclass
class RunReport:
    started_at: str
    finished_at: str | None = None
    requests: int = 0
    competitions: list[CompetitionResult] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(not c.ok for c in self.competitions)


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
    result.seconds = time.monotonic() - started
    log.info(
        "footystats_competition_ingested",
        season_id=season_id,
        fetched=result.fetched,
        skipped=result.skipped,
        failed=result.failed,
        seconds=round(result.seconds, 1),
    )
    return result


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

    for position, competition in enumerate(competitions, start=1):
        print(f"[{position}/{len(competitions)}] {competition.name} ({competition.competition_id})")
        result = ingest_competition(
            provider,
            competition.competition_id,
            competition.name,
            resume=args.resume,
            limit=args.limit,
        )
        report.competitions.append(result)
        marker = "ok" if result.ok else "FAILED"
        print(
            f"    {marker}: {result.fetched} fetched, {result.skipped} already had, "
            f"{result.failed} failed, {result.seconds / 60:.1f} min"
        )

    report.finished_at = datetime.now(UTC).isoformat()
    manifest = write_manifest(report)

    fetched = sum(c.fetched for c in report.competitions)
    failed = sum(c.failed for c in report.competitions)
    print(f"\n{fetched:,} players fetched, {failed} failed.")
    print(f"Manifest: {manifest.relative_to(REPO_ROOT)}")
    print("\nNext: python -m pipelines.load.load_providers --source footystats --replace --verify")

    log.info("footystats_ingest_finished", fetched=fetched, failed=failed)
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
