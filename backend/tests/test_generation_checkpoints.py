"""The cache is the only copy of fourteen hours of fetching. These are the
tests that say the pipeline cannot lose it, mistake it, or resume the wrong one.

WHAT WAS WRONG
==============

Three things, and the first was the expensive one.

A START_NEW run never restored a cache - there was nothing to restore - so the
`actions/cache` post-step never registered, and the generation it created and
fetched for forty-five minutes was never saved. The database said IN_PROGRESS;
no runner had the files. Every first run of every refresh was lost.

The restore keys fell back to `footystats-gen-`, any generation at all, so
"expected G5, G5 missing" produced G4 - and the check that noticed only
warned. A fetch then ran against G4's files under G5's name.

And the cache key was immutable while the generation was not: a generation
grows over nineteen runs, and one key cannot hold nineteen states.

WHAT THESE TESTS SIMULATE
=========================

The workflow, without GitHub. `FakeCache` stands in for `actions/cache`: it
saves a generation directory under a key and restores the newest key with a
prefix, which is what GitHub does. `FakeDatabase` stands in for
`fact_refresh_generation`: status and checkpoint revision per generation. The
gate, the verifier, the store and the ingest are the real ones.
"""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass, field
from typing import Any

import pytest
from pipelines.footystats.gate import (
    Action,
    Verdict,
    decide_from_state,
    verify_local_state,
)
from pipelines.footystats.generations import (
    GenerationError,
    GenerationStatus,
    GenerationStore,
)
from pipelines.footystats.ingest import ingest_competition

# ---------------------------------------------------------------------------
# Stand-ins
# ---------------------------------------------------------------------------


class RosterProvider:
    """A roster and a per-player fetch, with the calls counted."""

    def __init__(self, players: list[str]) -> None:
        self.players = players
        self.fetched: list[str] = []

    def _roster(self, season_id: str) -> list[dict[str, object]]:
        return [{"id": p, "club_team_id": 1} for p in self.players]

    def _get(self, path: str, **params: object) -> object:
        if path == "/league-teams":
            return {"data": [{"id": 1, "name": "A Club"}]}
        player_id = str(params.get("player_id"))
        self.fetched.append(player_id)
        return {"data": {"id": player_id}}


@dataclass
class FakeCache:
    """`actions/cache`, reduced to what matters: immutable keys, prefix restore
    to the newest key, and nothing else."""

    store: dict[str, pathlib.Path] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def save(self, key: str, directory: pathlib.Path, into: pathlib.Path) -> None:
        if key in self.store:
            # GitHub refuses to overwrite. A pipeline that relied on
            # overwriting would silently keep the first checkpoint forever.
            raise RuntimeError(f"cache key {key!r} already exists and is immutable")
        target = into / key
        shutil.copytree(directory, target)
        self.store[key] = target
        self.order.append(key)

    def restore(self, exact: str, prefix: str, into: pathlib.Path) -> str | None:
        """Exact key first, else the newest key with the prefix, else nothing."""
        if exact in self.store:
            chosen = exact
        else:
            matches = [k for k in self.order if k.startswith(prefix)]
            if not matches:
                return None
            chosen = matches[-1]
        if into.exists():
            shutil.rmtree(into)
        shutil.copytree(self.store[chosen], into)
        return chosen


@dataclass
class FakeDatabase:
    """`fact_refresh_generation`, reduced to status and revision."""

    rows: dict[str, tuple[str, int]] = field(default_factory=dict)

    def record(self, store: GenerationStore) -> None:
        for generation in store.all():
            self.rows[generation.generation_id] = (
                generation.status.value,
                generation.metadata.checkpoint_revision,
            )

    def live(self) -> list[tuple[str, str]]:
        return [
            (gid, status)
            for gid, (status, _) in sorted(self.rows.items())
            if status in {"IN_PROGRESS", "COMPLETE", "VALIDATED"}
        ]

    def revision(self, generation_id: str) -> int | None:
        row = self.rows.get(generation_id)
        return row[1] if row else None


class BudgetOf:
    """`Deadline`, expiring after a number of player fetches rather than
    minutes. What a forty-five-minute run looks like to the ingest."""

    def __init__(self, provider: RosterProvider, fetches: int | None) -> None:
        self.provider = provider
        self.stop_at = None if fetches is None else len(provider.fetched) + fetches
        self.limit_seconds = None if fetches is None else 1.0

    def expired(self) -> bool:
        return self.stop_at is not None and len(self.provider.fetched) >= self.stop_at


