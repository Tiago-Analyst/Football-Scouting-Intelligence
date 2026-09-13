"""What should this scheduled run actually do?

    python -m pipelines.footystats.gate     # writes action=... proceed=...

WHY A GATE EXISTS AT ALL
========================

A complete FootyStats refresh is about 23,500 requests - roughly fourteen hours
at the account's rate limit - and a job may fetch for about forty-five minutes.
So a generation needs around nineteen productive runs.

On the cadence cron alone (Mondays, Wednesdays, Fridays) that is three weeks per
refresh, by which time the data being published is older than the interval that
produced it. The fix is to run far more often while a refresh is unfinished,
which introduces the opposite hazard: an hourly cron that starts a new
fourteen-hour refresh every hour.

THE ACTIONS
===========

    FETCH          A generation is IN_PROGRESS. Resume it.
    PUBLISH_READY  A generation is COMPLETE or VALIDATED and not yet
                   published. Retry publication - do not fetch anything.
    START_NEW      Nothing is open and the cadence fired. Begin a generation.
    NOOP           Nothing is open and the hourly cron fired. Do nothing.

`PUBLISH_READY` is the one that was missing, and its absence was expensive.
A generation whose fetch finished but whose publication failed - identity
resolution erroring, a quality check failing, the promotion refusing - was
indistinguishable from no generation at all, so the next cadence run started a
fresh one and refetched every player. Thirteen hours of API budget discarded
because a downstream step had a bad minute.

WHY THE DATABASE IS AUTHORITATIVE
=================================

Generation state lives in two places: the files on disk, which only a runner
that restored the cache can see, and `fact_refresh_generation`, which every
runner can reach.

Deciding from the filesystem meant deciding from an empty one. A fresh GitHub
runner has no `data/raw/footystats/generations/` until the cache is restored,
so the gate saw nothing, answered NOOP, and the cache was never restored -
the hourly continuation could never run at all. Ordering the cache first would
work but costs a large download every quiet hour.

So the database decides *what* to do, and the cache is restored only when the
answer needs local files. `verify_local_state` then checks that what was
restored is the generation the database named, at a checkpoint no older than
the one the database recorded.

WHO IS AUTHORITATIVE
====================

    PostgreSQL `fact_refresh_generation`   generation identity, status, and the
                                           checkpoint revision last recorded
    GitHub Actions cache                   checkpoint payload storage, nothing more
    the runner's filesystem                a restored working copy, nothing more

A cache or a filesystem may never override the database on *which* generation
is live. They may legitimately hold a newer checkpoint of the *same* generation
- the last run saved its cache and then could not reach the database - and
that is reconciled forward, never backward. When the database cannot be read
in production the gate fails closed: no decision, no fetch, no new generation.

WHAT A MISMATCH DOES
====================

Stops the run. Not a warning: `--verify-restored` exits non-zero, the workflow
step fails, and every generation-dependent step after it is skipped. The three
cases and why each one stops:

    same generation, local == database revision    continue
    same generation, local >  database revision    continue; the database is
                                                   advanced to the local
                                                   revision after an
                                                   integrity check
    same generation, local <  database revision    STOP - stale checkpoint
    same generation, files do not match metadata   STOP - partial restore
    different generation                           STOP - two universes
    nothing                                        STOP - see below

The restore itself asks GitHub for a key that does not exist
(`footystats-gen-<id>-restore-<run_id>`) so that only the restore-keys prefix
matches, and GitHub returns the newest cache for the generation. Asking for
the database's revision exactly was the bug: with `-0004` and `-0005` both
saved and the database still saying 4, the exact hit won and checkpoint 5 was
silently discarded.

Nothing restored for a live generation is the case that wants spelling out.
The fetch *could* rebuild from an empty directory, and an earlier version of
this let it, with a warning. That is the wrong call: a runner with no state
for G5 would start a fresh fetch under G5's name, refetching every player the
lost checkpoint had, and the database would go on describing a generation
whose files no longer match it. So it stops, says what happened, and names the
recovery - restore the cache, or abandon the generation explicitly with
`python -m pipelines.footystats.generations --abandon <id>`. Never
automatically.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from enum import StrEnum

from pipelines.footystats.generations import (
    GenerationError,
    GenerationStatus,
    GenerationStore,
)
from pipelines.load.resolve_source import CONTINUE_ONLY, START


class Action(StrEnum):
    """What a run should do. Read by the workflow to gate every later step."""

    FETCH = "FETCH"
    PUBLISH_READY = "PUBLISH_READY"
    START_NEW = "START_NEW"
    NOOP = "NOOP"

    @property
    def needs_local_state(self) -> bool:
        """Whether the run has to restore the generation cache.

        `START_NEW` does not: it creates a generation rather than continuing
        one, and restoring a previous generation's files would only give it
        something to be confused by.
        """
        return self in {Action.FETCH, Action.PUBLISH_READY}

    @property
    def fetches(self) -> bool:
        return self is Action.FETCH or self is Action.START_NEW


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    #: The generation this run works on, when one already exists.
    generation_id: str | None = None
    #: The checkpoint the database recorded for it. What the restore is
    #: checked against.
    expected_revision: int | None = None

    @property
    def proceed(self) -> bool:
        return self.action is not Action.NOOP


#: Statuses that mean "fetching is finished; publication has not succeeded".
AWAITING_PUBLICATION = (GenerationStatus.COMPLETE, GenerationStatus.VALIDATED)


#: Statuses a run may pick up. PUBLISHED is finished and FAILED is abandoned.
LIVE_STATUSES = (
    GenerationStatus.IN_PROGRESS.value,
    GenerationStatus.COMPLETE.value,
    GenerationStatus.VALIDATED.value,
)


def active_generations(session) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Every generation the database considers live, as `(id, status)`.

    `expected_revision_for` fetches the checkpoint separately: the decision
    itself is pure over `(id, status)` and tested as such.

    A list rather than the newest one, because "there are two" is an answer
    that has to reach the caller. Silently taking the newest would resume one
    universe while another sat half-fetched, which is the failure generations
    exist to prevent.
    """
    from sqlalchemy import select

    from app.models import FactRefreshGeneration

    rows = session.execute(
        select(FactRefreshGeneration.generation_id, FactRefreshGeneration.status)
        .where(FactRefreshGeneration.source == "footystats")
        .order_by(FactRefreshGeneration.generation_id)
    ).all()
    return [(generation_id, status) for generation_id, status in rows if status in LIVE_STATUSES]


