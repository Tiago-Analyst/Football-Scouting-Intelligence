"""Swap the staged dataset into production, atomically.

    python -m pipelines.load.promote --apply
    python -m pipelines.load.promote --rollback
    python -m pipelines.load.promote            # report, change nothing

WHAT PROBLEM THIS SOLVES
========================

A refresh used to load straight into the served tables. `--verify` ran the
serving quality suite inside that transaction, so a load producing bad data
rolled back - but everything *after* the commit ran against data readers were
already being served: identity resolution, the prune, the data-quality report,
the independent analytics validation.

If one of those failed, the site was serving a dataset nothing had finished
checking, and the only remedy was to notice and re-run.

Now a refresh loads into `analytics_staging` and every one of those steps runs
against it. This module is the moment the result becomes production, and it is
the only moment: anything that fails before it leaves the served schema
untouched, because the served schema was never being written to.

HOW THE SWAP WORKS
==================

Three renames in one transaction:

    analytics          -> analytics_previous
    analytics_staging  -> analytics
    analytics_previous -> analytics_staging

PostgreSQL takes DDL locks and commits this atomically, so a reader sees either
the whole previous dataset or the whole new one - never a mixture, and never an
empty schema. Renaming a schema does not rewrite the tables in it, so the cost
is a lock rather than a copy, whatever the row count.

The schema that was serving becomes the staging schema. That is not a
side-effect to tolerate; it is the recovery path. One cycle of production data
is always sitting in `analytics_staging`, and `--rollback` is the same swap
performed again.

WHAT IT REFUSES TO DO
=====================

Promote a staging schema that is empty, or one holding fewer player-seasons
than production by a wide margin. Both are shapes a half-finished load leaves
behind, and promoting either would replace a season with a fragment of itself
in a way no later step could detect - the data would be internally consistent
and simply missing.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SERVING = "analytics"
STAGING = "analytics_staging"
INTERMEDIATE = "analytics_previous"

#: How far below production a staging load may fall and still be promoted.
#:
#: Not a fixed floor: a season legitimately grows and shrinks, competitions are
#: added, and a provider can drop one. A fragment is a different shape - the
#: failure this catches is a load that stopped a third of the way through and
#: committed what it had.
MIN_RETAINED_SHARE = 0.75


@dataclass(frozen=True)
class SchemaCounts:
    """Row counts either side of a promotion, for the decision and the log."""

    players: int
    player_seasons: int
    competitions: int

    @property
    def is_empty(self) -> bool:
        return self.player_seasons == 0


class PromotionError(RuntimeError):
    """The swap was refused. Production is untouched."""


def _counts(connection, schema: str) -> SchemaCounts:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    def count(table: str) -> int:

        # schemas this file owns, never values from outside it. A bound
        # parameter cannot carry an identifier, so interpolation is the only
        # option here and the safety comes from the values being fixed.
        return int(
            connection.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar()  # noqa: S608
            or 0
        )

    return SchemaCounts(
        players=count("dim_player"),
        player_seasons=count("fact_player_season_stats"),
        competitions=count("dim_competition"),
    )


def check(before: SchemaCounts, staged: SchemaCounts) -> list[str]:
    """Why this promotion should not happen. Empty means it may."""
    reasons: list[str] = []

    if staged.is_empty:
        reasons.append("the staging schema holds no player-seasons; there is nothing to promote")
        return reasons

    if before.is_empty:
        # First promotion into an empty production schema. Nothing to compare
        # against, and nothing to lose.
        return reasons

    share = staged.player_seasons / before.player_seasons
    if share < MIN_RETAINED_SHARE:
        reasons.append(
            f"staging holds {staged.player_seasons:,} player-seasons against production's "
            f"{before.player_seasons:,} ({share:.0%}). A drop this large is the shape of a "
            f"load that stopped partway; promote with --force if the season really did "
            f"shrink."
        )
    return reasons


def swap(connection) -> None:  # type: ignore[no-untyped-def]
    """The three renames. Caller owns the transaction."""
    from sqlalchemy import text

    connection.execute(text(f'ALTER SCHEMA "{SERVING}" RENAME TO "{INTERMEDIATE}"'))
    connection.execute(text(f'ALTER SCHEMA "{STAGING}" RENAME TO "{SERVING}"'))
    connection.execute(text(f'ALTER SCHEMA "{INTERMEDIATE}" RENAME TO "{STAGING}"'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the swap. Without it, report only.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help=(
            "Swap back to the previous dataset. The same operation: the schema "
            "that was serving is sitting in staging."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Promote despite a large row-count drop. For a season that really did shrink.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings
    from app.core.database import get_engine
    from app.core.logging import configure_logging, get_logger

    settings = get_settings()
    configure_logging(settings)
    log = get_logger(__name__)

    engine = get_engine()
    with engine.connect() as connection:
        production = _counts(connection, SERVING)
        staged = _counts(connection, STAGING)

    print(f"{'':<14}{'production':>14}{'staging':>14}")
    for label, attribute in (
        ("players", "players"),
        ("player-seasons", "player_seasons"),
        ("competitions", "competitions"),
    ):
        print(f"{label:<14}{getattr(production, attribute):>14,}{getattr(staged, attribute):>14,}")
    print()

    if args.rollback:
        # No row-count check. A rollback is a decision to go back to what was
        # being served an hour ago, and refusing it because that dataset is
        # smaller would be refusing the recovery path at the moment it is
        # needed.
        if not args.apply:
            print("Would swap back to the previous dataset. Re-run with --apply.")
            return 0
        with engine.begin() as connection:
            swap(connection)
        print("Rolled back. The previous dataset is serving again.")
        log.warning("analytics_promotion_rolled_back")
        return 0

    reasons = check(production, staged)
    if reasons and not args.force:
        for reason in reasons:
            print(f"REFUSED: {reason}", file=sys.stderr)
        print("\nProduction is untouched.", file=sys.stderr)
        return 1
    if reasons:
        for reason in reasons:
            print(f"::warning::forced past: {reason}")

    if not args.apply:
        print("Ready to promote. Re-run with --apply.")
        return 0

    with engine.begin() as connection:
        swap(connection)

    print(
        f"Promoted. {staged.player_seasons:,} player-seasons across "
        f"{staged.competitions:,} competitions are now serving."
    )
    print(f'The previous dataset is in "{STAGING}" and can be restored with `--rollback --apply`.')
    log.info(
        "analytics_promoted",
        players=staged.players,
        player_seasons=staged.player_seasons,
        competitions=staged.competitions,
        replaced_player_seasons=production.player_seasons,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
