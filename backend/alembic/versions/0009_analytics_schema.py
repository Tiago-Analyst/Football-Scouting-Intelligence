"""Move the analytical tables into a schema that can be swapped.

Revision ID: 0009_analytics_schema
Revises: 0008_refresh_generation
Create Date: 2026-09-08

WHY
===

A refresh currently replaces production data inside one transaction, and the
checks that run *after* the commit - identity resolution, prune, data quality,
analytics validation - run against data readers are already being served. If
one of them fails, the site is serving a dataset nothing has finished checking.

Atomic promotion moves the finish line. A refresh loads into
`analytics_staging`, every check runs against that, and only then are the two
schemas swapped. Anything that fails before the swap leaves the served schema
untouched, because it was never the thing being written to.

WHAT MAKES THIS SAFE
====================

The analytical tables are closed under foreign keys. Nothing outside them
references them, and they reference nothing outside:

    dim_competition, dim_club, dim_player, dim_season,
    fact_player_season_stats, fact_market_value, fact_transfer,
    bridge_player_source

`shortlist_entry` stores `player_key` as a plain string rather than a foreign
key to `dim_player`, which is what makes the cluster movable at all - a
referencing row in an operational table would break the moment the referenced
table was swapped out from under it.

Everything else stays in `public` and is never swapped: accounts, sessions,
shortlists, and the quality, load and refresh histories, which are records of
what happened and must survive the data they describe.

HOW THE SWAP WORKS
==================

Three renames in one transaction, in `pipelines.load.promote`:

    analytics          -> analytics_previous
    analytics_staging  -> analytics
    analytics_previous -> analytics_staging

The schema that was serving becomes the staging schema for the next cycle, so
one cycle of history is always recoverable by running the same swap again.

ROLLBACK
========

`downgrade()` moves the tables back into `public` and drops the two schemas.
It is safe as long as `public` holds no table of the same name, which it will
not unless something has been created by hand.

Note that a downgrade discards `analytics_staging` - by then it holds either an
unfinished load or the previous cycle's data, and neither is something a schema
migration should decide to promote.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0009_analytics_schema"
down_revision: str | None = "0008_refresh_generation"
branch_labels: str | None = None
depends_on: str | None = None

SERVING = "analytics"
STAGING = "analytics_staging"

#: The closed foreign-key cluster, parents first so a move never dangles.
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


def upgrade() -> None:
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{SERVING}"'))

    # Rebuilt rather than created if absent. A staging schema left behind by an
    # earlier attempt holds tables this migration would then skip, and they
    # would carry whatever names that attempt gave them - which is precisely
    # the divergence this migration exists to prevent. Staging holds no data
    # worth keeping at migration time: it is either empty or an unfinished
    # load.
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{STAGING}" CASCADE'))
    op.execute(sa.text(f'CREATE SCHEMA "{STAGING}"'))

    for table in ANALYTICAL_TABLES:
        # Foreign keys and indexes are held by OID and follow the table, so
        # moving the whole cluster preserves every relationship inside it.
        op.execute(sa.text(f'ALTER TABLE IF EXISTS public."{table}" SET SCHEMA "{SERVING}"'))

    _staging_metadata().create_all(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    _staging_metadata().drop_all(op.get_bind(), checkfirst=True)
    for table in ANALYTICAL_TABLES:
        op.execute(sa.text(f'ALTER TABLE IF EXISTS "{SERVING}"."{table}" SET SCHEMA public'))
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{STAGING}" CASCADE'))
    op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{SERVING}" CASCADE'))


def _staging_metadata() -> sa.MetaData:
    """The analytical tables, re-bound to the staging schema.

    WHY NOT `CREATE TABLE ... LIKE`

    `LIKE ... INCLUDING ALL` copies indexes and constraints and gives them
    PostgreSQL's default names - `dim_club_pkey` rather than `pk_dim_club`,
    `dim_club_name_idx` rather than `ix_dim_club_name`. The structures are
    equivalent, so nothing fails until a promotion swaps the default-named
    schema into production and the next migration alters a constraint by a name
    that no longer exists - long after the change that caused it.

    Reconciling the names afterwards is possible and was tried; it depends on
    comparing `pg_get_indexdef` output, which qualifies the table name only
    when the schema is off the search path, so the same index yields different
    text depending on who is asking.

    Building from the application's own models sidesteps all of it: the naming
    convention runs over both schemas and the names are identical by
    construction.
    """
    from app.core.database import Base

    metadata = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for name in ANALYTICAL_TABLES:
        Base.metadata.tables[name].to_metadata(metadata, schema=STAGING)
    return metadata
