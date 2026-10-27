"""The scheduled pipeline's configuration.

Specification section 22 requires the refresh cadence to be configurable, and
section 23 requires that a failed validation publishes nothing.

GitHub will not read a cron from a config file — the schedule must be a literal
in the workflow. So the same cadence is written twice, and two copies of a fact
drift. These tests make the drift fail rather than go unnoticed.
"""

from __future__ import annotations

from itertools import pairwise
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


class TestNothingFiresOnTheHour:
    """Round numbers are what someone tidies a cron back to.

    Measured over 393 hours to 20 October: 88 of the ~393 fires an hourly cron
    asks for arrived - 22%, median gap 4.3 hours, and exactly one run in 88
    started at :00. Not our doing: no run overlapped the next trigger and one
    in 88 was cancelled. GitHub's documentation names the top of the hour as a
    high load time and says queued jobs may be dropped under enough of it.

    Every cron here was at :00. Moving them off it is the documented
    mitigation, and it is the kind of change that looks like untidiness to the
    next reader.
    """

    def test_no_schedule_fires_at_minute_zero(self, workflow: dict) -> None:
        for entry in workflow["triggers"]["schedule"]:
            minute = entry["cron"].split()[0]
            assert minute != "0", f"{entry['cron']} is back on the hour"

    def test_nor_at_the_minutes_the_documentation_suggests(self, workflow: dict) -> None:
        """:15 and :20 are the examples GitHub gives, so they are where the
        next wave of workflows moved to. Being off the hour is the point;
        being off the obvious alternative costs nothing."""
        for entry in workflow["triggers"]["schedule"]:
            assert entry["cron"].split()[0] not in {"15", "20"}, entry["cron"]

    def test_the_cadence_and_the_continuation_do_not_collide(self, workflow: dict) -> None:
        """Both firing in the same minute queues one behind the other for no
        benefit, and the queue is where fires are dropped."""
        minutes = [entry["cron"].split()[0] for entry in workflow["triggers"]["schedule"]]
        assert len(set(minutes)) == len(minutes), minutes


class TestTheCadenceGetsMoreThanOneChance:
    """It is the only trigger that may begin a generation.

    `pipelines.load.resolve_source` maps a cron literal to a mode: the cadence
    may START, the hourly continuation may only CONTINUE. That separation is
    right - an hourly cron allowed to start would begin a sixteen-hour refresh
    every hour - but it made one fire the only way a refresh ever begins.
    Dropped at the measured rate, a refresh did not run late; it did not run
    until the next Monday, Wednesday or Friday.
    """

    def test_the_footystats_cadence_fires_several_times_a_day(self, competitions: dict) -> None:
        hours = competitions["refresh"]["footystats"]["cron"].split()[1]
        assert "," in hours, "one attempt is a single point of failure"
        assert len(hours.split(",")) >= 3

    def test_the_attempts_are_spread_rather_than_consecutive(self, competitions: dict) -> None:
        """Back-to-back retries meet the same busy period they just lost to."""
        field = competitions["refresh"]["footystats"]["cron"].split()[1]
        hours = sorted(int(hour) for hour in field.split(","))
        gaps = [later - earlier for earlier, later in pairwise(hours)]
        assert all(gap >= 2 for gap in gaps), hours

    def test_only_the_cadence_may_start_one(self, competitions: dict) -> None:
        """The guard that makes the extra attempts safe to add: a continuation
        cron that could start would begin a refresh every hour."""
        from pipelines.load.resolve_source import load_config, resolve_with_mode

        config = load_config()
        footystats = competitions["refresh"]["footystats"]

        _, cadence_mode = resolve_with_mode(
            event_name="schedule", schedule=footystats["cron"], input_source=None, config=config
        )
        _, continuation_mode = resolve_with_mode(
            event_name="schedule",
            schedule=footystats["continuation_cron"],
            input_source=None,
            config=config,
        )
        assert cadence_mode == "start"
        assert continuation_mode == "continue_only"


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
        configured = {
            cron
            for entry in competitions["refresh"].values()
            # A source may declare two: `cron` is the cadence, when a new
            # refresh generation may begin, and `continuation_cron` is when an
            # unfinished one may carry on.
            for key in ("cron", "continuation_cron")
            if (cron := entry.get(key))
        }
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

    def test_every_exclusion_identifies_the_season_it_refers_to(self, competitions: dict) -> None:
        """A reason without a season is not actionable.

        There are two kinds here and they are identified differently. One is
        excluded because the catalogue has nothing current, so it names the
        newest season that does exist (`latest_season`). The other has a
        perfectly current season that this subscription does not carry, so it
        names that season and its id - and can be moved back verbatim once the
        league is chosen on the account. Requiring `latest_season` of both, as
        this test once did, would have forced the second kind to claim its
        season was stale, which is the one thing it is not.
        """
        for entry in competitions.get("excluded") or []:
            stale = bool(entry.get("latest_season"))
            unsubscribed = bool(entry.get("season_id")) and bool(entry.get("season"))
            assert stale or unsubscribed, entry

    def test_an_unsubscribed_exclusion_is_not_also_listed_for_ingest(
        self, competitions: dict
    ) -> None:
        """The two lists contradicting each other is how this started.

        A competition named in both would be asked for and refused on every
        run, and a refused roster leaves the generation permanently incomplete
        - so nothing is ever published, hourly, until somebody reads the log.
        """
        ingested = {str(e["season_id"]) for e in competitions["footystats"]}
        for entry in competitions.get("excluded") or []:
            season_id = entry.get("season_id") or entry.get("latest_season_id")
            assert str(season_id) not in ingested, entry

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


