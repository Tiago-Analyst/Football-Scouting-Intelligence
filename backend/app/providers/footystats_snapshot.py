"""Serve recorded FootyStats responses instead of calling the API.

The provider talks to the network through one method. This replaces it with a
reader over the snapshots `pipelines.footystats.ingest` wrote, so the loader
gets exactly the same canonical records without a single request.

That matters for three reasons.

**A load must be reproducible.** Specification section 4 keeps raw snapshots so
transformations can be re-run; a load that re-fetched would produce different
data every time and could never be compared against a previous run.

**A load must be fast.** Fetching takes hours and the load runs in one
transaction. Reading from disk takes seconds.

**A load must not need the API to be up.** Re-running last week's load should
work at three in the morning when the provider is down, because the data is
already here.

The provider itself is unchanged and unaware: it asks for a path and parameters
and gets a response-shaped dictionary back, whatever produced it.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from app.core import paths
from app.core.logging import get_logger

log = get_logger(__name__)

REPO_ROOT = paths.REPO_ROOT
SNAPSHOT_DIR = REPO_ROOT / "data" / "raw" / "footystats" / "snapshots"


class SnapshotUnavailableError(Exception):
    """No snapshot exists for what was asked. Never a silent empty result."""


class SnapshotReader:
    """Reads one competition's recorded responses.

    Loaded lazily and held in memory: a competition is a few hundred players and
    the loader walks all of them, so reading the file once beats seeking it per
    player.
    """

    def __init__(self, directory: Path = SNAPSHOT_DIR) -> None:
        self._directory = directory
        self._rosters: dict[str, list[dict[str, Any]]] = {}
        self._players: dict[str, dict[str, Any]] = {}
        self._loaded: set[str] = set()

    # -- Loading ------------------------------------------------------------

    def available_seasons(self) -> list[str]:
        """Which competitions have a snapshot, from the files themselves."""
        if not self._directory.exists():
            return []
        return sorted(
            path.name[len("season-") : -len(".jsonl.gz")]
            for path in self._directory.glob("season-*.jsonl.gz")
        )

    def _generation_roster(self, season_id: str) -> list[dict[str, Any]]:
        """The roster file beside the snapshot, when this is a generation.

        Read directly rather than through `pipelines.footystats.generations`:
        this module is in the serving layer and the pipeline package is not a
        dependency of it. The file is one JSON object and the format is stated
        where it is written.
        """
        path = self._directory / f"season-{season_id}.roster.json"
        if not path.exists():
            return []
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("footystats_generation_roster_unreadable", season_id=season_id)
            return []

        rows = parsed.get("players") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            # A bare list of ids: a generation from before rosters carried
            # records. Nothing here to prefer over the header.
            return []
        return [r for r in rows if isinstance(r, dict) and r.get("id") is not None]

    def _load(self, season_id: str) -> None:
        if season_id in self._loaded:
            return

        path = self._directory / f"season-{season_id}.jsonl.gz"
        if not path.exists():
            raise SnapshotUnavailableError(
                f"no snapshot for season {season_id}. Run "
                f"`python -m pipelines.footystats.ingest --season {season_id}` first."
            )

        # THE ROSTER COMES FROM THE GENERATION WHEN THERE IS ONE.
        #
        # The snapshot's first line is written once, when the file is created,
        # and a full fetch spans days. A player signed in January is added to
        # the generation's roster on the next visit and can never reach that
        # header - so the loader, reading the header, expected them, fetched
        # them, and then had no roster row to take their club from.
        #
        # The header stays as the fallback: a snapshot from before generations,
        # or a `--flat` local fetch, has nothing else.
        roster: list[dict[str, Any]] = self._generation_roster(season_id)
        header_roster: list[dict[str, Any]] = []
        players: dict[str, Any] = {}
        malformed = 0
        incomplete = False

        try:
            with gzip.open(path, "rb") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        # A truncated final line is what an interrupted fetch
                        # leaves behind. Counted and skipped rather than failing
                        # the load, because the rest is intact and usable.
                        malformed += 1
                        continue

                    if record.get("kind") == "roster":
                        header_roster = [
                            r for r in (record.get("data") or []) if isinstance(r, dict)
                        ]
                    elif record.get("kind") == "player":
                        players[str(record.get("player_id"))] = record.get("data")
        except (EOFError, gzip.BadGzipFile, OSError):
            # No end-of-stream marker: the file is still being written, or the
            # fetch was killed. A full run takes hours, so reading a snapshot
            # mid-fetch is normal operation rather than an error - and refusing
            # would mean no load is possible until every competition is done.
            # Everything decompressed so far is intact and already collected.
            incomplete = True

        if malformed or incomplete:
            log.warning(
                "footystats_snapshot_incomplete",
                season_id=season_id,
                malformed_lines=malformed,
                truncated=incomplete,
                players_recovered=len(players),
                note="players missing from this snapshot load with no statistics",
            )

        if not roster:
            roster = header_roster
        elif header_roster:
            missing = len(
                {str(r.get("id")) for r in roster} - {str(r.get("id")) for r in header_roster}
            )
            if missing:
                log.info(
                    "footystats_roster_grew_since_the_snapshot_header",
                    season_id=season_id,
                    players_added_after_the_fetch_began=missing,
                    note="read from the generation roster, which the header cannot grow to hold",
                )

        self._rosters[season_id] = roster
        for player_id, data in players.items():
            self._players[player_id] = data
        self._loaded.add(season_id)

        log.info(
            "footystats_snapshot_loaded",
            season_id=season_id,
            roster=len(roster),
            players=len(players),
        )

    # -- The provider's transport seam --------------------------------------

    def __call__(self, path: str, **params: object) -> Any:
        """Answer a provider request from the snapshot.

        Shaped exactly like the live response - `{"data": ...}` - because the
        provider's parsing is the thing being reused, and reproducing it here
        would be a second implementation to keep in step.
        """
        if path == "/league-players":
            season_id = str(params.get("season_id"))
            self._load(season_id)
            return {"data": self._rosters.get(season_id, [])}

        if path == "/player-stats":
            player_id = str(params.get("player_id"))
            if player_id not in self._players:
                # A player is only known once the season carrying them has been
                # read. The load happens to ask for the roster first, so this
                # worked by ordering rather than by design - and a reader that
                # returns "no such player" because of call order would drop
                # players silently. Load everything, then answer.
                for season_id in self.available_seasons():
                    self._load(season_id)

            if player_id not in self._players:
                # The fetch recorded a failure for this player, or never reached
                # them. An empty list is the same answer the API gives for a
                # player with no record, and the provider already handles it.
                return {"data": []}
            return {"data": self._players[player_id]}

        if path == "/league-teams":
            # Clubs are not snapshotted: the roster carries `club_team_id` and
            # the loader resolves names from Transfermarkt, which knows them
            # better. Returning empty is honest; inventing names would not be.
            return {"data": []}

        if path == "/test-call":
            return {"success": True, "data": "snapshot"}

        raise SnapshotUnavailableError(f"{path} is not served from snapshots")