def key_for(generation_id: str, revision: int) -> str:
    return f"footystats-gen-{generation_id}-{revision:04d}"


def prefix_for(generation_id: str) -> str:
    return f"footystats-gen-{generation_id}-"


@dataclass
class Runner:
    """One workflow run, on a fresh disk."""

    disk: pathlib.Path
    cache: FakeCache
    db: FakeDatabase
    cache_root: pathlib.Path
    provider: RosterProvider
    mode: str

    @property
    def generations(self) -> pathlib.Path:
        return self.disk / "generations"

    def run(self, *, at: Any, budget: int | None = None) -> dict[str, Any]:
        """The steps, in the workflow's order. Returns what each one did."""
        from pipelines.footystats.generations import new_generation_id

        outcome: dict[str, Any] = {}

        # 5. gate - from the database, never the disk
        decision = decide_from_state(self.mode, self.db.live())
        outcome["action"] = decision.action
        if not decision.proceed:
            return outcome

        # 7. restore - only within the expected generation
        if decision.action.needs_local_state:
            assert decision.generation_id is not None
            expected_rev = self.db.revision(decision.generation_id) or 0
            outcome["restored"] = self.cache.restore(
                key_for(decision.generation_id, expected_rev),
                prefix_for(decision.generation_id),
                self.generations,
            )
            # 8. verify - fatal
            verdict = verify_local_state(
                GenerationStore(root=self.generations),
                decision.generation_id,
                expected_revision=expected_rev,
            )
            outcome["verify"] = verdict
            if not verdict.ok:
                outcome["stopped"] = verdict.reason
                return outcome

        if not decision.action.fetches:
            return outcome

        # 16. fetch
        store = GenerationStore(root=self.generations)
        if decision.action is Action.FETCH:
            generation = store.resolve(resume=True, expected_id=decision.generation_id)
        else:
            self.generations.mkdir(parents=True, exist_ok=True)
            generation = store.resolve(resume=True, now=at)
            assert generation.generation_id == new_generation_id(at)
        result = ingest_competition(
            self.provider,
            "16504",
            "Test",
            resume=True,
            deadline=BudgetOf(self.provider, budget),  # type: ignore[arg-type]
            generation=generation,
        )
        if result.complete:
            generation.mark_competition_complete("16504")
        generation.refresh_counts(completed=result.fetched + result.skipped, failed=[])
        generation.evaluate_completeness()
        if generation.metadata.complete:
            generation.set_status(GenerationStatus.COMPLETE)
        revision = generation.checkpoint()
        outcome["generation_id"] = generation.generation_id
        outcome["revision"] = revision
        outcome["complete"] = generation.metadata.complete

        # 17. save - immediately, keyed by what the fetch actually did
        self.cache.save(
            key_for(generation.generation_id, revision), self.generations, self.cache_root
        )
        self.db.record(store)
        outcome["saved"] = key_for(generation.generation_id, revision)
        return outcome


@pytest.fixture
def world(tmp_path: pathlib.Path) -> dict[str, Any]:
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    return {"cache": FakeCache(), "db": FakeDatabase(), "cache_root": cache_root, "tmp": tmp_path}


def fresh_runner(world: dict[str, Any], name: str, provider: RosterProvider, mode: str) -> Runner:
    """A new runner has a new, empty disk. That is the whole premise."""
    disk = world["tmp"] / name
    disk.mkdir()
    return Runner(
        disk=disk,
        cache=world["cache"],
        db=world["db"],
        cache_root=world["cache_root"],
        provider=provider,
        mode=mode,
    )


def at(day: int, hour: int = 4) -> Any:
    import datetime as dt

    return dt.datetime(2026, 9, day, hour, 0, 0, tzinfo=dt.UTC)


# ---------------------------------------------------------------------------
# The whole lifecycle, run by run
# ---------------------------------------------------------------------------


