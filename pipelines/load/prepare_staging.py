"""Seed the staging schema from current production, before a provider refresh.

    python -m pipelines.load.prepare_staging --apply
    python -m pipelines.load.prepare_staging            # report, change nothing

THE BUG THIS EXISTS TO FIX
==========================

Production holds two providers. FootyStats supplies performance; Transfermarkt
supplies identity, market values and transfers. A refresh replaces **one** of
them.

Staging was empty. So the next FootyStats refresh would have loaded its
performance data into an empty schema and promoted it, and production would
have become a universe with 79,800 market values and 34,321 transfers missing -
every one of them silently, because the result is internally consistent and
simply has no Transfermarkt in it.

Relying on the schema swap to leave the previous production in staging is not a
fix either. It is correct exactly once: after a promotion, staging holds the
dataset one cycle old, so the *second* refresh in a row builds on data that is
already a generation behind. Refresh FootyStats to F2 and publish, then refresh
Transfermarkt from that stale staging, and production becomes `F1 + T2` - the
one combination that must never exist.

THE MODEL
=========

Before every refresh, staging is rebuilt from **current** production:

    reset staging
    copy production -> staging          F1 + T1
    purge only the refreshing source    T1
    load the refreshed provider         F2 + T1
    validate
    promote                             F2 + T1

Then the next refresh starts again from what is now current, so Transfermarkt's
turn begins from `F2 + T1` and ends at `F2 + T2`. The stale combination has
nowhere to come from.

WHAT IT VERIFIES
================

That staging matches production row for row before the purge. A seed that
silently copied less than everything would produce exactly the failure this
module exists to prevent, one table at a time.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SERVING = "analytics"
STAGING = "analytics_staging"

#: Parents first, so a copy never references a row that is not there yet.
#: The same order the schema migration uses, and the reverse of it truncates.
ANALYTICAL_TABLES = (
    "dim_competition",
    "dim_season",
    "dim_club",
    "dim_player",
    "bridge_player_source",
    "fact_player_season_stats",
    "fact_market_value",
    "fact_transfer",
)


class StagingError(RuntimeError):
    """Staging could not be prepared. Nothing downstream should run."""


@dataclass(frozen=True)
class Fingerprint:
    """Row counts per table, which is what "matches production" means here."""

    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def differences(self, other: Fingerprint) -> list[str]:
        return [
            f"{table}: production {self.counts.get(table, 0):,} vs staging "
            f"{other.counts.get(table, 0):,}"
            for table in ANALYTICAL_TABLES
            if self.counts.get(table, 0) != other.counts.get(table, 0)
        ]


def fingerprint(connection, schema: str) -> Fingerprint:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    counts: dict[str, int] = {}
    for table in ANALYTICAL_TABLES:
        counts[table] = int(
            connection.execute(
                text(f'SELECT count(*) FROM "{schema}"."{table}"')  # noqa: S608
            ).scalar()
            or 0
        )
    return Fingerprint(counts=counts)


def _columns(connection, schema: str, table: str) -> list[str]:  # type: ignore[no-untyped-def]
    """Column names in declaration order.

    Named explicitly rather than relying on `SELECT *`: the two schemas were
    built by different routes - production moved from `public`, staging created
    from the models - and a positional copy would depend on their column order
    having stayed in step, which nothing guarantees.
    """
    from sqlalchemy import text

    return [
        row[0]
        for row in connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
            ),
            {"s": schema, "t": table},
        )
    ]


def prepare(connection) -> Fingerprint:  # type: ignore[no-untyped-def]
    """Reset staging and copy production into it. Caller owns the transaction."""
    from sqlalchemy import text

    # -- Empty it -----------------------------------------------------------
    #
    # One statement so foreign keys never see a partially emptied schema.
    # `RESTART IDENTITY` resets the sequences; they are set to production's
    # values below, after the rows are in.
    targets = ", ".join(f'"{STAGING}"."{table}"' for table in ANALYTICAL_TABLES)
    connection.execute(text(f"TRUNCATE {targets} RESTART IDENTITY CASCADE"))

    # -- Copy, parents first ------------------------------------------------
    for table in ANALYTICAL_TABLES:
        production_columns = _columns(connection, SERVING, table)
        staging_columns = set(_columns(connection, STAGING, table))
        shared = [c for c in production_columns if c in staging_columns]
        missing = [c for c in production_columns if c not in staging_columns]
        if missing:
            raise StagingError(
                f'"{STAGING}"."{table}" is missing {missing}. The two schemas have '
                f"diverged; a migration altered one and not the other."
            )
        names = ", ".join(f'"{c}"' for c in shared)
        connection.execute(
            # Identifiers only, every one of them read back from
            # information_schema. A bound parameter cannot carry a table or
            # column name, so interpolation is the only option here.
            text(
                f'INSERT INTO "{STAGING}"."{table}" ({names}) '  # noqa: S608
                f'SELECT {names} FROM "{SERVING}"."{table}"'
            )
        )

    _sync_sequences(connection)
    return fingerprint(connection, STAGING)


def _sync_sequences(connection) -> None:  # type: ignore[no-untyped-def]
    """Advance staging's sequences past the ids just copied.

    The copy preserves primary keys, so a sequence left at 1 would hand the
    next insert an id that already exists. Every load after a seed would fail
    on the first new player.
    """
    from sqlalchemy import text

    rows = connection.execute(
        text("""
            SELECT c.relname AS table_name, a.attname AS column_name,
                   pg_get_serial_sequence(quote_ident(n.nspname) || '.' ||
                                          quote_ident(c.relname), a.attname) AS seq
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = :schema
              AND a.attnum > 0
              AND NOT a.attisdropped
              AND pg_get_serial_sequence(quote_ident(n.nspname) || '.' ||
                                         quote_ident(c.relname), a.attname) IS NOT NULL
        """),
        {"schema": STAGING},
    ).all()

    for table, column, sequence in rows:
        connection.execute(
            # Identifiers only, from the catalogue query above.
            text(
                f"SELECT setval('{sequence}', "  # noqa: S608
                f'COALESCE((SELECT max("{column}") FROM "{STAGING}"."{table}"), 0) + 1, false)'
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Rebuild staging. Without it, report only."
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
        production = fingerprint(connection, SERVING)
        staged = fingerprint(connection, STAGING)

    print(f"{'':<28}{'production':>12}{'staging':>12}")
    for table in ANALYTICAL_TABLES:
        print(
            f"{table:<28}{production.counts.get(table, 0):>12,}{staged.counts.get(table, 0):>12,}"
        )
    print()

    if not args.apply:
        print(
            f"Would reset staging and copy {production.total:,} rows from production.\n"
            "Re-run with --apply."
        )
        return 0

    with engine.begin() as connection:
        seeded = prepare(connection)

    differences = production.differences(seeded)
    if differences:
        # The transaction has committed; report loudly rather than pretend.
        for difference in differences:
            print(f"MISMATCH: {difference}", file=sys.stderr)
        print(
            "\nStaging does not match production. Do NOT load or promote from it.",
            file=sys.stderr,
        )
        log.error("staging_seed_mismatch", differences=differences)
        return 1

    print(
        f"Staging seeded from production: {seeded.total:,} rows across "
        f"{len(ANALYTICAL_TABLES)} tables, matching row for row."
    )
    print("The refreshing provider is purged from it next; every other provider stays.")
    log.info("staging_seeded", rows=seeded.total, tables=len(ANALYTICAL_TABLES))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
