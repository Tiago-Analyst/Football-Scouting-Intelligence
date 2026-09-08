"""Should this scheduled run fetch anything?

    python -m pipelines.footystats.gate     # writes proceed=true|false

WHY A GATE EXISTS AT ALL

A complete FootyStats refresh is about 23,500 requests - roughly fourteen hours
at the account's rate limit - and a job may fetch for about forty-five minutes.
So a generation needs around nineteen productive runs.

On the cadence cron alone (Mondays, Wednesdays, Fridays) that is three weeks
per refresh, by which time the data being published is older than the interval
that produced it. The fix is to run far more often while a refresh is
unfinished, which introduces the opposite hazard: an hourly cron that starts a
new fourteen-hour refresh every hour.

So the two crons mean different things, and this decides which applies:

    start           the cadence fired. Begin a generation, or carry on with
                    an open one.
    continue_only   the hourly cron fired. Carry on with an open generation,
                    and do nothing at all if there is none.

The second case is the common one - most hours have no refresh running - and it
exits immediately, before anything expensive.

CONCURRENCY

The workflow's `concurrency` group is what stops two runs fetching at once.
This is the second line: `GenerationStore.in_progress()` raises if it ever
finds two open generations, so an interleaved universe is reported rather than
silently assembled.
"""

from __future__ import annotations

import argparse
import os
import sys

from pipelines.footystats.generations import GenerationError, GenerationStore
from pipelines.load.resolve_source import CONTINUE_ONLY, START


def decide(mode: str, store: GenerationStore) -> tuple[bool, str]:
    """Whether to fetch, and why. Never raises for an ordinary state."""
    try:
        open_one = store.in_progress()
    except GenerationError as exc:
        # Two open generations, or unreadable metadata. Structural: a person
        # should look rather than a run should guess.
        return False, f"generation state needs attention: {exc}"

    if mode == CONTINUE_ONLY:
        if open_one is None:
            return False, "no refresh generation is in progress; nothing to continue"
        return True, (
            f"continuing generation {open_one.generation_id} "
            f"({open_one.metadata.completion_pct:.1f}% complete, "
            f"{open_one.metadata.pending_players:,} player(s) pending)"
        )

    if mode == START:
        if open_one is not None:
            return True, (
                f"cadence fired while generation {open_one.generation_id} is still open "
                f"({open_one.metadata.completion_pct:.1f}% complete); continuing it rather "
                f"than starting another"
            )
        return True, "starting a new refresh generation"

    return False, f"unknown mode {mode!r}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        default=os.environ.get("REFRESH_MODE", START),
        help="start | continue_only. Normally from the source resolver.",
    )
    args = parser.parse_args(argv)

    proceed, reason = decide(args.mode, GenerationStore())
    print(f"proceed={'true' if proceed else 'false'}")
    print(f"reason={reason}")

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"proceed={'true' if proceed else 'false'}\n")
            handle.write(f"reason={reason}\n")

    if not proceed:
        print(f"\nNothing to do: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
