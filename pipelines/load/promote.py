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

WHAT ELSE HAPPENS IN THE SAME TRANSACTION
=========================================

Two records, because both are claims about production and both would be lies if
they outlived a failed swap:

    fact_source_publication   one row: this source's data is now serving
    fact_refresh_generation   the generation becomes PUBLISHED

`fact_source_load` cannot answer either question any more. It is written by the
loader, and the loader now writes to staging - so a refresh that loads at 10:00
and fails identity resolution at 10:20 leaves a load row stamped 10:00 while
production still serves yesterday. Freshness read from that ledger tells a
reader the figures on screen are today's when they are not.

A publication row exists only if the swap committed, and the swap cannot commit
without it.

ONCE PER REFRESH
================

Before swapping, the promotion asks the ledger whether `source + refresh_id`
is already published, and stops - exit 0, nothing touched - if it is. A job
re-run after the first attempt committed would otherwise swap the previous
dataset back into production and record a second publication of the new one.
`--rollback` deletes the retracted row, so a refresh published and then rolled
back can be published again on purpose; the partial unique index
`uq_source_publication_refresh` says the same thing from the database side.

ONE SOURCE, NOT ALL OF THEM
===========================

A promotion publishes the whole universe, but only one provider in it is new.
Promoting a Transfermarkt refresh must not advance FootyStats' freshness: the
performance figures in that dataset are the ones published a fortnight ago and
saying otherwise restates the original bug with different tables.

So `--source` names the provider that was refreshed, and it is the only one
that gets a publication row.

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

#: Analytical tables carrying a `source` column, which is what makes "how many
#: rows did this provider publish" answerable at all.
SOURCED_TABLES = (
    "dim_competition",
    "dim_club",
    "bridge_player_source",
    "fact_player_season_stats",
    "fact_market_value",
    "fact_transfer",
)

#: Generation statuses a promotion may publish from. IN_PROGRESS is not one:
#: promoting a half-fetched universe is the failure generations exist to stop.
PUBLISHABLE_STATUSES = ("COMPLETE", "VALIDATED")


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


def rows_for_source(connection, schema: str, source: str) -> int:  # type: ignore[no-untyped-def]
    """Total source-owned relational rows in `schema` for this provider.

    Summed across every table that carries a `source` column - competitions,
    clubs, bridges, player-seasons, market values, transfers. A volume, and
    only that: it is the figure that changes when a refresh actually worked.
    It is *not* a player-season count, and was being read as one; that number
    is `player_seasons_for_source`, kept apart so one column cannot carry two
    meanings.
    """
    from sqlalchemy import text

    total = 0
    for table in SOURCED_TABLES:
        total += int(
            connection.execute(
                text(f'SELECT count(*) FROM "{schema}"."{table}" WHERE source = :s'),  # noqa: S608
                {"s": source},
            ).scalar()
            or 0
        )
    return total


def player_seasons_for_source(connection, schema: str, source: str) -> int:  # type: ignore[no-untyped-def]
    """Player-seasons this provider supplied. The number a reader means by
    "how many players", which `rows_for_source` is not."""
    from sqlalchemy import text

    return int(
        connection.execute(
            text(
                f'SELECT count(*) FROM "{schema}"."fact_player_season_stats" '  # noqa: S608
                f"WHERE source = :s"
            ),
            {"s": source},
        ).scalar()
        or 0
    )


def generation_status(connection, source: str, generation_id: str) -> str | None:  # type: ignore[no-untyped-def]
    """What the database says this generation's status is, or None."""
    from sqlalchemy import text

    row = connection.execute(
        text(
            "SELECT status FROM public.fact_refresh_generation "
            "WHERE source = :s AND generation_id = :g"
        ),
        {"s": source, "g": generation_id},
    ).first()
    return str(row[0]) if row else None


def already_published(connection, source: str, refresh_id: str | None) -> bool:  # type: ignore[no-untyped-def]
    """Whether this exact refresh has a publication row that has not been
    retracted.

    The check that makes a promotion safe to run twice. A job re-run after
    the first attempt committed, an operator invoking it twice, a connection
    lost after the commit but before the job recorded success: the second
    swap would put the previous dataset back and write a second row saying
    the new one was published again.

    A rollback deletes the row, so "published then rolled back" is not
    "already published" and a deliberate republish still works.
    """
    from sqlalchemy import text

    if refresh_id is None:
        return False
    return bool(
        connection.execute(
            text(
                "SELECT 1 FROM public.fact_source_publication "
                "WHERE source = :s AND refresh_id = :r LIMIT 1"
            ),
            {"s": source, "r": refresh_id},
        ).first()
    )