class TestTheCacheSurvivesTheLifecycle:
    """Section 16 of the brief, as a simulation."""

    def test_run_one_start_new_saves_a_cache_nothing_restored(self, world: dict[str, Any]) -> None:
        """THE run that used to lose everything.

        Nothing to restore, so `actions/cache` never registered a save. The
        save now keys off the fetch's own outputs and runs regardless.
        """
        provider = RosterProvider([str(i) for i in range(1, 101)])
        run1 = fresh_runner(world, "runner1", provider, "start").run(at=at(1), budget=40)

        assert run1["action"] is Action.START_NEW
        assert "restored" not in run1, "a new generation has nothing to restore"
        assert run1["revision"] == 1
        assert run1["saved"] in world["cache"].store, "and it was saved anyway"
        assert world["db"].rows[run1["generation_id"]] == ("IN_PROGRESS", 1)

    def test_run_two_restores_verifies_resumes_and_saves_a_new_key(
        self, world: dict[str, Any]
    ) -> None:
        provider = RosterProvider([str(i) for i in range(1, 101)])
        run1 = fresh_runner(world, "runner1", provider, "start").run(at=at(1), budget=40)
        run2 = fresh_runner(world, "runner2", provider, "continue_only").run(at=at(1, 5), budget=40)

        assert run2["action"] is Action.FETCH
        assert run2["restored"] == run1["saved"], "the newest checkpoint of the same generation"
        assert run2["verify"].ok
        assert run2["generation_id"] == run1["generation_id"], "resumed, not restarted"
        assert run2["revision"] == 2
        assert run2["saved"] != run1["saved"], "an immutable key cannot be reused"
        # 40 fetched in run one, 40 more in run two: nothing refetched.
        assert len(provider.fetched) == 80

    def test_run_three_completes_and_is_published_and_run_four_starts_fresh(
        self, world: dict[str, Any]
    ) -> None:
        provider = RosterProvider([str(i) for i in range(1, 101)])
        r1 = fresh_runner(world, "runner1", provider, "start")
        run1 = r1.run(at=at(1), budget=40)
        fresh_runner(world, "runner2", provider, "continue_only").run(at=at(1, 5), budget=40)
        run3 = fresh_runner(world, "runner3", provider, "continue_only").run(at=at(1, 6))

        assert run3["complete"] is True
        assert world["db"].rows[run1["generation_id"]] == ("COMPLETE", 3)
        assert len(provider.fetched) == 100, "every player fetched exactly once"

        # The candidate pipeline: validated, then promoted. Simulated at the
        # database level; the real transaction is tested in
        # test_atomic_promotion.
        gid = run1["generation_id"]
        world["db"].rows[gid] = ("VALIDATED", 3)
        assert decide_from_state("continue_only", world["db"].live()).action is Action.PUBLISH_READY
        world["db"].rows[gid] = ("PUBLISHED", 3)

        # Run four: the cadence fires. Nothing is live, so a new generation.
        run4 = fresh_runner(world, "runner4", provider, "start").run(at=at(3), budget=10)
        assert run4["action"] is Action.START_NEW
        assert run4["generation_id"] != gid, "G1 is finished; this is G2"
        assert "restored" not in run4, "G1's cache was never offered to G2"
        assert len(provider.fetched) == 110, "G2 fetches players G1 already had - a refresh"
        assert run4["revision"] == 1, "G2's own revision, not G1's continued"

    def test_an_hourly_run_with_nothing_live_does_nothing(self, world: dict[str, Any]) -> None:
        provider = RosterProvider(["1"])
        run = fresh_runner(world, "runner1", provider, "continue_only").run(at=at(1))
        assert run["action"] is Action.NOOP
        assert provider.fetched == []


# ---------------------------------------------------------------------------
# The wrong cache
# ---------------------------------------------------------------------------


