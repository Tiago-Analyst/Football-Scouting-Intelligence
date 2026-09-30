"""Record where a provider refresh has got to, where the API can read it.

Revision ID: 0008_refresh_generation
Revises: 0007_recorded_minutes_unclamped
Create Date: 2026-09-08

A generation's own state lives on disk beside its snapshots, which is the right
place for it - the fetch runs over many runs and the disk is what survives
between them.

The serving layer cannot see that disk. The fetch runs in CI with its snapshots
in the job cache; the API runs elsewhere. A /data-quality page reading the
generation directory would therefore show full progress in development and
nothing at all in production, which is worse than showing nothing in both.

This table is the projection: the pipeline writes where it has got to, the API
reads it, and neither needs the other's filesystem.

ROLLBACK

Dropping it loses the refresh history and nothing else. No other table
references it, and the page degrades to hiding the panel - which is what it
already does when no generation has been recorded.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_refresh_generation"
down_revision: str | None = "0007_recorded_minutes_unclamped"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "fact_refresh_generation"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("generation_id", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_expected_players", sa.Integer(), nullable=False),
        sa.Column("completed_players", sa.Integer(), nullable=False),
        sa.Column("failed_players", sa.Integer(), nullable=False),
        sa.Column("competitions_expected", sa.Integer(), nullable=False),
        sa.Column("competitions_complete", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.CheckConstraint("total_expected_players >= 0", name="generation_expected_non_negative"),
        sa.CheckConstraint("completed_players >= 0", name="generation_completed_non_negative"),
        sa.CheckConstraint("failed_players >= 0", name="generation_failed_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "generation_id", name="uq_refresh_generation"),
    )
    op.create_index(
        "ix_refresh_generation_source_time", TABLE, ["source", "updated_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_generation_source_time", table_name=TABLE)
    op.drop_table(TABLE)