def publishable_generation(connection, source: str) -> str | None:
    """The generation this promotion is publishing, if the source has one.

    `None` is an ordinary answer, not a failure. Transfermarkt is a dataset
    download with no generation model, and a FootyStats promotion run by hand
    against an already-loaded staging schema has nothing open either.
    """
    from sqlalchemy import text

    row = connection.execute(
        text(
            "SELECT generation_id FROM public.fact_refresh_generation "
            "WHERE source = :s AND status = ANY(:statuses) "
            "ORDER BY generation_id DESC LIMIT 1"
        ),
        {"s": source, "statuses": list(PUBLISHABLE_STATUSES)},
    ).first()
    return row[0] if row else None


def record_publication(  # type: ignore[no-untyped-def]
    connection,
    *,
    source: str,
    generation_id: str | None,
    rows_published: int,
    player_seasons_published: int | None = None,
    refresh_id: str | None = None,
) -> None:
    """Write the records that make the promotion visible to readers.

    Caller owns the transaction, and that is the entire point: called from
    anywhere else, these become claims that can outlive a swap that never
    happened.

    Three writes:

      - the publication row, which freshness reads;
      - this refresh's quality rows, CANDIDATE -> PUBLISHED, by `source +
        refresh_id` - never by source alone, which would promote every older
        candidate of the provider, and never by generation, which Transfermarkt
        does not have;
      - for FootyStats, the generation's status, COMPLETE or VALIDATED ->
        PUBLISHED.

    All three tables live in `public`, so the schema renames above do not
    move them and the writes here are unaffected by which schema is serving.
    """
    from sqlalchemy import text

    refresh = refresh_id or generation_id

    connection.execute(
        text(
            "INSERT INTO public.fact_source_publication "
            "(source, refresh_id, generation_id, published_at, rows_published, "
            " player_seasons_published) "
            "VALUES (:source, :refresh_id, :generation_id, now(), :rows, :player_seasons)"
        ),
        {
            "source": source,
            "refresh_id": refresh,
            "generation_id": generation_id,
            "rows": rows_published,
            "player_seasons": player_seasons_published,
        },
    )

    if refresh is not None:
        connection.execute(
            text(
                "UPDATE public.fact_data_quality SET context = 'PUBLISHED' "
                "WHERE source = :source AND refresh_id = :refresh_id "
                "AND context = 'CANDIDATE'"
            ),
            {"source": source, "refresh_id": refresh},
        )

    if generation_id is None:
        return

    # COMPLETE or VALIDATED -> PUBLISHED. Guarded on the current status rather
    # than set unconditionally: re-running a promotion must not drag a FAILED
    # generation back to life, and must not restamp one already published with
    # a later time than the dataset actually reached readers.
    connection.execute(
        text(
            "UPDATE public.fact_refresh_generation "
            "SET status = 'PUBLISHED', published_at = now(), updated_at = now() "
            "WHERE source = :source AND generation_id = :generation_id "
            "AND status = ANY(:statuses)"
        ),
        {
            "source": source,
            "generation_id": generation_id,
            "statuses": list(PUBLISHABLE_STATUSES),
        },
    )


