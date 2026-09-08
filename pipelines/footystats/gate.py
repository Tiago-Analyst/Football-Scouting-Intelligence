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
restored is the generation the database named: a stale cache holding an older
generation must not be resumed against a newer database record.
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


def verify_local_state(store: GenerationStore, expected_id: str) -> tuple[bool, str]:
    """Whether the restored cache holds the generation the database named.

    A cache restored from `restore-keys` can be an older generation's, and
    resuming that against a newer database record would interleave two
    universes - the exact failure generations exist to prevent. Better to
    rebuild than to continue into the wrong one.
    """
    try:
        found = {g.generation_id for g in store.all()}
    except GenerationError as exc:
        return False, f"generation state on disk is unreadable: {exc}"

    if expected_id in found:
        return True, f"restored cache holds generation {expected_id}"
    if not found:
        return False, (
            f"the database expects generation {expected_id} and the restored cache holds "
            f"none. The fetch will start it again from whatever is on disk."
        )
    return False, (
        f"the database expects generation {expected_id} and the restored cache holds "
        f"{sorted(found)}. Refusing to resume into the wrong generation."
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
            "Check that the restored cache holds this generation. Run after the "
            "cache step, with the id the earlier gate reported."
        ),
    )
    args = parser.parse_args(argv)

    if args.verify_restored:
        ok, reason = verify_local_state(GenerationStore(), args.verify_restored)
        print(f"cache_matches={'true' if ok else 'false'}")
        print(f"reason={reason}")
        _emit({"cache_matches": "true" if ok else "false", "reason": reason})
        if not ok:
            print(f"::warning::{reason}", file=sys.stderr)
        # Never fatal. A mismatched cache is recoverable by fetching again;
        # failing the job would turn a slow refresh into a stopped one.
        return 0

    live = _live_from_state()
    decision = decide_from_state(args.mode, live)

    print(f"action={decision.action.value}")
    print(f"proceed={'true' if decision.proceed else 'false'}")
    print(f"needs_local_state={'true' if decision.action.needs_local_state else 'false'}")
    print(f"generation_id={decision.generation_id or ''}")
    print(f"reason={decision.reason}")
    _emit(
        {
            "action": decision.action.value,
            "proceed": "true" if decision.proceed else "false",
            "needs_local_state": "true" if decision.action.needs_local_state else "false",
            "generation_id": decision.generation_id or "",
            "reason": decision.reason,
        }
    )
    if not decision.proceed:
        print(f"\nNothing to do: {decision.reason}", file=sys.stderr)
    return 0


def _live_from_state() -> list[tuple[str, str]]:
    """The database when it is reachable, the filesystem when it is not."""
    try:
        from app.core.database import get_session_factory

        with get_session_factory()() as session:
            return active_generations(session)
    except Exception as exc:  # a local run without a database reaches here
        print(
            f"Could not read generation state from the database "
            f"({type(exc).__name__}); falling back to the local filesystem.",
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
