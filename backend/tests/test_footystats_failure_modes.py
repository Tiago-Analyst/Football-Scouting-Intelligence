"""Which failures should stop a run, and which are the run working.

THE DISTINCTION

A per-player endpoint that fails after the provider's own retries is one player
missing. They are not written to the snapshot, so they are not in `done`, so
they count as pending, so the run is incomplete, so nothing is published and
the next run retries exactly them. That is the design working. It used to exit
1, which turned an hour of saved progress into a red job for one transient 500
out of twenty-three thousand calls.

A rejected key is the opposite. Every request after it fails identically, each
one still paying the rate limiter's wait, so carrying on spends the whole run's
budget discovering the same thing forty-seven times. That needs a person, and
the exit code is how it says so.

What both have in common, and what must never change: an incomplete universe is
never published.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from pipelines.footystats import ingest
from pipelines.footystats.ingest import (
    CompetitionResult,
    RunReport,
    ingest_competition,
    load_failure_ledger,
    update_failure_ledger,
)

from app.providers.footystats import FootyStatsAuthError, FootyStatsError


class FlakyProvider:
    """Fails a named set of players, succeeds for everyone else."""

    def __init__(self, roster_rows: list[dict[str, Any]], *, failing: set[str]) -> None:
        self._roster_rows = roster_rows
        self.failing = failing
        self.calls: list[str] = []

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        return self._roster_rows

    def _get(self, path: str, **params: object) -> Any:
        player_id = str(params.get("player_id"))
        self.calls.append(player_id)
        if player_id in self.failing:
            raise FootyStatsError("/player-stats failed after 3 attempts: HTTP 500")
        return {"data": {"id": player_id}}


class RefusingProvider:
    """The key is rejected. `fail_from` decides whether the roster gets through."""

    def __init__(self, roster_rows: list[dict[str, Any]], *, roster_ok: bool = False) -> None:
        self._roster_rows = roster_rows
        self.roster_ok = roster_ok
        self.calls = 0

    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        if self.roster_ok:
            return self._roster_rows
        raise FootyStatsAuthError("/league-players refused: HTTP 403")

    def _get(self, path: str, **params: object) -> Any:
        self.calls += 1
        raise FootyStatsAuthError("/player-stats refused: HTTP 401")


def roster(count: int) -> list[dict[str, Any]]:
    return [{"id": i} for i in range(1, count + 1)]


@pytest.fixture
def snapshots_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ingest, "SNAPSHOT_DIR", tmp_path)
    return tmp_path


def snapshot_players(path: Path) -> list[str]:
    with gzip.open(path, "rb") as handle:
        return [
            json.loads(line)["player_id"]
            for line in handle
            if json.loads(line).get("kind") == "player"
        ]


# ---------------------------------------------------------------------------
# Recoverable: one player's endpoint fails
# ---------------------------------------------------------------------------


class TestARecoverablePlayerFailure:
    def test_the_rest_of_the_roster_is_still_fetched(self, snapshots_in_tmp: Path) -> None:
        provider = FlakyProvider(roster(6), failing={"3"})
        result = ingest_competition(provider, "1", "Test League", resume=False)

        assert result.fetched == 5
        assert result.failed == 1

    def test_the_failed_players_are_named_not_merely_counted(self, snapshots_in_tmp: Path) -> None:
        """So the next run can say what it is retrying, and a player who fails
        every week can be told apart from a different player failing each week.
        """
        provider = FlakyProvider(roster(6), failing={"2", "5"})
        result = ingest_competition(provider, "1", "Test League", resume=False)

        assert sorted(result.failed_player_ids) == ["2", "5"]

    def test_it_is_not_fatal(self, snapshots_in_tmp: Path) -> None:
        provider = FlakyProvider(roster(4), failing={"1"})
        result = ingest_competition(provider, "1", "Test League", resume=False)

        assert result.fatal is False
        assert result.error is None

    def test_the_competition_is_incomplete_so_nothing_can_be_published(
        self, snapshots_in_tmp: Path
    ) -> None:
        """The guarantee that matters most. A failed player is a hole in the
        universe, and a universe with a hole in it is not the season.
        """
        provider = FlakyProvider(roster(4), failing={"1"})
        result = ingest_competition(provider, "1", "Test League", resume=False)

        assert result.pending == 1
        assert result.complete is False
        assert RunReport(started_at="t", competitions=[result]).complete is False

    def test_the_run_exits_successfully(self, snapshots_in_tmp: Path) -> None:
        """A saved hour of progress is not a broken job."""
        result = ingest_competition(
            FlakyProvider(roster(4), failing={"1"}), "1", "Test League", resume=False
        )
        report = RunReport(started_at="t", competitions=[result])

        assert report.fatal is False
        assert report.failed_count == 1
        assert not any(c.error for c in report.competitions)


class TestTheNextRunRetriesThem:
    def test_a_resumed_run_fetches_only_what_failed(self, snapshots_in_tmp: Path) -> None:
        first = FlakyProvider(roster(6), failing={"3", "4"})
        ingest_competition(first, "1", "Test League", resume=False)

        # The provider has recovered.
        second = FlakyProvider(roster(6), failing=set())
        result = ingest_competition(second, "1", "Test League", resume=True)

        assert sorted(second.calls) == ["3", "4"], "it re-fetched players it already had"
        assert result.fetched == 2
        assert result.skipped == 4

    def test_and_the_universe_is_then_complete(self, snapshots_in_tmp: Path) -> None:
        ingest_competition(
            FlakyProvider(roster(6), failing={"3"}), "1", "Test League", resume=False
        )
        result = ingest_competition(
            FlakyProvider(roster(6), failing=set()), "1", "Test League", resume=True
        )

        assert result.pending == 0
        assert result.complete is True
        assert RunReport(started_at="t", competitions=[result]).complete is True

    def test_the_snapshot_holds_every_player_exactly_once(self, snapshots_in_tmp: Path) -> None:
        """Appending on resume must not duplicate what was already written."""
        ingest_competition(
            FlakyProvider(roster(6), failing={"3"}), "1", "Test League", resume=False
        )
        ingest_competition(FlakyProvider(roster(6), failing=set()), "1", "Test League", resume=True)

        written = snapshot_players(ingest.snapshot_path("1"))
        assert sorted(written) == ["1", "2", "3", "4", "5", "6"]
        assert len(written) == len(set(written))


# ---------------------------------------------------------------------------
# Fatal: the credential is refused
# ---------------------------------------------------------------------------


class TestAFatalAuthenticationFailure:
    def test_a_refused_roster_is_fatal(self, snapshots_in_tmp: Path) -> None:
        result = ingest_competition(RefusingProvider(roster(5)), "1", "Test League", resume=False)

        assert result.fatal is True
        assert result.error is not None

    def test_it_does_not_spend_the_budget_discovering_it_again(
        self, snapshots_in_tmp: Path
    ) -> None:
        provider = RefusingProvider(roster(500))
        ingest_competition(provider, "1", "Test League", resume=False)

        assert provider.calls == 0, "it kept calling a key that had been refused"

    def test_a_key_revoked_mid_competition_stops_that_competition(
        self, snapshots_in_tmp: Path
    ) -> None:
        """The roster came back, then the key stopped working."""
        provider = RefusingProvider(roster(200), roster_ok=True)
        result = ingest_competition(provider, "1", "Test League", resume=False)

        assert result.fatal is True
        assert provider.calls == 1, "it did not stop at the first refusal"

    def test_the_report_says_the_run_is_fatal(self, snapshots_in_tmp: Path) -> None:
        result = ingest_competition(RefusingProvider(roster(5)), "1", "Test League", resume=False)
        report = RunReport(started_at="t", competitions=[result])

        assert report.fatal is True
        assert report.complete is False

    def test_a_fatal_run_is_never_complete(self, snapshots_in_tmp: Path) -> None:
        """Belt and braces on the rule everything else depends on."""
        good = ingest_competition(
            FlakyProvider(roster(3), failing=set()), "1", "Complete League", resume=False
        )
        bad = ingest_competition(RefusingProvider(roster(3)), "2", "Refused League", resume=False)
        report = RunReport(started_at="t", competitions=[good, bad], unvisited=4)

        assert good.complete is True
        assert report.complete is False


class TestTheProviderNamesTheFatalCase:
    """The distinction has to exist at the provider or the ingest cannot see it."""

    def test_an_auth_error_is_a_footystats_error(self) -> None:
        """So existing `except FootyStatsError` handlers still catch it."""
        assert issubclass(FootyStatsAuthError, FootyStatsError)

    def test_the_message_carries_no_key(self) -> None:
        error = FootyStatsAuthError("/player-stats refused: HTTP 403. The API key is wrong.")
        assert "key=" not in str(error)


# ---------------------------------------------------------------------------
# The ledger, so a player failing forever is visible
# ---------------------------------------------------------------------------


class TestThePersistentFailureLedger:
    def test_a_failure_is_recorded(self, snapshots_in_tmp: Path) -> None:
        result = CompetitionResult(season_id="1", name="L", failed=1, failed_player_ids=["77"])
        ledger = update_failure_ledger(RunReport(started_at="t", competitions=[result]))

        assert ledger["77"]["runs_failed"] == 1

    def test_repeated_failures_accumulate(self, snapshots_in_tmp: Path) -> None:
        """The signal that separates a broken record from weather."""
        for _ in range(3):
            result = CompetitionResult(season_id="1", name="L", failed=1, failed_player_ids=["77"])
            update_failure_ledger(RunReport(started_at="t", competitions=[result]))

        assert load_failure_ledger()["77"]["runs_failed"] == 3

    def test_the_first_and_last_dates_are_both_kept(self, snapshots_in_tmp: Path) -> None:
        report = RunReport(
            started_at="t",
            competitions=[
                CompetitionResult(season_id="1", name="L", failed=1, failed_player_ids=["77"])
            ],
        )
        update_failure_ledger(report, now="2026-01-01T00:00:00+00:00")
        update_failure_ledger(report, now="2026-03-01T00:00:00+00:00")

        entry = load_failure_ledger()["77"]
        assert entry["first_failed_at"].startswith("2026-01-01")
        assert entry["last_failed_at"].startswith("2026-03-01")

    def test_a_player_who_succeeds_is_cleared(self, snapshots_in_tmp: Path) -> None:
        """A ledger that only grows would report every historical blip forever."""
        failing = CompetitionResult(season_id="1", name="L", failed=1, failed_player_ids=["3"])
        update_failure_ledger(RunReport(started_at="t", competitions=[failing]))
        assert "3" in load_failure_ledger()

        # A real run that fetched them.
        ingest_competition(
            FlakyProvider(roster(4), failing=set()), "1", "Test League", resume=False
        )
        recovered = ingest_competition(
            FlakyProvider(roster(4), failing=set()), "1", "Test League", resume=True
        )
        recovered.fetched = 1  # force the ledger to consult this competition
        update_failure_ledger(RunReport(started_at="t", competitions=[recovered]))

        assert "3" not in load_failure_ledger()

    def test_a_corrupt_ledger_does_not_fail_a_fetch(self, snapshots_in_tmp: Path) -> None:
        """It records history about failures; it gates nothing."""
        (snapshots_in_tmp / "failures.json").write_text("{not json", encoding="utf-8")
        assert load_failure_ledger() == {}