def retract_publication(connection) -> tuple[str, str | None] | None:  # type: ignore[no-untyped-def]
    """Undo the most recent publication record, for a rollback.

    A rollback really does un-publish: the dataset that row described is no
    longer the one being served. Leaving it in place would make freshness
    report the retracted publication, which is the bug this whole pass is
    about, arriving by a different route.

    So the row is deleted rather than superseded. The previous publication is
    still in the table and is true again, which is exactly the state a rollback
    restores. The generation goes back to VALIDATED so the gate offers it for
    publication again instead of treating it as finished.
    """
    from sqlalchemy import text

    row = connection.execute(
        text(
            "DELETE FROM public.fact_source_publication WHERE id = "
            "(SELECT id FROM public.fact_source_publication "
            " ORDER BY published_at DESC, id DESC LIMIT 1) "
            "RETURNING source, generation_id, refresh_id"
        )
    ).first()
    if row is None:
        return None

    source, generation_id, refresh_id = row
    if refresh_id is not None:
        # Its checks describe a candidate again. Leaving them PUBLISHED would
        # put the retracted refresh's checks on the public page above the
        # dataset that is actually serving.
        connection.execute(
            text(
                "UPDATE public.fact_data_quality SET context = 'CANDIDATE' "
                "WHERE source = :source AND refresh_id = :refresh_id "
                "AND context = 'PUBLISHED'"
            ),
            {"source": source, "refresh_id": refresh_id},
        )
    if generation_id is not None:
        connection.execute(
            text(
                "UPDATE public.fact_refresh_generation "
                "SET status = 'VALIDATED', published_at = NULL, updated_at = now() "
                "WHERE source = :source AND generation_id = :generation_id "
                "AND status = 'PUBLISHED'"
            ),
            {"source": source, "generation_id": generation_id},
        )
    return source, generation_id


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
        "--source",
        choices=["demo", "transfermarkt", "footystats"],
        help=(
            "The provider this refresh replaced. Required with --apply: it is "
            "the source whose freshness advances, and guessing it would tell "
            "readers the other provider was refreshed too."
        ),
    )
    parser.add_argument(
        "--generation-id",
        help=(
            "The generation being published. Normally resolved from the "
            "database; pass it to publish a specific one."
        ),
    )
    parser.add_argument(
        "--refresh-id",
        default=None,
        help=(
            "The refresh being published - the identity its quality rows carry. "
            "Defaults to the generation id. The workflow always passes it."
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
            retracted = retract_publication(connection)
        print("Rolled back. The previous dataset is serving again.")
        if retracted is not None:
            source, generation_id = retracted
            print(
                f"Retracted the {source} publication"
                + (f" of generation {generation_id}" if generation_id else "")
                + "; freshness reports the dataset now serving."
            )
        log.warning(
            "analytics_promotion_rolled_back",
            retracted_source=retracted[0] if retracted else None,
            retracted_generation=retracted[1] if retracted else None,
        )
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

    if not args.source:
        print(
            "REFUSED: --source is required with --apply. A promotion advances one "
            "provider's freshness, and which one is not something this can infer "
            "from the row counts.",
            file=sys.stderr,
        )
        return 2

    with engine.begin() as connection:
        refresh_id = args.refresh_id or args.generation_id
        if already_published(connection, args.source, refresh_id):
            # Safe no-op. Not a refusal: the thing the run exists to do has
            # been done, and a red job over a published dataset would send
            # somebody to re-run it a third time.
            print(
                f"Refresh {refresh_id} of {args.source} is already published. "
                f"Nothing to do; production is untouched."
            )
            log.info(
                "analytics_promotion_already_published", source=args.source, refresh_id=refresh_id
            )
            return 0
        if args.generation_id:
            # Named by the workflow from the database. Verified against the
            # database again here, inside the promotion's own transaction:
            # the one thing a promotion must never do is publish a
            # generation the database is not expecting to be published.
            status = generation_status(connection, args.source, args.generation_id)
            if status not in PUBLISHABLE_STATUSES:
                print(
                    f"REFUSED: generation {args.generation_id} is "
                    f"{status or 'unknown to the database'}, not one of "
                    f"{', '.join(PUBLISHABLE_STATUSES)}. Production is untouched.",
                    file=sys.stderr,
                )
                return 1
        # Counted before the swap, while the new dataset is still in staging.
        generation_id = args.generation_id or publishable_generation(connection, args.source)
        published_rows = rows_for_source(connection, STAGING, args.source)
        published_player_seasons = player_seasons_for_source(connection, STAGING, args.source)
        swap(connection)
        record_publication(
            connection,
            source=args.source,
            generation_id=generation_id,
            rows_published=published_rows,
            player_seasons_published=published_player_seasons,
            refresh_id=refresh_id or generation_id,
        )

    print(
        f"Promoted. {staged.player_seasons:,} player-seasons across "
        f"{staged.competitions:,} competitions are now serving."
    )
    print(
        f"{args.source}: {published_rows:,} source-owned rows published, "
        f"{published_player_seasons:,} of them player-seasons"
        + (f", from generation {generation_id}." if generation_id else ".")
    )
    if generation_id is None:
        print(f"No open generation for {args.source}; the publication is recorded without one.")
    print(f'The previous dataset is in "{STAGING}" and can be restored with `--rollback --apply`.')
    log.info(
        "analytics_promoted",
        source=args.source,
        generation_id=generation_id,
        players=staged.players,
        player_seasons=staged.player_seasons,
        competitions=staged.competitions,
        published_rows=published_rows,
        published_player_seasons=published_player_seasons,
        replaced_player_seasons=production.player_seasons,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
