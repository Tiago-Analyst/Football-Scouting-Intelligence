"""Baseline: establish the migration chain.

Deliberately empty. Phase 0 sets up the migration machinery only; the
analytical schema (dim_player, fact_player_season_stats, ...) is introduced in
Phase 2. Applying this revision creates Alembic's `alembic_version` table,
which the readiness endpoint reports so that "the API can reach a *migrated*
database" is observable rather than assumed.

Revision ID: 0001_baseline
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
