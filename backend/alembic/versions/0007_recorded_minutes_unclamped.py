"""Allow recorded_minutes to exceed minutes played.

Revision ID: 0007_recorded_minutes_unclamped
Revises: 0006_source_load
Create Date: 2026-09-08

WHY THE CONSTRAINT GOES

`recorded_minutes <= minutes` encodes a fact about football: the statistics
cannot describe more minutes than were played. It is a true statement about the
world and a false one about this provider's data.

The denominator validation established, against FootyStats' own published
per-90 fields, that detailed metrics are computed over the recorded figure -
including in records where it exceeds the played figure. One sampled player has
326 played minutes and 416 recorded, and their detailed rates reproduce only
when divided by 416.

So the provider means something by that number, the constraint was rejecting
it, and the loader was clamping to satisfy the constraint. Clamping 416 to 326
inflates every detailed per-90 for that player by 28% - a silent corruption
produced by a rule intended to prevent one.

WHAT REPLACES IT

Nothing, at the database level. The two non-negativity constraints stay,
because those are arithmetic rather than editorial: a negative minute count is
not a provider opinion, it is corrupt.

The relationship between the two figures is now a data-quality observation
rather than a schema rule. `pipelines.quality.report` counts the rows where it
holds and reports them, and the profile marks the player rather than hiding the
discrepancy.

ROLLBACK

`downgrade()` restores the constraint. It will fail if any row violates it by
then, which is the correct behaviour: re-imposing the rule means deciding what
to do with the rows that break it, and that is a decision, not a migration.
Clean them first, or stay on this revision.

NO DATA IS REWRITTEN

Existing rows were clamped on the way in, and this migration does not attempt
to reconstruct what they were - that information was destroyed at load time and
only a refresh can recover it. The next FootyStats generation loads the raw
values.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_recorded_minutes_unclamped"
down_revision: str | None = "0006_source_load"
branch_labels: str | None = None
depends_on: str | None = None

CONSTRAINT = "ck_fact_player_season_stats_recorded_minutes_within_minutes"
TABLE = "fact_player_season_stats"


def upgrade() -> None:
    # Raw DDL rather than `op.drop_constraint`. The metadata naming convention
    # applies its `ck_%(table_name)s_` prefix to whatever name it is handed, so
    # passing the real constraint name produces
    # `ck_fact_player_season_stats_ck_fact_player_season_stats_...` and fails.
    # `IF EXISTS` keeps this idempotent on a database that never had it.
    op.execute(sa.text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT}"))


def downgrade() -> None:
    # Will refuse if any row now exceeds. See the note above: that is a
    # decision about data, not something a downgrade should make silently.
    op.execute(
        sa.text(
            f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} "
            "CHECK (recorded_minutes IS NULL OR minutes IS NULL "
            "OR recorded_minutes <= minutes)"
        )
    )
