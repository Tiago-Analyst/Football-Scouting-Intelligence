"""Which generation a check describes, and which checkpoint a generation is at.

Revision ID: 0011_generation_context
Revises: 0010_source_publication
Create Date: 2026-09-13

THREE ADDITIONS, ONE REASON
===========================

Every one of these is a fact the pipeline knew and the database could not hold,
and each gap produced a claim the site could not back.

`fact_data_quality.generation_id` and `.context`
    The quality report ran against staging and wrote its rows beside every
    other run's. Production serving G4, a G5 candidate checked and then failed
    at promotion, and `/data-quality` showed G5's checks above G4's data. The
    rows now say which generation they describe and whether that generation
    was a candidate or is published; the promotion flips the candidate rows to
    PUBLISHED in its own transaction.

`fact_refresh_generation.checkpoint_revision`
    The GitHub Actions cache is immutable per key. A generation grows over
    nineteen hourly runs, so each run saves under a new key carrying this
    revision, and the database records the revision the last run reached. A
    restore that comes back older is refused rather than resumed.

`fact_source_publication.player_seasons_published`
    `rows_published` sums every source-owned row - competitions, clubs,
    bridges, player-seasons, market values, transfers - and was being read as a
    player-season count. Two meanings, one column. This is the second meaning,
    in its own column.

ROLLBACK
========

Dropping the columns loses the generation attribution on quality rows; the
rows themselves stay. Freshness and the refresh panel keep working from the
columns that remain.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0011_generation_context"
down_revision: str | None = "0010_source_publication"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "fact_data_quality",
        sa.Column("generation_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fact_data_quality",
        # CANDIDATE: ran against staging for a generation not yet promoted.
        # PUBLISHED: describes the dataset readers are being served.
        # Null: written before contexts existed, or by a run with no
        # generation (a local demo load).
        sa.Column("context", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "data_quality_context_valid",
        "fact_data_quality",
        "context IS NULL OR context IN ('CANDIDATE', 'PUBLISHED')",
    )
    op.create_index(
        "ix_data_quality_generation",
        "fact_data_quality",
        ["source", "generation_id", "context"],
    )

    op.add_column(
        "fact_refresh_generation",
        sa.Column("checkpoint_revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "generation_revision_non_negative",
        "fact_refresh_generation",
        "checkpoint_revision >= 0",
    )

    op.add_column(
        "fact_source_publication",
        sa.Column("player_seasons_published", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "publication_player_seasons_non_negative",
        "fact_source_publication",
        "player_seasons_published IS NULL OR player_seasons_published >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "publication_player_seasons_non_negative", "fact_source_publication", type_="check"
    )
    op.drop_column("fact_source_publication", "player_seasons_published")

    op.drop_constraint("generation_revision_non_negative", "fact_refresh_generation", type_="check")
    op.drop_column("fact_refresh_generation", "checkpoint_revision")

    op.drop_index("ix_data_quality_generation", table_name="fact_data_quality")
    op.drop_constraint("data_quality_context_valid", "fact_data_quality", type_="check")
    op.drop_column("fact_data_quality", "context")
    op.drop_column("fact_data_quality", "generation_id")
