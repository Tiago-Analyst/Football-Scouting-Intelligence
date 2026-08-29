"""Fetching into snapshots, and loading back out of them.

The two properties that make a fourteen-hour fetch workable:

**It survives interruption.** Progress is recorded per player, so a run that
stops after nine hours resumes rather than restarting. A fetch that has to be
perfect to be useful is a fetch nobody dares start.

**The load never calls the API.** It reads what was recorded, which is what
makes it fast, atomic, repeatable, and possible at three in the morning when the
provider is down.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from pipelines.footystats.ingest import (
    _load_progress,
    _save_progress,
    ingest_competition,
    snapshot_path,
)

from app.providers.footystats_snapshot import SnapshotReader, SnapshotUnavailableError


class FakeProvider:
    """A provider whose network is a dictionary, counting what it was asked."""

    def __init__(self, roster: list[dict[str, Any]], *, fail: set[str] | None = None) -> None:
        self._roster_rows = roster
        self._fail = fail or set()
        self.player_calls: list[str] = []

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        return self._roster_rows

    def _get(self, path: str, **params: object) -> Any:
        player_id = str(params.get("player_id"))
        self.player_calls.append(player_id)
        if player_id in self._fail:
            raise RuntimeError("provider said no")
        return {"data": [{"competition_id": 17146, "known_as": f"Player {player_id}"}]}


def roster(count: int) -> list[dict[str, Any]]:
    return [
        {"id": i, "known_as": f"Player {i}", "position": "Midfielder"} for i in range(1, count + 1)
    ]


@pytest.fixture(autouse=True)
def snapshots_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never write into the real snapshot directory from a test."""
    import pipelines.footystats.ingest as ingest

    monkeypatch.setattr(ingest, "SNAPSHOT_DIR", tmp_path)
    return tmp_path


class TestFetching:
    def test_it_writes_a_roster_and_one_line_per_player(self, snapshots_in_tmp: Path) -> None:
        provider = FakeProvider(roster(3))
        result = ingest_competition(provider, "17146", "A League", resume=False)

        assert result.fetched == 3
        assert result.ok

        with gzip.open(snapshot_path("17146"), "rb") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        assert records[0]["kind"] == "roster"
        assert [r["kind"] for r in records[1:]] == ["player"] * 3

    def test_a_failing_player_does_not_stop_the_competition(self, snapshots_in_tmp: Path) -> None:
        """One player's failure must not cost the other four hundred."""
        provider = FakeProvider(roster(4), fail={"2"})
        result = ingest_competition(provider, "17146", "A League", resume=False)

        assert result.fetched == 3
        assert result.failed == 1
        assert not result.ok  # reported, not hidden

    def test_a_failing_roster_ends_that_competition_only(self, snapshots_in_tmp: Path) -> None:
        class NoRoster(FakeProvider):
            def _roster(self, season_id: str) -> list[dict[str, Any]]:
                raise RuntimeError("upstream is down")

        result = ingest_competition(NoRoster([]), "17146", "A League", resume=False)
        assert result.error is not None
        assert result.fetched == 0

    def test_the_limit_bounds_what_is_fetched(self, snapshots_in_tmp: Path) -> None:
        provider = FakeProvider(roster(10))
        result = ingest_competition(provider, "17146", "A League", resume=False, limit=3)
        assert result.fetched == 3
        assert len(provider.player_calls) == 3


class TestResuming:
    def test_a_resumed_run_refetches_nothing(self, snapshots_in_tmp: Path) -> None:
        """The property that makes a fourteen-hour fetch restartable."""
        first = FakeProvider(roster(5))
        ingest_competition(first, "17146", "A League", resume=False)

        second = FakeProvider(roster(5))
        result = ingest_competition(second, "17146", "A League", resume=True)

        assert result.fetched == 0
        assert result.skipped == 5
        assert second.player_calls == []

    def test_a_resumed_run_fetches_only_what_is_new(self, snapshots_in_tmp: Path) -> None:
        ingest_competition(FakeProvider(roster(5)), "17146", "A League", resume=False)

        grown = FakeProvider(roster(8))
        result = ingest_competition(grown, "17146", "A League", resume=True)

        assert result.fetched == 3
        assert result.skipped == 5
        assert grown.player_calls == ["6", "7", "8"]

    def test_without_resume_it_starts_over(self, snapshots_in_tmp: Path) -> None:
        """`--resume` is opt-in: a plain re-run replaces the snapshot rather
        than appending to it, which is what a fresh season needs."""
        ingest_competition(FakeProvider(roster(3)), "17146", "A League", resume=False)
        again = FakeProvider(roster(3))
        result = ingest_competition(again, "17146", "A League", resume=False)
        assert result.fetched == 3
        assert len(again.player_calls) == 3

    def test_progress_without_a_snapshot_is_discarded(self, snapshots_in_tmp: Path) -> None:
        """Progress claiming work that no file contains cannot be trusted.
        Refetching is slow; trusting it would silently lose players."""
        _save_progress("17146", {"1", "2", "3"})
        assert _load_progress("17146") == {"1", "2", "3"}

        provider = FakeProvider(roster(3))
        result = ingest_competition(provider, "17146", "A League", resume=True)
        assert result.fetched == 3

    def test_a_corrupt_progress_file_is_survivable(self, snapshots_in_tmp: Path) -> None:
        """What an interrupted write leaves behind."""
        (snapshots_in_tmp / "season-17146.progress.json").write_text(
            "{ truncated", encoding="utf-8"
        )
        assert _load_progress("17146") == set()


