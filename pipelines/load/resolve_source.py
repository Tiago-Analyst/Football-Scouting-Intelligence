"""Decide which provider a pipeline run is refreshing.

WHY THIS EXISTS

The workflow used to answer the question inline, in every step, as::

    ${{ inputs.source || 'transfermarkt' }}

`inputs` is empty on a scheduled run, so the fallback applied to all of them.
The Monday/Wednesday/Friday crons exist to refresh FootyStats and resolved to
Transfermarkt instead - three runs a week refreshing the wrong provider, and
doing it after the FootyStats fetch had already run, because that step was
gated on the API key rather than on the source.

The answer is now computed once, here, and read by every step.

HOW THE SCHEDULE IS MATCHED

GitHub needs cron literals in the workflow file and will not read them from
config, so the same expressions appear in two places. Rather than hard-coding
the mapping a third time, this matches `github.event.schedule` - the literal
GitHub reports for the firing cron - against `refresh.<source>.cron` in
`config/competitions.yaml`. Adding a source to that file and its cron to the
workflow is then enough; nothing here changes.

An unrecognised cron is an error rather than a default. A schedule nobody can
account for should stop a run that writes to production, not pick a provider
and carry on - which is exactly the failure this module replaces.
"""

from __future__ import annotations

import os
import pathlib
import sys
from collections.abc import Mapping

import yaml

#: Sources a run may refresh. `demo` is manual-only: nothing schedules it.
KNOWN_SOURCES = ("transfermarkt", "footystats", "demo")

CONFIG = pathlib.Path(__file__).resolve().parents[2] / "config" / "competitions.yaml"


class UnresolvedSource(RuntimeError):
    """The run's source could not be determined from its trigger."""


#: What a scheduled run is allowed to do.
#:
#: `start` may begin a new refresh generation, or continue an open one.
#: `continue_only` may only continue an open one - a cron that fires hourly
#: must not start a fresh fourteen-hour refresh every hour.
START = "start"
CONTINUE_ONLY = "continue_only"


def cron_map(config: Mapping[str, object]) -> dict[str, tuple[str, str]]:
    """`{cron literal: (source, mode)}` from the refresh block.

    Two kinds of cron per source. `cron` is the cadence - when a new refresh
    may begin. `continuation_cron` fires more often and may only carry an
    unfinished one forward.

    Sources with no cron are skipped rather than mapped to `None`: a source
    that is never scheduled cannot be selected by a schedule.
    """
    refresh = config.get("refresh") or {}
    if not isinstance(refresh, Mapping):
        return {}
    mapping: dict[str, tuple[str, str]] = {}
    for source, entry in refresh.items():
        if not isinstance(entry, Mapping):
            continue
        for key, mode in (("cron", START), ("continuation_cron", CONTINUE_ONLY)):
            cron = entry.get(key)
            if isinstance(cron, str) and cron.strip():
                mapping[_normalise(cron)] = (str(source), mode)
    return mapping


def _normalise(cron: str) -> str:
    """Collapse whitespace so `0 4 * * 1,3,5` and `0  4 * * 1,3,5` agree."""
    return " ".join(cron.split())


def resolve_with_mode(
    *,
    event_name: str,
    schedule: str | None,
    input_source: str | None,
    config: Mapping[str, object],
) -> tuple[str, str]:
    """The source this run refreshes, and what it is allowed to do.

    Manual dispatch uses what the operator chose, and may start a refresh. A
    schedule uses whichever source claims that cron, and whether it may start
    one depends on which of that source's crons fired. Anything else is an
    error.
    """
    if event_name == "workflow_dispatch":
        chosen = (input_source or "").strip()
        if not chosen:
            raise UnresolvedSource(
                "workflow_dispatch without a source. The input has a default, so an "
                "empty value means the workflow was changed rather than that the "
                "operator declined to choose."
            )
        if chosen not in KNOWN_SOURCES:
            raise UnresolvedSource(f"unknown source {chosen!r}; expected one of {KNOWN_SOURCES}")
        return chosen, START

    if event_name == "schedule":
        literal = _normalise(schedule or "")
        if not literal:
            raise UnresolvedSource("a scheduled run reported no cron expression")
        mapping = cron_map(config)
        entry = mapping.get(literal)
        if entry is None:
            raise UnresolvedSource(
                f"no source in config/competitions.yaml claims the cron {literal!r}. "
                f"Known: {sorted(mapping)}. Add it to `refresh`, or remove the cron "
                f"from the workflow - a scheduled run must not guess which provider "
                f"it is refreshing."
            )
        source, mode = entry
        if source not in KNOWN_SOURCES:
            raise UnresolvedSource(f"config schedules unknown source {source!r}")
        return source, mode

    raise UnresolvedSource(
        f"cannot resolve a source for event {event_name!r}. Only workflow_dispatch "
        f"and schedule refresh production data."
    )


def resolve(
    *,
    event_name: str,
    schedule: str | None,
    input_source: str | None,
    config: Mapping[str, object],
) -> str:
    """The source alone, for callers that do not care what it may do."""
    source, _ = resolve_with_mode(
        event_name=event_name,
        schedule=schedule,
        input_source=input_source,
        config=config,
    )
    return source


def load_config(path: pathlib.Path = CONFIG) -> Mapping[str, object]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, Mapping) else {}


def main(argv: list[str] | None = None) -> int:
    """Resolve from the environment and write to `$GITHUB_OUTPUT`."""
    try:
        source, mode = resolve_with_mode(
            event_name=os.environ.get("EVENT_NAME", ""),
            schedule=os.environ.get("SCHEDULE"),
            input_source=os.environ.get("INPUT_SOURCE"),
            config=load_config(),
        )
    except UnresolvedSource as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    values = {"source": source, "mode": mode}
    for key, value in values.items():
        print(f"{key}={value}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