def decide_from_state(mode: str, live: list[tuple[str, str]]) -> Decision:
    """The decision itself, given the mode and whatever is live.

    Pure: no database, no filesystem. Every branch below is a test in
    `test_pipeline_source_resolution.py`.
    """
    if len(live) > 1:
        # Two open universes. Which one to continue is a judgement about how
        # they got that way, and a scheduled job guessing wrong wastes days of
        # API budget interleaving them.
        names = ", ".join(generation_id for generation_id, _ in live)
        return Decision(
            Action.NOOP,
            f"more than one generation is live ({names}); this needs attention rather than a guess",
        )

    if live:
        generation_id, status = live[0]
        if status == GenerationStatus.IN_PROGRESS.value:
            reason = (
                f"continuing generation {generation_id} rather than starting another"
                if mode == START
                else f"continuing generation {generation_id}"
            )
            return Decision(Action.FETCH, reason, generation_id)
        # COMPLETE or VALIDATED: fetching is done and publication is not.
        return Decision(
            Action.PUBLISH_READY,
            (
                f"generation {generation_id} is {status} and unpublished; retrying "
                f"publication without refetching"
            ),
            generation_id,
        )

    if mode == START:
        return Decision(Action.START_NEW, "no generation is live; starting a new one")

    if mode == CONTINUE_ONLY:
        return Decision(
            Action.NOOP,
            "no generation is live: nothing to continue on the continuation cron",
        )

    return Decision(Action.NOOP, f"unknown mode {mode!r}")


@dataclass(frozen=True)
class Verdict:
    """What the verification found. `ok` is the only thing the workflow acts
    on; the rest is for the person reading why it stopped."""

    ok: bool
    reason: str
    local_revision: int | None = None


