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
        for cron, (source, _mode) in cron_map(config).items():
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

    def test_a_failure_to_resolve_blocks_publication(self, workflow: dict) -> None:
        """A reversed decision, and the reasoning that was wrong.

        The step was `continue-on-error: true`, on the argument that unmatched
        players are an ordinary outcome and a "failing" resolution step should
        not keep a good load off the site. The first half is true; the second
        does not follow. The process failing and the matching being imperfect
        are different events, and they share an exit code only if nobody
        separates them.

        They are separated at the source: `resolve.py` exits 0 with matched,
        ambiguous and unmatched counts in its summary. A non-zero exit means
        the process itself failed, which leaves the two providers unjoined -
        and every market value, contract date and cross-source figure hangs off
        that join.
        """
        step = _step(workflow, "Resolve identities across providers")
        assert "continue-on-error" not in step, (
            "identity resolution is advisory again, so a refresh can publish a "
            "database where the two providers came apart"
        )

    def test_everything_downstream_requires_it(self, workflow: dict) -> None:
        for name in (
            "Drop market history nothing can reach",
            "Record the quality report",
            "Recompute sample players independently",
        ):
            condition = " ".join(str(_step(workflow, name)["if"]).split())
            assert "steps.identity.outcome" in condition, name

    def test_the_promotion_requires_it_too(self, workflow: dict) -> None:
        """The step that decides what readers see.

        Identity resolution is no longer the last gate before publication -
        promotion is - so this checks the gate that now matters.
        """
        condition = " ".join(str(_step(workflow, "Promote the staged dataset")["if"]).split())
        assert "steps.identity.outcome == 'success'" in condition
        for other in ("steps.load", "steps.quality", "steps.validation"):
            assert other in condition, other

    def test_publication_waits_for_the_promotion(self, workflow: dict) -> None:
        """Not for the load.

        The load now writes to staging, so a successful load means nothing has
        reached readers yet. Reloading the API before the promotion would
        publish the previous dataset's view over the new one's cache, which is
        worse than doing nothing.
        """
        condition = " ".join(
            str(_step(workflow, "Publish the refreshed data to the live site")["if"]).split()
        )
        assert condition == "steps.promote.outcome == 'success'"


class TestTheContinuationSchedule:
    """A refresh takes about fourteen hours of fetching; a job manages forty-five
    minutes. On the cadence cron alone that is three weeks per refresh, which
    publishes data older than the interval that produced it.
    """

    def test_the_hourly_cron_exists_and_is_claimed(self, workflow: dict, config: dict) -> None:
        triggers = workflow.get("on") or workflow.get(True)
        scheduled = {" ".join(entry["cron"].split()) for entry in triggers["schedule"]}
        assert "0 * * * *" in scheduled
        assert cron_map(config)["0 * * * *"] == ("footystats", "continue_only")

    def test_the_cadence_cron_may_start_a_generation(self, config: dict) -> None:
        assert cron_map(config)["0 4 * * 1,3,5"] == ("footystats", "start")

    def test_a_manual_run_may_start_one(self, config: dict) -> None:
        from pipelines.load.resolve_source import START, resolve_with_mode

        _, mode = resolve_with_mode(
            event_name="workflow_dispatch",
            schedule=None,
            input_source="footystats",
            config=config,
        )
        assert mode == START

    def test_the_gate_runs_before_the_fetch(self, workflow: dict) -> None:
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        assert names.index("Decide what this run should do") < names.index(
            "Retrieve FootyStats data"
        )

    def test_the_gate_runs_before_the_cache_rather_than_after_it(self, workflow: dict) -> None:
        """The ordering that made hourly continuation impossible.

        The gate used to read the filesystem, and a fresh runner has no
        generation directory until the cache is restored - so it saw nothing,
        answered NOOP, and the cache was never restored. The gate reads the
        database instead, decides first, and the cache is restored only when
        the answer needs local files.
        """
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        assert names.index("Decide what this run should do") < names.index(
            "Restore the refresh generation"
        )

    def test_the_cache_restores_the_generations_directory(self, workflow: dict) -> None:
        """It cached the retired flat snapshot layout, so nothing was ever
        resumable: every runner started with no generation state."""
        step = _step(workflow, "Restore the refresh generation")
        paths = str(step["with"]["path"])
        assert "data/raw/footystats/generations" in paths

    def test_the_fetch_is_gated_on_the_action_not_merely_on_proceeding(
        self, workflow: dict
    ) -> None:
        """A PUBLISH_READY run proceeds and must not fetch.

        Its generation's fetch is already finished; refetching would discard
        fourteen hours of API budget because a downstream step had a bad
        minute, which is the whole reason the action exists.
        """
        condition = " ".join(str(_step(workflow, "Retrieve FootyStats data")["if"]).split())
        # The *settled* action: the verify step's when it ran, the gate's
        # when it did not. A gate that said FETCH is stale once the restored
        # checkpoint proves the generation COMPLETE.
        assert "steps.action.outputs.action == 'FETCH'" in condition
        assert "steps.action.outputs.action == 'START_NEW'" in condition
        assert "steps.gate.outputs.action ==" not in condition
        assert "steps.gate.outputs.proceed" not in condition

    def test_concurrent_runs_are_queued_rather_than_cancelled(self, workflow: dict) -> None:
        """Cancelling a fetch mid-flight loses the progress it had not flushed."""
        concurrency = workflow["concurrency"]
        assert concurrency["cancel-in-progress"] is False
        assert concurrency["group"]


