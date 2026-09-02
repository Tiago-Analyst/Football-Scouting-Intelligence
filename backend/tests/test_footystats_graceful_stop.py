"""Stopping before the job is killed, and refusing to publish half a season.

A full FootyStats refresh is about fourteen hours at the account's rate limit,
driven by a GitHub job capped at sixty minutes. The previous design relied on
`--resume` plus `actions/cache`, which sounds sufficient and is not: a job
killed by its own timeout is not guaranteed to persist a cache it created, so
the hour's work could be lost rather than merely truncated - and the process
dies mid-write with the progress file as old as the last checkpoint.

So the run now stops itself with time in hand and reports whether the whole
refresh is on disk. That second part is what protects production: a partial
universe must never be loaded, and the previous data stays live until a
complete one exists.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import pytest
from pipelines.footystats import ingest
from pipelines.footystats.ingest import (
    CompetitionResult,
    Deadline,
    RunReport,
    emit_completion,
    ingest_competition,
)


class FakeProvider:
    """A roster, and a clock that advances with every player fetched."""

    def __init__(self, roster: list[dict[str, Any]], *, seconds_per_player: float = 0.0) -> None:
        self._roster_rows = roster
        self.seconds_per_player = seconds_per_player
        self.calls = 0
        self.clock = 0.0

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        return self._roster_rows

    def _get(self, path: str, **params: object) -> Any:
        self.calls += 1
        self.clock += self.seconds_per_player
        return {"data": {"id": params.get("player_id")}}


def roster(count: int) -> list[dict[str, Any]]:
    return [{"id": i} for i in range(1, count + 1)]


@pytest.fixture
def snapshots_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ingest, "SNAPSHOT_DIR", tmp_path)
    return tmp_path


class FakeClock:
    """A monotonic clock the test drives, so nothing sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TestTheDeadline:
    def test_no_limit_never_expires(self) -> None:
        assert Deadline(None).expired() is False
        assert Deadline(None).remaining is None

    def test_a_limit_expires_once_it_is_reached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = FakeClock()
        monkeypatch.setattr(ingest.time, "monotonic", clock)
        deadline = Deadline(1)  # one minute

        assert deadline.expired() is False
        clock.now = 59.0
        assert deadline.expired() is False
        assert deadline.remaining == pytest.approx(1.0)
        clock.now = 60.0
        assert deadline.expired() is True
        assert deadline.remaining == 0.0


class TestStoppingMidCompetition:
    def test_it_stops_and_says_so(
        self, snapshots_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = FakeClock()
        monkeypatch.setattr(ingest.time, "monotonic", clock)

        provider = FakeProvider(roster(10))
        original = provider._get

        def ticking(path: str, **params: object) -> Any:
            clock.now += 10.0
            return original(path, **params)

        monkeypatch.setattr(provider, "_get", ticking)

        result = ingest_competition(
            provider,
            "17146",
            "A League",
            resume=False,
            deadline=Deadline(0.5),  # 30s
        )

        assert result.stopped_early is True
        assert result.complete is False
        assert 0 < result.fetched < 10
        assert result.pending == 10 - result.fetched

    def test_what_it_fetched_is_on_disk_and_readable(
        self, snapshots_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The file must be flushed and closed, not left half-written.

        A truncated gzip member is the failure this guards: the loader has been
        caught by one before, and a snapshot that cannot be read is worse than
        one that is short, because it fails at load time rather than here.
        """
        clock = FakeClock()
        monkeypatch.setattr(ingest.time, "monotonic", clock)
        provider = FakeProvider(roster(20))
        original = provider._get

        def ticking(path: str, **params: object) -> Any:
            clock.now += 5.0
            return original(path, **params)

        monkeypatch.setattr(provider, "_get", ticking)

        result = ingest_competition(
            provider, "17146", "A League", resume=False, deadline=Deadline(0.5)
        )

        path = ingest.snapshot_path("17146")
        with gzip.open(path, "rb") as handle:
            lines = handle.read().decode("utf-8").splitlines()
        # One roster header plus one line per player actually fetched.
        assert len(lines) == result.fetched + 1

    def test_progress_is_saved_so_the_next_run_continues(
        self, snapshots_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = FakeClock()
        monkeypatch.setattr(ingest.time, "monotonic", clock)
        provider = FakeProvider(roster(20))
        original = provider._get

        def ticking(path: str, **params: object) -> Any:
            clock.now += 5.0
            return original(path, **params)

        monkeypatch.setattr(provider, "_get", ticking)
        first = ingest_competition(
            provider, "17146", "A League", resume=False, deadline=Deadline(0.5)
        )
        assert first.stopped_early

        # Second run, no deadline: it must pick up exactly where the first left
        # off and re-fetch nothing.
        second = ingest_competition(FakeProvider(roster(20)), "17146", "A League", resume=True)
        assert second.skipped == first.fetched
        assert second.fetched == 20 - first.fetched
        assert second.complete is True
        assert second.pending == 0

    def test_a_deadline_already_passed_fetches_nobody(self, snapshots_in_tmp: Path) -> None:
        """And still writes a readable file rather than a broken one."""
        provider = FakeProvider(roster(5))
        result = ingest_competition(
            provider, "17146", "A League", resume=False, deadline=Deadline(0)
        )
        assert result.fetched == 0
        assert result.stopped_early is True
        assert result.pending == 5
        assert provider.calls == 0


class TestWhatCountsAsComplete:
    def test_a_finished_competition_is_complete(self, snapshots_in_tmp: Path) -> None:
        result = ingest_competition(FakeProvider(roster(4)), "17146", "A", resume=False)
        assert result.complete is True
        assert result.pending == 0

    def test_a_run_is_complete_only_when_every_competition_is(self) -> None:
        done = CompetitionResult("1", "A", pending=0)
        partial = CompetitionResult("2", "B", pending=7)
        assert RunReport(started_at="x", competitions=[done]).complete is True
        assert RunReport(started_at="x", competitions=[done, partial]).complete is False

    def test_a_competition_never_visited_counts_against_completeness(self) -> None:
        """Conservative on purpose.

        A competition this run never reached is not known to be complete,
        whatever a previous run may have fetched. The cost of assuming
        otherwise is publishing a partial universe as if it were the season.
        """
        done = CompetitionResult("1", "A", pending=0)
        report = RunReport(started_at="x", competitions=[done], unvisited=3)
        assert report.complete is False

    def test_an_empty_run_is_not_complete(self) -> None:
        """Nothing fetched is not the same as everything fetched."""
        assert RunReport(started_at="x").complete is False

    def test_a_competition_that_errored_is_not_complete(self) -> None:
        broken = CompetitionResult("1", "A", pending=0, error="roster failed: TimeoutError")
        assert broken.complete is False
        assert RunReport(started_at="x", competitions=[broken]).complete is False


class TestTellingTheWorkflow:
    def test_it_writes_the_flag_the_workflow_gates_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        output = tmp_path / "github_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))

        emit_completion(False)
        emit_completion(True)

        assert output.read_text(encoding="utf-8").splitlines() == [
            "complete=false",
            "complete=true",
        ]
        assert "complete=false" in capsys.readouterr().out

    def test_outside_actions_it_still_says_so_on_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        emit_completion(True)
        assert "complete=true" in capsys.readouterr().out