class TestNothingIsAskedBeforeThereIsSomewhereToAsk:
    """The run must not fail for the absence of a thing it never checked for.

    The gate reads `fact_refresh_generation` to decide what the run should do,
    and it fails closed when it cannot reach the database. That is right: a
    fresh runner that decided from its empty disk would start a second
    fourteen-hour fetch beside the one already in progress.

    What was wrong was the order. The gate ran before the preflight that asks
    whether a database is configured at all, so with no `POSTGRES_*` secrets
    every FootyStats-scheduled run raised and went red - thirty-nine of forty
    - while the Transfermarkt ones skipped cleanly and passed. A scheduled job
    that is red every day is a job nobody reads on the day it matters, which
    is the outcome the preflight's own comment says it exists to prevent.
    """

    @staticmethod
    def steps(workflow: dict) -> list[dict]:
        job = next(iter(workflow["jobs"].values()))
        return job["steps"]

    def position_of(self, workflow: dict, name: str) -> int:
        for index, step in enumerate(self.steps(workflow)):
            if step.get("name") == name:
                return index
        raise AssertionError(f"no step named {name!r}")

    def test_the_preflight_runs_before_the_gate(self, workflow: dict) -> None:
        preflight = self.position_of(workflow, "Check the pipeline is configured")
        gate = self.position_of(workflow, "Decide what this run should do")
        assert preflight < gate, (
            "the gate reads the database before anything establishes there is one"
        )

    def test_the_gate_waits_for_the_preflight(self, workflow: dict) -> None:
        gate = self.steps(workflow)[self.position_of(workflow, "Decide what this run should do")]
        condition = " ".join(str(gate.get("if", "")).split())
        assert "steps.preflight.outputs.database == 'true'" in condition, (
            "the gate runs whether or not a database is configured"
        )

    def test_every_step_that_needs_the_database_waits_for_it(self, workflow: dict) -> None:
        # The gate was the only one that did not, which is why it was the only
        # one that failed. This keeps the next one from being added below it.
        needs_database = {
            "Check the production configuration",
            "Apply migrations",
            "Seed staging from current production",
        }
        for step in self.steps(workflow):
            if step.get("name") in needs_database:
                condition = " ".join(str(step.get("if", "")).split())
                assert "steps.preflight.outputs.database == 'true'" in condition, (
                    f"{step['name']} would run with no database configured"
                )

    def test_an_unconfigured_run_says_so_rather_than_failing(self, workflow: dict) -> None:
        report = self.position_of(workflow, "Report that there is nothing to refresh")
        gate = self.position_of(workflow, "Decide what this run should do")
        assert report < gate, "the explanation arrives after the step that made it necessary"


class TestTheConnectionTravelsWhole:
    """A managed database is reached by its URL, not by five pieces of one.

    The settings object has preferred `DATABASE_URL` all along, and Render
    passes one. The pipeline assembled its own from five secrets instead, and
    an assembled one has nowhere to put `sslmode` - which Neon requires and
    refuses the connection without:

        ERROR: connection is insecure (try using `sslmode=require`)

    So the five-part path could not have worked against the deployed database
    whatever was in the secrets. Both forms are passed now, and the settings
    object decides, exactly as it does for the service.
    """

    @staticmethod
    def steps_with_credentials(workflow: dict) -> list[dict]:
        job = next(iter(workflow["jobs"].values()))
        return [s for s in job["steps"] if "POSTGRES_HOST" in (s.get("env") or {})]

    def test_every_step_that_takes_the_parts_also_takes_the_url(self, workflow: dict) -> None:
        steps = self.steps_with_credentials(workflow)
        assert steps, "no step reads the database credentials at all"
        missing = [s["name"] for s in steps if "DATABASE_URL" not in s["env"]]
        assert missing == [], f"these take the parts but not the whole: {missing}"

    def test_the_preflight_accepts_either_form(self, workflow: dict) -> None:
        job = next(iter(workflow["jobs"].values()))
        preflight = next(s for s in job["steps"] if s.get("id") == "preflight")
        assert "DATABASE_URL" in (preflight.get("env") or {})
        assert "DATABASE_URL" in preflight["run"], (
            "the preflight would report no database for a deployment that has one"
        )

    def test_the_settings_still_prefer_the_url(self) -> None:
        # The workflow passes both, so which wins is decided here. If this
        # stopped preferring the URL, the sslmode would be dropped again and
        # the connection would be refused - with a message about the password.
        from app.core.config import Settings

        settings = Settings(
            database_url="postgresql://whole:url@example.neon.tech/db?sslmode=require",
            postgres_host="ignored.example",
            postgres_user="ignored",
        )
        assert "example.neon.tech" in settings.sqlalchemy_url
        assert "sslmode=require" in settings.sqlalchemy_url
        assert "ignored" not in settings.sqlalchemy_url