def verify_local_state(
    store: GenerationStore,
    expected_id: str,
    *,
    expected_revision: int | None = None,
) -> Verdict:
    """Whether the restored cache holds the generation the database named.

    Three ways to fail, none of them recoverable by continuing:

    - the wrong generation: resuming it against a newer database record would
      interleave two universes, the failure generations exist to prevent;
    - no generation: the fetch would start G5 again from nothing under G5's
      name, and the database would go on describing files that no longer
      exist. Stop, say so, name the recovery;
    - the right generation at an older checkpoint than the database recorded:
      resuming it refetches what the newer checkpoint already had and cannot
      know which players the failure ledger has since retired. Progress is
      monotonic or it is not progress.

    A local revision *newer* than the database's is allowed. It means the last
    run saved its cache and then could not reach the database to say so, and
    the disk is the truth in that case.
    """
    try:
        generations = {g.generation_id: g for g in store.all()}
    except GenerationError as exc:
        return Verdict(False, f"generation state on disk is unreadable: {exc}")

    generation = generations.get(expected_id)
    if generation is None:
        if not generations:
            return Verdict(
                False,
                f"generation {expected_id} is live in the database but its local checkpoint "
                f"state could not be restored. Nothing was resumed and nothing was started. "
                f"Recover by restoring its cache, or abandon it explicitly: "
                f"python -m pipelines.footystats.generations --abandon {expected_id}",
            )
        return Verdict(
            False,
            f"the database expects generation {expected_id} and the restored cache holds "
            f"{sorted(generations)}. Refusing to resume into the wrong generation.",
        )

    local = generation.metadata.checkpoint_revision
    if expected_revision is not None and local < expected_revision:
        return Verdict(
            False,
            f"generation {expected_id} was restored at checkpoint {local} but the database "
            f"recorded checkpoint {expected_revision}. A newer checkpoint exists and was not "
            f"restored; resuming from this one would regress progress. Nothing was resumed.",
            local,
        )

    problems = generation.integrity_problems()
    if problems:
        # Newer or not, a checkpoint whose files do not match its metadata is
        # not a state to continue from, and certainly not one to tell the
        # database to trust.
        return Verdict(
            False,
            f"generation {expected_id} was restored at checkpoint {local} but its files do "
            f"not match its metadata: {'; '.join(problems)}. Nothing was resumed.",
            local,
        )

    if expected_revision is not None and local > expected_revision:
        return Verdict(
            True,
            f"restored cache holds generation {expected_id} at checkpoint {local}, newer than "
            f"the database's {expected_revision}: the last run saved its cache and could not "
            f"record it. Intact; the database will be advanced to {local}.",
            local,
        )
    return Verdict(
        True, f"restored cache holds generation {expected_id} at checkpoint {local}", local
    )


def decide(mode: str, store: GenerationStore) -> tuple[bool, str]:
    """Filesystem-only decision, for local runs with no database.

    Kept because `--apply`-style local work should not need PostgreSQL. The
    workflow uses `main`, which prefers the database.
    """
    decision = decide_from_state(mode, _live_from_disk(store))
    return decision.proceed, decision.reason


def _live_from_disk(store: GenerationStore) -> list[tuple[str, str]]:
    """What the local generation directory holds, for runs without a database.

    An unreadable directory returns nothing rather than raising: on the local
    path that means "start one", and on the fallback path the database was
    already unavailable, so refusing here would leave no way to run at all.
    """
    try:
        generations = store.all()
    except GenerationError:
        return []
    return [
        (g.generation_id, g.status.value)
        for g in generations
        if g.status is GenerationStatus.IN_PROGRESS or g.status in AWAITING_PUBLICATION
    ]


