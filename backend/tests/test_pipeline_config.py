"""The scheduled pipeline's configuration.

Specification section 22 requires the refresh cadence to be configurable, and
section 23 requires that a failed validation publishes nothing.

GitHub will not read a cron from a config file — the schedule must be a literal
in the workflow. So the same cadence is written twice, and two copies of a fact
drift. These tests make the drift fail rather than go unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPETITIONS = REPO_ROOT / "config" / "competitions.yaml"
PIPELINE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def competitions() -> dict:
    return load(COMPETITIONS)


@pytest.fixture(scope="module")
def workflow() -> dict:
    parsed = load(PIPELINE_WORKFLOW)
    # YAML 1.1 reads a bare `on:` key as the boolean True.
    parsed["triggers"] = parsed.get("on") or parsed.get(True)
    return parsed


class TestCadence:
    def test_the_config_declares_both_sources(self, competitions: dict) -> None:
        refresh = competitions["refresh"]
        assert set(refresh) == {"footystats", "transfermarkt"}

    def test_every_declared_cadence_appears_in_the_workflow(
        self, competitions: dict, workflow: dict
    ) -> None:
        """The one that would silently rot: someone changes the config, the
        schedule does not move, and the pipeline keeps its old cadence while
        the file says otherwise."""
        configured = {entry["cron"] for entry in competitions["refresh"].values()}
        scheduled = {entry["cron"] for entry in workflow["triggers"]["schedule"]}
        assert configured == scheduled

    def test_every_source_says_whether_it_is_enabled(self, competitions: dict) -> None:
        for name, entry in competitions["refresh"].items():
            assert isinstance(entry.get("enabled"), bool), name

    def test_footystats_is_enabled(self, competitions: dict) -> None:
        """A key now exists and the catalogue has been probed, so the schedule
        has something to fetch. This asserted the opposite until then."""
        assert competitions["refresh"]["footystats"]["enabled"] is True


class TestCompetitionList:
    def test_every_competition_carries_its_evidence(self, competitions: dict) -> None:
        """This asserted the list was empty, because no identifier had ever been
        observed. Now that /league-list has been called, the invariant it
        protected is unchanged — nothing here may be invented — but it is
        expressed as: every entry says what it is and when it was seen.
        """
        entries = competitions["footystats"]
        assert entries, "the catalogue has been probed; this should not be empty"
        for entry in entries:
            assert isinstance(entry["season_id"], int), entry
            assert entry["name"], entry
            assert entry["season"], entry
            assert entry["added_on"], entry

    def test_season_ids_are_unique(self, competitions: dict) -> None:
        """The same season twice would load one competition's players twice and
        double every count derived from them."""
        ids = [e["season_id"] for e in competitions["footystats"]]
        assert len(set(ids)) == len(ids)

    def test_every_competition_has_a_current_season(self, competitions: dict) -> None:
        """A stale season id silently loads football several years old onto a
        site that presents itself as current. Three subscribed competitions have
        no recent season at all and are recorded under `excluded` instead."""
        for entry in competitions["footystats"]:
            year = int(str(entry["season"])[:4])
            assert year >= 2026, entry

    def test_excluded_competitions_say_why(self, competitions: dict) -> None:
        """Dropping them silently would leave the next person to rediscover that
        their top flights stop years ago in this catalogue."""
        for entry in competitions.get("excluded") or []:
            assert entry["reason"], entry
            assert entry["latest_season"], entry

    def test_transfermarkt_is_ingested_whole(self, competitions: dict) -> None:
        """Filtering it before load would discard the identities that identity
        resolution needs to match against."""
        assert competitions["transfermarkt"]["ingest_all_competitions"] is True


class TestWorkflowSafety:
    def test_it_does_not_run_on_push(self, workflow: dict) -> None:
        """A data refresh triggered by a commit would republish production data
        on an unrelated code change."""
        assert "push" not in workflow["triggers"]
        assert "pull_request" not in workflow["triggers"]

    def test_concurrent_runs_are_prevented(self, workflow: dict) -> None:
        """Two loads writing the same tables at once is the one way to get a
        half-published dataset past a transactional loader."""
        concurrency = workflow["concurrency"]
        assert concurrency["group"]
        assert concurrency["cancel-in-progress"] is False

    def test_the_load_step_verifies_before_publishing(self, workflow: dict) -> None:
        """Section 23 rule 11. Without `--verify` the quality suite runs after
        the commit, and a failure is found with the bad data already live."""
        steps = workflow["jobs"]["refresh"]["steps"]
        load = next(s for s in steps if s.get("id") == "load")
        assert "--verify" in load["run"]

    def test_the_api_key_is_never_echoed(self, workflow: dict) -> None:
        """It reaches the FootyStats step as an environment variable and must
        not appear in a `run:` line, where it would land in the public log."""
        for step in workflow["jobs"]["refresh"]["steps"]:
            assert "${{ secrets.FOOTYSTATS_API_KEY }}" not in (step.get("run") or "")

    def test_a_failed_load_still_reports(self, workflow: dict) -> None:
        """A pipeline that goes quiet on failure is worse than one that fails
        loudly: nobody learns the data stopped refreshing."""
        steps = workflow["jobs"]["refresh"]["steps"]
        summary = next(s for s in steps if s.get("name") == "Summarise the run")
        assert summary["if"].startswith("always()")