class TestTheWorkflowParsesWhereItHasTo:
    """`yaml.safe_load` is not the parser that matters.

    A duplicate key is legal YAML - the last one wins - so `safe_load` reads a
    workflow with two `DATABASE_URL` entries without complaint, and so does
    every test above. GitHub refuses it outright:

        failed to parse workflow: 'DATABASE_URL' is already defined

    which arrives as an HTTP 422 on dispatch, long after CI has gone green. So
    this reads the file strictly rather than trusting the loader that let it
    through.
    """

    def test_no_mapping_defines_the_same_key_twice(self) -> None:
        import yaml

        class Strict(yaml.SafeLoader):
            pass

        def no_duplicates(loader: yaml.Loader, node: yaml.Node, deep: bool = False) -> dict:
            seen: set = set()
            for key_node, _ in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in seen:
                    raise AssertionError(
                        f"{key!r} is defined twice at line {key_node.start_mark.line + 1}; "
                        "GitHub refuses the workflow, though yaml.safe_load does not"
                    )
                seen.add(key)
            return loader.construct_mapping(node, deep)

        Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicates)

        for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
            # `Strict` subclasses SafeLoader and only narrows it, so this
            # constructs nothing a safe load would not.
            yaml.load(workflow.read_text(encoding="utf-8"), Loader=Strict)  # noqa: S506


class TestAnOverrunLeavesEvidence:
    """A step killed by the timeout must not take its log with it.

    Eight steps pipe their output through `tee`, and a pipe makes Python
    buffer stdout. The first production-scale identity resolution ran for
    forty-five minutes, was killed by the job timeout, and uploaded an empty
    `pipeline-identity.log` - so the one question worth asking, where the time
    went, had no evidence at all.
    """

    def test_python_output_is_unbuffered(self, workflow: dict) -> None:
        job = next(iter(workflow["jobs"].values()))
        assert (job.get("env") or {}).get("PYTHONUNBUFFERED") == "1", (
            "a step killed by the timeout will upload an empty log"
        )

    def test_the_steps_that_pipe_are_the_reason(self, workflow: dict) -> None:
        # If nothing piped any more, the setting would be harmless rather than
        # necessary, and this test should be deleted rather than kept passing.
        job = next(iter(workflow["jobs"].values()))
        piped = [s for s in job["steps"] if "| tee" in str(s.get("run", ""))]
        assert piped, "nothing pipes its output; PYTHONUNBUFFERED is no longer load-bearing"


class TestTheCadenceIsWeekly:
    """One generation a week, on a day of the week rather than of the month.

    The number moved twice for two different reasons, and the guard has to
    follow the second one. Mondays, Wednesdays and Fridays was chosen when a
    generation fetched 8,862 players; reading every page of the roster made
    that 28,311, or ~950 Actions minutes of waiting on a rate limiter per
    generation, so the 2,000 a month a PRIVATE repository gets ran out on 22
    October and the cadence was cut to the 1st and the 15th to fit.

    The repository went public on 27 October 2026. Actions is free for public
    repositories, so that allowance no longer binds and the cadence is back to
    a question about football: a round of matches a week.
    """

    def test_it_runs_on_a_day_of_the_week_rather_than_days_of_the_month(
        self, competitions: dict
    ) -> None:
        fields = competitions["refresh"]["footystats"]["cron"].split()
        assert fields[4] != "*", "no day-of-week is set, so this is not a weekly cadence"
        assert len(fields[4].split(",")) == 1, f"{fields[4]!r} is more than one day a week"

    def test_the_day_of_month_field_stays_unrestricted(self, competitions: dict) -> None:
        """The same trap as before, now facing the other way.

        Cron treats a restricted day-of-month and a restricted day-of-week as
        ALTERNATIVES, not as a conjunction. While the cadence was the 1st and
        the 15th, the day-of-WEEK field had to stay `*`. Now that it is a
        weekday, the day-of-MONTH field is the one that must: `17 4 1,15 * 1`
        fires on the 1st, the 15th *and* every Monday.
        """
        fields = competitions["refresh"]["footystats"]["cron"].split()
        assert fields[2] == "*", f"day-of-month is {fields[2]!r}, so this fires on those days too"

    def test_it_starts_after_the_transfermarkt_refresh(self, competitions: dict) -> None:
        """Why Monday and not some other day.

        Identity resolution matches FootyStats players against Transfermarkt,
        which refreshes on Sunday. Starting the day after means the market data
        underneath a generation is a day old rather than nearly a week.
        """
        footystats_day = int(competitions["refresh"]["footystats"]["cron"].split()[4])
        transfermarkt_day = int(competitions["refresh"]["transfermarkt"]["cron"].split()[4])
        assert footystats_day == (transfermarkt_day + 1) % 7, (
            f"footystats runs on day {footystats_day} and transfermarkt on {transfermarkt_day}"
        )