def expected_revision_for(generation_id: str) -> int | None:
    """The checkpoint the database recorded for this generation, if reachable."""
    from pipelines.footystats.publish_status import expected_state

    state = expected_state(generation_id)
    return state[1] if state else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default=os.environ.get("REFRESH_MODE", START),
        help="start | continue_only. Normally from the source resolver.",
    )
    parser.add_argument(
        "--verify-restored",
        metavar="GENERATION_ID",
        help=(
            "Check that the restored cache holds this generation at a checkpoint no "
            "older than the database recorded. Exits non-zero otherwise: the workflow "
            "must not continue past a mismatch."
        ),
    )
    parser.add_argument(
        "--expected-revision",
        type=int,
        default=None,
        help="The checkpoint the database recorded. Read from the database when omitted.",
    )
    args = parser.parse_args(argv)

    if args.verify_restored:
        expected = args.expected_revision
        if expected is None:
            expected = expected_revision_for(args.verify_restored)
        verdict = verify_local_state(
            GenerationStore(), args.verify_restored, expected_revision=expected
        )
        print(f"cache_matches={'true' if verdict.ok else 'false'}")
        print(
            f"local_revision={verdict.local_revision if verdict.local_revision is not None else ''}"
        )
        print(f"reason={verdict.reason}")
        _emit(
            {
                "cache_matches": "true" if verdict.ok else "false",
                "local_revision": (
                    str(verdict.local_revision) if verdict.local_revision is not None else ""
                ),
                "reason": verdict.reason,
            }
        )
        if not verdict.ok:
            # FATAL, deliberately. An earlier version warned and continued,
            # on the grounds that a fetch could rebuild what was missing.
            # It could - under the wrong generation's name, refetching
            # everything the lost checkpoint held. See the module docstring.
            print(f"::error::{verdict.reason}", file=sys.stderr)
            return 1
        if (
            expected is not None
            and verdict.local_revision is not None
            and verdict.local_revision > expected
        ):
            # Forward, and only forward. The disk is newer and intact; the
            # database catches up so the next run's exact key names this
            # checkpoint rather than the one before it.
            from pipelines.footystats.publish_status import reconcile_revision

            if reconcile_revision(args.verify_restored, verdict.local_revision):
                print(f"database checkpoint advanced {expected} -> {verdict.local_revision}")
            else:
                print(
                    "::warning::could not advance the database checkpoint; the next run "
                    "will restore the newest checkpoint for this generation regardless"
                )
        return 0

    try:
        live = _live_from_state()
    except AuthoritativeStateUnavailable as exc:
        # FAIL CLOSED. No action, no outputs that a later step could act on.
        print(f"::error::{exc}", file=sys.stderr)
        _emit({"action": "", "proceed": "false", "needs_local_state": "false"})
        return 1
    decision = decide_from_state(args.mode, live)
    if decision.generation_id and decision.expected_revision is None:
        decision = Decision(
            decision.action,
            decision.reason,
            decision.generation_id,
            expected_revision_for(decision.generation_id),
        )

    # Padded the same way the fetch pads it, so the exact cache key the
    # restore asks for is the key the last save wrote.
    revision = "" if decision.expected_revision is None else f"{decision.expected_revision:04d}"
    print(f"action={decision.action.value}")
    print(f"proceed={'true' if decision.proceed else 'false'}")
    print(f"needs_local_state={'true' if decision.action.needs_local_state else 'false'}")
    print(f"generation_id={decision.generation_id or ''}")
    print(f"expected_revision={revision}")
    print(f"reason={decision.reason}")
    _emit(
        {
            "action": decision.action.value,
            "proceed": "true" if decision.proceed else "false",
            "needs_local_state": "true" if decision.action.needs_local_state else "false",
            "generation_id": decision.generation_id or "",
            "expected_revision": revision,
            "reason": decision.reason,
        }
    )
    if not decision.proceed:
        print(f"\nNothing to do: {decision.reason}", file=sys.stderr)
    return 0


class AuthoritativeStateUnavailable(RuntimeError):
    """The database could not be read and nothing else is allowed to decide."""


def local_fallback_allowed() -> bool:
    """Whether a run may decide from the filesystem when the database is down.

    Never in production. The database is authoritative for generation state,
    and a fresh runner that cannot reach it has an empty disk - which reads
    as "no generation", which reads as START_NEW, which starts a fourteen-hour
    fetch beside the one the database knows is IN_PROGRESS. Failing closed
    costs one hourly run; failing open costs the refresh.

    Allowed for local development and tests, where there may be no database
    at all, when either:

      - `ALLOW_LOCAL_GATE_FALLBACK=true` is set explicitly, or
      - the environment is not production and the run is not on GitHub
        Actions.

    GitHub Actions is detected by the `GITHUB_ACTIONS` variable the runner
    sets. A production-mode local run stays closed: there is no reason to
    decide from the disk against a production database, and one good reason
    not to.
    """
    if os.environ.get("ALLOW_LOCAL_GATE_FALLBACK", "").lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        return False
    return os.environ.get("APP_ENV", "development").lower() != "production"


def _live_from_state() -> list[tuple[str, str]]:
    """The database, which is authoritative. The filesystem only where that
    is explicitly allowed - see `local_fallback_allowed`."""
    try:
        from app.core.database import get_session_factory

        with get_session_factory()() as session:
            return active_generations(session)
    except Exception as exc:
        if not local_fallback_allowed():
            raise AuthoritativeStateUnavailable(
                f"could not read generation state from the database "
                f"({type(exc).__name__}). The database is authoritative and this run may "
                f"not decide from the local filesystem: a fresh runner with no database "
                f"would see no generation and start a new one beside the one in progress. "
                f"Nothing was decided, fetched, started or published. Set "
                f"ALLOW_LOCAL_GATE_FALLBACK=true only for local development."
            ) from exc
        print(
            f"Could not read generation state from the database "
            f"({type(exc).__name__}); falling back to the local filesystem, which is "
            f"allowed outside production.",
            file=sys.stderr,
        )
        return _live_from_disk(GenerationStore())


def _emit(values: dict[str, str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            # Reasons can carry a newline from an exception message; a
            # multi-line value corrupts every output written after it.
            handle.write(f"{key}={' '.join(str(value).split())}\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