class TestTheGateDecision:
    def test_an_hourly_run_with_nothing_open_does_nothing(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from pipelines.footystats.gate import decide
        from pipelines.footystats.generations import GenerationStore
        from pipelines.load.resolve_source import CONTINUE_ONLY

        proceed, reason = decide(CONTINUE_ONLY, GenerationStore(root=tmp_path / "g"))
        assert proceed is False
        assert "nothing to continue" in reason

    def test_an_hourly_run_continues_an_open_generation(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from pipelines.footystats.gate import decide
        from pipelines.footystats.generations import GenerationStore
        from pipelines.load.resolve_source import CONTINUE_ONLY

        store = GenerationStore(root=tmp_path / "g")
        store.create()
        proceed, reason = decide(CONTINUE_ONLY, store)
        assert proceed is True
        assert "continuing generation" in reason

    def test_the_cadence_starts_one_when_none_is_open(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from pipelines.footystats.gate import decide
        from pipelines.footystats.generations import GenerationStore
        from pipelines.load.resolve_source import START

        proceed, reason = decide(START, GenerationStore(root=tmp_path / "g"))
        assert proceed is True
        assert "starting a new" in reason

    def test_the_cadence_does_not_start_a_second_one(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """A refresh still running on Wednesday is continued, not restarted."""
        from pipelines.footystats.gate import decide
        from pipelines.footystats.generations import GenerationStore
        from pipelines.load.resolve_source import START

        store = GenerationStore(root=tmp_path / "g")
        store.create()
        proceed, reason = decide(START, store)
        assert proceed is True
        assert "rather than starting another" in reason

    def test_a_publication_ready_generation_is_retried_rather_than_refetched(
        self,
        tmp_path,  # type: ignore[no-untyped-def]
    ) -> None:
        """The expensive gap this closes.

        A generation whose fetch finished but whose publication failed used to
        be indistinguishable from no generation at all, so the next cadence run
        started a fresh one and refetched every player.
        """
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.load.resolve_source import START

        decision = decide_from_state(START, [("20260907T040000Z", "COMPLETE")])
        assert decision.action is Action.PUBLISH_READY
        assert not decision.action.fetches, "nothing to refetch"
        assert decision.action.needs_local_state, "but its files are still needed"
        assert decision.generation_id == "20260907T040000Z"

    def test_a_broken_generation_state_stops_the_run(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        """Rather than guessing between two open generations."""
        from pipelines.footystats.gate import decide
        from pipelines.footystats.generations import GenerationStore
        from pipelines.load.resolve_source import CONTINUE_ONLY

        store = GenerationStore(root=tmp_path / "g")
        first = store.create()
        (store.root / "20200101T000000Z").mkdir(parents=True)
        (store.root / "20200101T000000Z" / "metadata.json").write_text(
            first.metadata_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

        proceed, reason = decide(CONTINUE_ONLY, store)
        assert proceed is False
        assert "manual intervention" in reason


class TestTheCacheIsSavedRightAfterTheFetch:
    """Sections 1, 2, 3 and 6 of the brief, asserted against pipeline.yml.

    The cache used to be one `actions/cache` step: restore at its position,
    save in a post-step at the end of the job. A START_NEW run restored
    nothing, so the post-step never registered and the generation was lost;
    and the post-step ran after every failure-prone step, so a bad minute
    downstream could lose the hour before it.
    """

    def test_restore_and_save_are_separate_actions(self, workflow: dict) -> None:
        restore = _step(workflow, "Restore the refresh generation")
        save = _step(workflow, "Save the refresh generation")
        assert restore["uses"].startswith("actions/cache/restore@")
        assert save["uses"].startswith("actions/cache/save@")
        assert not any(
            str(s.get("uses", "")).startswith("actions/cache@") for s in _steps(workflow)
        ), "the combined action would save in a post-step, after everything that can fail"

    def test_the_save_follows_the_fetch_immediately(self, workflow: dict) -> None:
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        fetch = names.index("Retrieve FootyStats data")
        save = names.index("Save the refresh generation")
        assert save == fetch + 1
        for later in (
            "Seed staging from current production",
            "Load and verify",
            "Resolve identities across providers",
            "Record the quality report",
            "Recompute sample players independently",
            "Promote the staged dataset",
        ):
            assert names.index(later) > save, f"{later} runs before the cache is saved"

    def test_the_save_runs_for_start_new_and_for_a_failed_fetch(self, workflow: dict) -> None:
        """`always()` so a failed fetch step still saves what it wrote; keyed
        by the fetch's own outputs so a START_NEW run, whose generation did
        not exist when the gate ran, is saved too."""
        save = _step(workflow, "Save the refresh generation")
        condition = " ".join(str(save["if"]).split())
        assert "always()" in condition
        assert "steps.fetch.outputs.generation_id != ''" in condition
        assert "steps.fetch.outputs.generation_id" in str(save["with"]["key"])
        assert "steps.fetch.outputs.checkpoint_revision" in str(save["with"]["key"])
        assert "steps.gate.outputs.generation_id" not in str(save["with"]["key"])

    def test_the_restore_never_falls_back_to_another_generation(self, workflow: dict) -> None:
        restore = _step(workflow, "Restore the refresh generation")
        restore_keys = [
            k.strip() for k in str(restore["with"]["restore-keys"]).splitlines() if k.strip()
        ]
        assert restore_keys == ["footystats-gen-${{ steps.gate.outputs.generation_id }}-"]
        assert "footystats-gen-\n" not in str(restore["with"]["restore-keys"])
        assert not any(k == "footystats-gen-" for k in restore_keys)

    def test_the_restore_asks_for_a_key_that_cannot_exist(self, workflow: dict) -> None:
        """So that only the prefix matches and the newest checkpoint wins.

        Asking for the database's revision exactly was the bug: with `-0004`
        and `-0005` both saved and the database still saying 4, the exact hit
        won and checkpoint 5 was silently discarded.
        """
        restore = _step(workflow, "Restore the refresh generation")
        key = str(restore["with"]["key"])
        assert "restore-${{ github.run_id }}" in key
        assert "expected_revision" not in key

    def test_the_candidate_pipeline_names_the_source_and_the_refresh(self, workflow: dict) -> None:
        """Rows written as `all` can never be flipped to PUBLISHED; rows
        without `--candidate` read as production's."""
        for name in ("Load and verify", "Record the quality report"):
            run = _step(workflow, name)["run"]
            assert "--candidate" in run, name
            assert "--refresh-id" in run, name
            assert "steps.generation.outputs.refresh_id" in run, name
        quality = _step(workflow, "Record the quality report")["run"]
        assert '--source "${{ steps.resolve_source.outputs.source }}"' in quality
        assert "--refresh-id" in _step(workflow, "Promote the staged dataset")["run"]

    def test_the_refresh_is_named_for_every_provider(self, workflow: dict) -> None:
        step = _step(workflow, "Name the refresh this run publishes")
        assert "refresh_id=" in step["run"]
        assert "github.run_id" in step["run"], "Transfermarkt refreshes are named by the run"
        assert step["if"] == "steps.preflight.outputs.database == 'true'"

    def test_the_gate_runs_in_production_mode(self, workflow: dict) -> None:
        """Which is what makes it fail closed without its database."""
        gate = _step(workflow, "Decide what this run should do")
        assert gate["env"]["APP_ENV"] == "production"
        assert "ALLOW_LOCAL_GATE_FALLBACK" not in gate.get("env", {})
        text = WORKFLOW.read_text(encoding="utf-8")
        assert "ALLOW_LOCAL_GATE_FALLBACK" not in text

    def test_the_verification_is_a_step_that_can_fail(self, workflow: dict) -> None:
        verify = _step(workflow, "Check the restored generation is the expected one")
        assert verify["id"] == "verify"
        assert "--verify-restored" in verify["run"]
        assert "--expected-revision" in verify["run"]
        assert "continue-on-error" not in verify

    def test_the_fetch_is_gated_on_the_verification(self, workflow: dict) -> None:
        condition = " ".join(str(_step(workflow, "Retrieve FootyStats data")["if"]).split())
        assert "steps.verify.outcome == 'success'" in condition
        assert "--expect-generation" in _step(workflow, "Retrieve FootyStats data")["run"]

    def test_the_candidate_pipeline_names_the_generation(self, workflow: dict) -> None:
        """Section 4: no step chooses "the newest"; every step is told which."""
        for name in ("Load and verify", "Record the quality report", "Promote the staged dataset"):
            assert "--generation-id" in _step(workflow, name)["run"], name
            assert "steps.generation.outputs.id" in _step(workflow, name)["run"], name

    def test_validated_sits_between_validation_and_promotion(self, workflow: dict) -> None:
        names = [s.get("name") or s.get("uses") for s in _steps(workflow)]
        validation = names.index("Recompute sample players independently")
        validated = names.index("Mark the generation VALIDATED")
        promote = names.index("Promote the staged dataset")
        assert validation < validated < promote
        step = _step(workflow, "Mark the generation VALIDATED")
        assert "--mark-validated" in step["run"]
        condition = " ".join(str(step["if"]).split())
        for required in ("steps.load", "steps.identity", "steps.quality", "steps.validation"):
            assert f"{required}.outcome == 'success'" in condition

    def test_promotion_requires_validated_for_footystats(self, workflow: dict) -> None:
        condition = " ".join(str(_step(workflow, "Promote the staged dataset")["if"]).split())
        assert "steps.validated.outcome == 'success'" in condition
