"""Separate "a load happened" from "a dataset reached readers".

Revision ID: 0010_source_publication
Revises: 0009_analytics_schema
Create Date: 2026-09-08

WHY
===

`fact_source_load` records a load. That was the same thing as a publication
until staging existed; now it is not, and the difference is exactly the one a
reader cares about.

A refresh loads FootyStats into `analytics_staging` at 10:00 and identity
resolution fails at 10:20. Production is still yesterday's dataset and the site
is still serving it - but `fact_source_load` has a row stamped 10:00, so
`/data-quality` and the site footer announce "Performance data updated 10:00".

The claim is false in the way that matters: it says the figures on screen are
today's when they are yesterday's, which is worse than saying nothing.

WHAT THIS ADDS
==============

One row per source per successful promotion. Written inside the promotion
transaction, so it cannot exist for a dataset that did not reach production and
cannot be missing for one that did.

`fact_source_load` keeps its meaning - load attempts, including the ones that
never published - because "when did we last try" is worth answering separately
from "what are readers seeing".

WHY IT IS NOT IN THE ANALYTICAL SCHEMA
======================================

It is a record of what happened, not part of the dataset. Putting it in
`analytics` would swap it away on the next promotion, which is the opposite of
what a publication history is for.

ROLLBACK
========

Dropping it loses the publication history. Freshness then falls back to
reporting nothing rather than reporting a load time, which is the honest
degradation: absent is not the same as stale, and stale is not the same as
fresh.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0010_source_publication"
down_revision: str | None = "0009_analytics_schema"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "fact_source_publication"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        # Null for providers with no generation model - Transfermarkt is a
        # dataset download rather than a resumable fetch.
        sa.Column("generation_id", sa.String(length=32), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rows_published", sa.Integer(), nullable=False),
        sa.CheckConstraint("rows_published >= 0", name="publication_rows_non_negative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_publication_source_time", TABLE, ["source", "published_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_source_publication_source_time", table_name=TABLE)
    op.drop_table(TABLE)