class TestTheWrongCacheStopsTheRun:
    """Section 17. Expected G5, disk holds G4: stop. Not resume, not publish,
    not create G6, not continue."""

    def test_a_different_generation_on_disk_is_fatal(self, world: dict[str, Any]) -> None:
        provider = RosterProvider(["1", "2"])
        # G4: fetched, saved, and then abandoned by hand.
        run_g4 = fresh_runner(world, "runner1", provider, "start").run(at=at(1), budget=1)
        g4 = run_g4["generation_id"]
        world["db"].rows[g4] = ("FAILED", 1)
        # G5: started on a runner that saved nothing (its cache is lost).
        r5 = fresh_runner(world, "runner2", provider, "start")
        run_g5 = r5.run(at=at(2), budget=1)
        g5 = run_g5["generation_id"]
        del world["cache"].store[run_g5["saved"]]
        world["cache"].order.remove(run_g5["saved"])

        # A runner whose disk somehow holds G4 (restored by a stale key, put
        # there by hand - the restore keys can no longer do it, but a disk is
        # not only written by restores).
        runner = fresh_runner(world, "runner3", provider, "continue_only")
        shutil.copytree(world["cache"].store[run_g4["saved"]], runner.generations)
        fetched_before = len(provider.fetched)

        run = runner.run(at=at(2, 5))

        assert run["action"] is Action.FETCH, "the database expects G5 to be resumed"
        assert run["verify"].ok is False
        assert g4 in run["stopped"] and g5 in run["stopped"]
        assert "wrong generation" in run["stopped"]
        assert len(provider.fetched) == fetched_before, "nothing was fetched"
        assert not (runner.generations / g5).exists(), "G5 was not created on this disk"
        assert world["db"].rows[g5] == ("IN_PROGRESS", 1), "and the database was not touched"

    def test_the_store_refuses_to_resume_the_wrong_generation_even_if_asked(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Defence behind the workflow gate: the ingest's own resolution."""
        store = GenerationStore(root=tmp_path / "g")
        store.create(now=at(1))
        with pytest.raises(GenerationError, match="wrong generation"):
            store.resolve(resume=True, expected_id="29990101T000000Z")

    def test_the_restore_never_falls_back_to_another_generation(
        self, world: dict[str, Any]
    ) -> None:
        """The restore-key contract, on the stand-in that models it."""
        provider = RosterProvider(["1"])
        run_g4 = fresh_runner(world, "runner1", provider, "start").run(at=at(1))
        restored = world["cache"].restore(
            key_for("29990101T000000Z", 1),
            prefix_for("29990101T000000Z"),
            world["tmp"] / "elsewhere",
        )
        assert restored is None, f"G4's key {run_g4['saved']} must not satisfy a request for G5"


# ---------------------------------------------------------------------------
# The missing cache
# ---------------------------------------------------------------------------


class TestAMissingCacheStopsTheRunSafely:
    """Section 5. IN_PROGRESS in the database, nothing on disk: say so, name
    the recovery, change nothing."""

    def test_nothing_restored_is_fatal_and_names_the_recovery(self, world: dict[str, Any]) -> None:
        provider = RosterProvider(["1", "2", "3"])
        run1 = fresh_runner(world, "runner1", provider, "start").run(at=at(1), budget=1)
        # The cache is evicted.
        world["cache"].store.clear()
        world["cache"].order.clear()

        run2 = fresh_runner(world, "runner2", provider, "continue_only").run(at=at(1, 5))

        assert run2["action"] is Action.FETCH
        assert run2["restored"] is None
        assert run2["verify"].ok is False
        assert "could not be restored" in run2["stopped"]
        assert "--abandon " + run1["generation_id"] in run2["stopped"]
        assert len(provider.fetched) == 1, "nothing was refetched under G1's name"
        assert world["db"].rows[run1["generation_id"]] == ("IN_PROGRESS", 1), (
            "not completed, not failed, not replaced"
        )

    def test_the_store_says_the_same_thing(self, tmp_path: pathlib.Path) -> None:
        store = GenerationStore(root=tmp_path / "g")
        with pytest.raises(GenerationError, match="could not be restored"):
            store.resolve(resume=True, expected_id="29990101T000000Z")

    def test_abandoning_is_explicit_and_recorded(self, tmp_path: pathlib.Path) -> None:
        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.abandon("cache evicted; restarting by hand")

        reread = store.get(generation.generation_id)
        assert reread is not None
        assert reread.status is GenerationStatus.FAILED
        assert reread.metadata.failure_reason == "cache evicted; restarting by hand"
        assert store.in_progress() is None, "and the next cadence run may start fresh"


# ---------------------------------------------------------------------------
# Checkpoint revisions
# ---------------------------------------------------------------------------


class TestCheckpointRevisions:
    """Sections 12 to 14. Immutable keys, monotonic progress."""

    def test_every_run_bumps_the_revision(self, tmp_path: pathlib.Path) -> None:
        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        assert generation.metadata.checkpoint_revision == 0
        assert generation.checkpoint() == 1
        assert generation.checkpoint() == 2
        reread = store.get(generation.generation_id)
        assert reread is not None
        assert reread.metadata.checkpoint_revision == 2, "persisted, not only in memory"

    def test_an_older_checkpoint_than_the_database_recorded_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """G5 checkpoint 5 exists and checkpoint 4 was restored. Resuming 4
        would refetch what 5 had and could not know which players the failure
        ledger has since retired."""
        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.checkpoint()  # 1

        verdict = verify_local_state(store, generation.generation_id, expected_revision=2)
        assert verdict.ok is False
        assert "checkpoint 1" in verdict.reason and "checkpoint 2" in verdict.reason
        assert "regress" in verdict.reason

    def test_a_newer_local_checkpoint_is_allowed(self, tmp_path: pathlib.Path) -> None:
        """The last run saved its cache and then could not reach the database.
        The disk is the truth in that case, and the database catches up on the
        next record."""
        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.checkpoint()
        generation.checkpoint()  # 2

        verdict = verify_local_state(store, generation.generation_id, expected_revision=1)
        assert verdict.ok is True
        assert verdict.local_revision == 2

    def test_the_matching_checkpoint_is_accepted(self, tmp_path: pathlib.Path) -> None:
        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.checkpoint()
        verdict = verify_local_state(store, generation.generation_id, expected_revision=1)
        assert verdict == Verdict(
            True, f"restored cache holds generation {generation.generation_id} at checkpoint 1", 1
        )

    def test_completed_players_never_regress_across_accepted_checkpoints(
        self, world: dict[str, Any]
    ) -> None:
        provider = RosterProvider([str(i) for i in range(1, 31)])
        counts: list[int] = []
        fresh_runner(world, "r1", provider, "start").run(at=at(1), budget=10)
        for n, budget in ((2, 10), (3, 5), (4, None)):
            run = fresh_runner(world, f"r{n}", provider, "continue_only").run(
                at=at(1, n), budget=budget
            )
            assert run["verify"].ok
            store = GenerationStore(root=world["tmp"] / f"r{n}" / "generations")
            generation = store.get(run["generation_id"])
            assert generation is not None
            counts.append(generation.metadata.completed_players)
        assert counts == sorted(counts), f"progress went backwards: {counts}"
        assert counts[-1] == 30

    def test_cache_keys_are_never_reused_across_runs(self, world: dict[str, Any]) -> None:
        """`FakeCache.save` raises on a duplicate key, as GitHub refuses one.
        Three runs, three keys, no exception."""
        provider = RosterProvider([str(i) for i in range(1, 31)])
        fresh_runner(world, "r1", provider, "start").run(at=at(1), budget=10)
        fresh_runner(world, "r2", provider, "continue_only").run(at=at(1, 5), budget=10)
        fresh_runner(world, "r3", provider, "continue_only").run(at=at(1, 6))
        assert len(world["cache"].store) == 3
        assert all(k.endswith(("-0001", "-0002", "-0003")) for k in world["cache"].store)


# ---------------------------------------------------------------------------
# The verify CLI is fatal
# ---------------------------------------------------------------------------


class TestTheVerifyCommandStopsTheJob:
    def test_it_exits_non_zero_on_a_mismatch(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """`cache_matches=false` used to be an informational output. The
        workflow now consumes it as the step's exit code."""
        import pipelines.footystats.gate as gate

        monkeypatch.setattr(gate, "GenerationStore", lambda: GenerationStore(root=tmp_path / "g"))
        code = gate.main(["--verify-restored", "29990101T000000Z", "--expected-revision", "0"])

        assert code == 1
        err = capsys.readouterr().err
        assert "::error::" in err
        assert "--abandon 29990101T000000Z" in err

    def test_it_exits_zero_when_the_disk_matches(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pipelines.footystats.gate as gate

        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.checkpoint()
        monkeypatch.setattr(gate, "GenerationStore", lambda: store)

        code = gate.main(
            ["--verify-restored", generation.generation_id, "--expected-revision", "1"]
        )
        assert code == 0

    def test_a_stale_checkpoint_exits_non_zero(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pipelines.footystats.gate as gate

        store = GenerationStore(root=tmp_path / "g")
        generation = store.create(now=at(1))
        generation.checkpoint()
        monkeypatch.setattr(gate, "GenerationStore", lambda: store)

        code = gate.main(
            ["--verify-restored", generation.generation_id, "--expected-revision", "3"]
        )
        assert code == 1
