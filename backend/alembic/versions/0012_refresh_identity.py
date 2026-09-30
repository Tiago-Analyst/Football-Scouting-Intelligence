"""A provider-independent identity for every staging refresh.

Revision ID: 0012_refresh_identity
Revises: 0011_generation_context
Create Date: 2026-09-13

WHY
===

Quality rows learned to say which generation they describe, and whether that
generation was a candidate or is published. That fixed FootyStats and left
Transfermarkt where it was: Transfermarkt has no generation, so its staging
checks carried a null generation_id, and null read as "describes whatever is
serving" - the pre-context meaning. A T2 candidate checked in staging and then
stuck at promotion showed its checks as production's, which is the exact
failure the context column exists to prevent, arriving through the one
provider the column did not cover.

`refresh_id` is the identity every staging refresh has. For FootyStats it is
the generation id. For Transfermarkt it is minted by the workflow per run. The
promotion flips CANDIDATE rows to PUBLISHED by `source + refresh_id`, which
works for both, and `generation_id` stays as the FootyStats-specific detail it
always was.

The publication ledger gets the same column, so "which refresh is this source
serving" is answerable for Transfermarkt too.

BACKFILL
========

`refresh_id = generation_id` where a generation id is present: the two are the
same thing for FootyStats, and every row written under 0011 was FootyStats.

ROLLBACK
========

Dropping the columns loses the refresh attribution; the rows and their
generation_id stay.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0012_refresh_identity"
down_revision: str | None = "0011_generation_context"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("fact_data_quality", sa.Column("refresh_id", sa.String(length=64), nullable=True))
    op.execute(
        "UPDATE fact_data_quality SET refresh_id = generation_id "
        "WHERE refresh_id IS NULL AND generation_id IS NOT NULL"
    )
    # Latest published / latest candidate per source, and everything about one
    # refresh: the three queries the service runs.
    op.create_index(
        "ix_data_quality_source_context_time",
        "fact_data_quality",
        ["source", "context", "executed_at"],
    )
    op.create_index(
        "ix_data_quality_refresh",
        "fact_data_quality",
        ["source", "refresh_id", "context"],
    )

    op.add_column(
        "fact_source_publication", sa.Column("refresh_id", sa.String(length=64), nullable=True)
    )
    op.execute(
        "UPDATE fact_source_publication SET refresh_id = generation_id "
        "WHERE refresh_id IS NULL AND generation_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("fact_source_publication", "refresh_id")
    op.drop_index("ix_data_quality_refresh", table_name="fact_data_quality")
    op.drop_index("ix_data_quality_source_context_time", table_name="fact_data_quality")
    op.drop_column("fact_data_quality", "refresh_id")