class TestReadingBack:
    @pytest.fixture
    def reader(self, snapshots_in_tmp: Path) -> SnapshotReader:
        ingest_competition(FakeProvider(roster(4)), "17146", "A League", resume=False)
        return SnapshotReader(snapshots_in_tmp)

    def test_it_finds_what_was_fetched(self, reader: SnapshotReader) -> None:
        assert reader.available_seasons() == ["17146"]

    def test_it_serves_the_roster_in_the_api_shape(self, reader: SnapshotReader) -> None:
        """Shaped like the live response, so the provider's parsing is reused
        rather than reimplemented."""
        body = reader("/league-players", season_id="17146")
        assert len(body["data"]) == 4
        assert body["data"][0]["known_as"] == "Player 1"

    def test_it_serves_a_player(self, reader: SnapshotReader) -> None:
        body = reader("/player-stats", player_id="2")
        assert body["data"][0]["known_as"] == "Player 2"

    def test_an_unfetched_player_yields_an_empty_result(self, reader: SnapshotReader) -> None:
        """The same answer the API gives for a player with no record, which the
        provider already handles."""
        assert reader("/player-stats", player_id="9999")["data"] == []

    def test_a_missing_season_says_what_to_run(self, snapshots_in_tmp: Path) -> None:
        """Silently returning nothing would load an empty competition and look
        like the league had no players."""
        with pytest.raises(SnapshotUnavailableError, match="ingest"):
            SnapshotReader(snapshots_in_tmp)("/league-players", season_id="99999")

    def test_a_truncated_final_line_does_not_lose_the_file(self, snapshots_in_tmp: Path) -> None:
        """Exactly what an interrupted fetch leaves. The rest is intact and
        usable, so it is counted and skipped rather than raising."""
        ingest_competition(FakeProvider(roster(3)), "17146", "A League", resume=False)
        path = snapshot_path("17146")
        with gzip.open(path, "rb") as handle:
            body = handle.read()
        with gzip.open(path, "wb") as handle:
            handle.write(body + b'{"kind": "player", "player_id": "trunc')

        reader = SnapshotReader(snapshots_in_tmp)
        assert len(reader("/league-players", season_id="17146")["data"]) == 3

    def test_a_snapshot_still_being_written_is_read_as_far_as_it_goes(
        self, snapshots_in_tmp: Path
    ) -> None:
        """A full fetch takes hours, so loading while one is in progress is
        normal operation. The gzip stream then has no end-of-stream marker and
        raises on the *file*, not on a line - one layer below the truncated-line
        case, and initially unhandled. Refusing would mean no load is possible
        until every competition has finished."""
        ingest_competition(FakeProvider(roster(4)), "17146", "A League", resume=False)
        path = snapshot_path("17146")
        body = path.read_bytes()
        path.write_bytes(body[: int(len(body) * 0.8)])

        reader = SnapshotReader(snapshots_in_tmp)
        recovered = reader("/league-players", season_id="17146")["data"]
        assert recovered, "the roster is the first record and survives truncation"

    def test_an_unsupported_endpoint_is_refused(self, snapshots_in_tmp: Path) -> None:
        with pytest.raises(SnapshotUnavailableError):
            SnapshotReader(snapshots_in_tmp)("/league-list")


class TestTheLoadNeverCallsTheApi:
    def test_the_reader_satisfies_every_call_the_provider_makes(
        self, snapshots_in_tmp: Path
    ) -> None:
        """The provider asks for four paths during a load. If the reader could
        not serve one, the load would reach for the network mid-transaction."""
        ingest_competition(FakeProvider(roster(2)), "17146", "A League", resume=False)
        reader = SnapshotReader(snapshots_in_tmp)

        assert reader("/test-call")["success"] is True
        assert reader("/league-players", season_id="17146")["data"]
        assert reader("/player-stats", player_id="1")["data"]
        # Clubs are deliberately empty rather than invented; Transfermarkt
        # supplies club names.
        assert reader("/league-teams", season_id="17146")["data"] == []
