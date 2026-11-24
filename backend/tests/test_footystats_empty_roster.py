"""A configured competition that comes back with no players is an error.

WHAT HAPPENED

FootyStats re-issued Colombia Categoria Primera A's 2026 season id in November
2026. The configured id (16614) began answering HTTP 200 with `data: null`, the
ingest took that for an empty but successful competition, and the generation
that started on 2026-11-16 was promoted without the league: 238 players and a
whole competition gone from the site, with a green run and no message.

An empty roster is now a named, non-fatal error whose fix is a decision - a new
id, or a declaration under `excluded` - not a re-run. These tests pin that, and
the configuration change that follows from it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pipelines.footystats.ingest import (
    CompetitionResult,
    RunReport,
    ingest_competition,
    snapshot_path,
    verdict,
)

from app.providers.footystats import FootyStatsProvider

#: What /league-players answered for season 16614 on 2026-11-24, trimmed.
COLOMBIA_BODY_AFTER_THE_ID_WAS_REISSUED = {
    "success": True,
    "pager": {"current_page": 1, "max_page": 1, "results_per_page": 200, "total_results": 1},
    "data": None,
}

CONFIG = Path(__file__).resolve().parents[2] / "config" / "competitions.yaml"


class EmptyRoster:
    def _roster(self, season_id: str) -> list[dict[str, Any]]:
        return []

    def _get(self, path: str, **params: object) -> Any:  # pragma: no cover - never reached
        raise AssertionError("no player should be fetched for an empty roster")


class TestTheIngestFlagsIt:
    def test_an_empty_roster_is_flagged_and_not_fatal(self) -> None:
        result = ingest_competition(
            EmptyRoster(), season_id="99991", name="Colombia Categoria Primera A", resume=False
        )
        assert result.empty_roster is True
        assert result.error and "roster is empty" in result.error
        # The run carries on to the next competition; only the verdict refuses.
        assert result.fatal is False
        assert result.not_subscribed is False
        assert result.complete is False

    def test_no_snapshot_is_written_for_it(self) -> None:
        ingest_competition(EmptyRoster(), season_id="99992", name="Nowhere", resume=False)
        assert not snapshot_path("99992").exists()

    def test_the_providers_own_null_data_reads_as_an_empty_roster(self) -> None:
        """The shape the real answer had: success, a one-row pager, `data: null`."""

        class Stub:
            def _get(self, path: str, **params: object) -> Any:
                return COLOMBIA_BODY_AFTER_THE_ID_WAS_REISSUED

        assert FootyStatsProvider._roster_pages(Stub(), "16614") == []  # type: ignore[arg-type]

    def test_a_competition_with_players_is_not_flagged_by_default(self) -> None:
        assert (
            CompetitionResult(season_id="17146", name="England Premier League").empty_roster
            is False
        )


def report_with(*competitions: CompetitionResult) -> RunReport:
    return RunReport(started_at="2026-11-24T09:00:00Z", competitions=list(competitions))


class TestTheVerdictNamesIt:
    def test_the_empty_competition_is_named_and_the_run_refuses(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = report_with(
            CompetitionResult(season_id="17199", name="Spain La Liga", skipped=200),
            CompetitionResult(
                season_id="16614",
                name="Colombia Categoria Primera A",
                error="roster is empty: the provider answered with no players for this season id",
                empty_roster=True,
            ),
        )
        assert verdict(report) == 1
        printed = capsys.readouterr().out

        assert "16614" in printed and "Colombia Categoria Primera A" in printed
        assert "Spain La Liga" not in printed
        assert "Re-running will not change this" in printed
        assert "config/competitions.yaml" in printed
        assert "excluded" in printed
        assert "run again to continue" not in printed.lower()


@pytest.fixture(scope="module")
def competitions() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


class TestTheConfigurationAfterIt:
    def test_colombia_uses_the_reissued_season_id(self, competitions: dict) -> None:
        colombia = [e for e in competitions["footystats"] if "Colombia" in e["name"]]
        assert [e["season_id"] for e in colombia] == [18081]
        assert 16614 not in {e["season_id"] for e in competitions["footystats"]}

    def test_the_caf_champions_league_is_declared_empty_rather_than_asked_for(
        self, competitions: dict
    ) -> None:
        """It has returned no players since it was added. With the guard on, asking
        for it would fail every run; declaring it is what the guard asks for."""
        assert 17550 not in {e["season_id"] for e in competitions["footystats"]}
        declared = [e for e in competitions["excluded"] if e.get("season_id") == 17550]
        assert len(declared) == 1
        assert "no players" in declared[0]["reason"]
