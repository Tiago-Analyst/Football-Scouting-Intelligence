"""Which provider a scheduled run refreshes.

The bug these cover: every step in `pipeline.yml` resolved its source as
`inputs.source || 'transfermarkt'`. A scheduled run carries no inputs, so the
fallback applied to all of them - and the Monday, Wednesday and Friday crons,
which exist to refresh FootyStats, refreshed Transfermarkt instead.

Two kinds of test here, and both are needed. The first kind exercises the
resolver. The second reads `pipeline.yml` itself, because a correct resolver
that no step reads from would pass every test in the first group.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from pipelines.load.resolve_source import (
    KNOWN_SOURCES,
    UnresolvedSource,
    cron_map,
    load_config,
    resolve,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"


@pytest.fixture(scope="module")
def config() -> dict:
    return dict(load_config())


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(workflow: dict) -> list[dict]:
    return workflow["jobs"]["refresh"]["steps"]


def _step(workflow: dict, name: str) -> dict:
    for step in _steps(workflow):
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r}")


class TestTheScheduleDecidesTheSource:
    def test_sunday_refreshes_the_market_source(self, config: dict) -> None:
        assert (
            resolve(
                event_name="schedule",
                schedule="0 5 * * 0",
                input_source=None,
                config=config,
            )
            == "transfermarkt"
        )

    def test_monday_wednesday_friday_refresh_the_performance_source(self, config: dict) -> None:
        """The cron this whole module exists for."""
        assert (
            resolve(
                event_name="schedule",
                schedule="0 4 * * 1,3,5",
                input_source=None,
                config=config,
            )
            == "footystats"
        )

    def test_whitespace_in_the_cron_does_not_change_the_answer(self, config: dict) -> None:
        assert (
            resolve(
                event_name="schedule",
                schedule="0  4 * *  1,3,5",
                input_source=None,
                config=config,
            )
            == "footystats"
        )

    def test_an_unclaimed_cron_stops_the_run(self, config: dict) -> None:
        """Rather than defaulting, which is the failure being fixed.

        A schedule nobody can account for must not pick a provider and write to
        production with it.
        """
        with pytest.raises(UnresolvedSource, match="claims the cron"):
            resolve(event_name="schedule", schedule="30 2 * * 4", input_source=None, config=config)

    def test_a_schedule_with_no_cron_at_all_stops_the_run(self, config: dict) -> None:
        with pytest.raises(UnresolvedSource):
            resolve(event_name="schedule", schedule="", input_source=None, config=config)


class TestManualRunsUseWhatWasChosen:
    @pytest.mark.parametrize("chosen", KNOWN_SOURCES)
    def test_the_operators_choice_is_respected(self, config: dict, chosen: str) -> None:
        assert (
            resolve(
                event_name="workflow_dispatch",
                schedule=None,
                input_source=chosen,
                config=config,
            )
            == chosen
        )

    def test_a_manual_run_ignores_any_schedule_it_was_handed(self, config: dict) -> None:
        """Belt and braces: dispatch never consults the cron table."""
        assert (
            resolve(
                event_name="workflow_dispatch",
                schedule="0 5 * * 0",
                input_source="footystats",
                config=config,
            )
            == "footystats"
        )

    def test_an_unknown_source_is_refused(self, config: dict) -> None:
        with pytest.raises(UnresolvedSource, match="unknown source"):
            resolve(
                event_name="workflow_dispatch",
                schedule=None,
                input_source="wikipedia",
                config=config,
            )

    def test_an_empty_choice_is_refused_rather_than_defaulted(self, config: dict) -> None:
        with pytest.raises(UnresolvedSource):
            resolve(event_name="workflow_dispatch", schedule=None, input_source="", config=config)


class TestOtherTriggers:
    def test_a_push_cannot_refresh_production(self, config: dict) -> None:
        with pytest.raises(UnresolvedSource, match="cannot resolve"):
            resolve(event_name="push", schedule=None, input_source=None, config=config)


class TestTheWorkflowAndTheConfigAgree:
    """The two files hold the same crons and GitHub will not read one of them.

    So this is the check that keeps them in step, and it is the reason the
    resolver reads the config rather than hard-coding a third copy.
    """

    def test_every_cron_in_the_workflow_is_claimed_by_a_source(
        self, workflow: dict, config: dict
    ) -> None:
        # `on` is parsed by PyYAML 1.1 rules as the boolean True.
        triggers = workflow.get("on") or workflow.get(True)
        scheduled = [entry["cron"] for entry in triggers["schedule"]]
        claimed = cron_map(config)

        unclaimed = [cron for cron in scheduled if " ".join(cron.split()) not in claimed]
        assert not unclaimed, (
            f"{unclaimed} fires in the workflow and no source in "
            f"config/competitions.yaml claims it, so a real run would stop"
        )

    def test_every_scheduled_source_has_a_cron_in_the_workflow(
        self, workflow: dict, config: dict
    ) -> None:
        triggers = workflow.get("on") or workflow.get(True)
        scheduled = {" ".join(entry["cron"].split()) for entry in triggers["schedule"]}
        for cron, source in cron_map(config).items():
            enabled = (config["refresh"][source] or {}).get("enabled")
            if enabled:
                assert cron in scheduled, (
                    f"{source} is enabled with cron {cron!r} and the workflow never "
                    f"fires it, so it would only ever refresh by hand"
                )


class TestEveryStepReadsTheResolvedSource:
    def test_no_step_still_falls_back_to_a_hardcoded_source(self) -> None:
        """The literal defect, asserted against the file.

        Anything of the form `inputs.source || '...'` is the bug: it is empty
        on a schedule and silently becomes the fallback.
        """
        text = WORKFLOW.read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in text.splitlines()
            if "inputs.source" in line and "||" in line and not line.strip().startswith("#")
        ]
        assert not offenders, offenders

    def test_the_resolver_runs_before_anything_provider_specific(self, workflow: dict) -> None:
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        resolver = names.index("Resolve which source to refresh")
        for provider_step in (
            "Retrieve the Transfermarkt dataset",
            "Retrieve FootyStats data",
            "Load and verify",
        ):
            assert names.index(provider_step) > resolver

    def test_transfermarkt_retrieval_is_gated_on_the_resolved_source(self, workflow: dict) -> None:
        for name in ("Retrieve the Transfermarkt dataset", "Profile the Transfermarkt dataset"):
            condition = " ".join(str(_step(workflow, name)["if"]).split())
            assert "steps.resolve_source.outputs.source == 'transfermarkt'" in condition

    def test_footystats_ingestion_is_gated_on_the_resolved_source(self, workflow: dict) -> None:
        """The half of the bug that cost real API calls.

        The fetch was gated on the key existing, not on the source, so a
        Sunday Transfermarkt run fetched FootyStats too.
        """
        condition = " ".join(str(_step(workflow, "Retrieve FootyStats data")["if"]).split())
        assert "steps.resolve_source.outputs.source == 'footystats'" in condition

    def test_the_load_passes_the_resolved_source(self, workflow: dict) -> None:
        run = _step(workflow, "Load and verify")["run"]
        assert '--source "${{ steps.resolve_source.outputs.source }}"' in run

    def test_the_coverage_report_uses_the_same_source_as_the_load(self, workflow: dict) -> None:
        run = _step(workflow, "Measure what the loaded data can produce")["run"]
        assert "${{ steps.resolve_source.outputs.source }}" in run

    def test_the_summary_reports_the_source_that_actually_ran(self, workflow: dict) -> None:
        run = _step(workflow, "Summarise the run")["run"]
        assert "${{ steps.resolve_source.outputs.source }}" in run


class TestIdentityResolutionRunsOnEveryRefresh:
    """Section 2 of the brief: the pipeline maintains its own cross-source links.

    A load purges the source it is replacing, which takes that source's bridge
    rows with it. Without this step a merged player comes apart on every
    refresh and stays apart until somebody notices.
    """

    def test_the_pipeline_resolves_identities(self, workflow: dict) -> None:
        run = _step(workflow, "Resolve identities across providers")["run"]
        assert "pipelines.identity_resolution.resolve" in run
        assert "--apply" in run

    def test_it_runs_after_the_load_and_before_everything_downstream(self, workflow: dict) -> None:
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        order = {
            "load": names.index("Load and verify"),
            "identity": names.index("Resolve identities across providers"),
            "prune": names.index("Drop market history nothing can reach"),
            "quality": names.index("Record the quality report"),
            "validation": names.index("Recompute sample players independently"),
            "publish": names.index("Publish the refreshed data to the live site"),
        }
        assert (
            order["load"]
            < order["identity"]
            < order["prune"]
            < order["quality"]
            < order["validation"]
            < order["publish"]
        ), order

    def test_it_only_runs_when_the_load_actually_succeeded(self, workflow: dict) -> None:
        step = _step(workflow, "Resolve identities across providers")
        assert "steps.load.outcome == 'success'" in str(step["if"])

    def test_a_failure_to_resolve_does_not_block_publication(self, workflow: dict) -> None:
        """Unmatched providers is a degraded site; not publishing is a stale one.

        The load already verified inside its own transaction, so the data is
        sound. Letting resolution failure stop the analytics reload would keep
        correct data off the site to punish a separate problem.
        """
        step = _step(workflow, "Resolve identities across providers")
        assert step.get("continue-on-error") is True
