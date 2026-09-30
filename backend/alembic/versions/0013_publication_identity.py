"""One publication per source and refresh.

Revision ID: 0013_publication_identity
Revises: 0012_refresh_identity
Create Date: 2026-09-16

WHY
===

A promotion is a schema swap plus a publication row, in one transaction. Run
it twice for the same refresh - a job re-run after the first attempt had
already committed, an operator invoking it twice, a connection lost after the
commit but before the job recorded success - and the second swap puts the
*previous* dataset back into production while writing a second publication
row that says the new one was published again. Two rows, one lie.

The promotion now checks the ledger before swapping and stops if the refresh
is already published. This index is the database saying the same thing, for
whatever bypasses the check.

WHY PARTIAL
===========

Rows written before refresh ids existed have none, and two of them for one
source are history, not a conflict. Only named refreshes are unique.

WHY THIS DOES NOT BREAK ROLLBACK
================================

`--rollback` deletes the retracted publication row - it really does
un-publish - so the identity is released and the same refresh can be
published again on purpose. Idempotency distinguishes "already published"
(a row exists) from "published once and rolled back" (no row); the index
enforces exactly that distinction.

ROLLBACK
========

Dropping the index removes the protection and nothing else.
"""

from __future__ import annotations

from alembic import op

revision: str = "0013_publication_identity"
down_revision: str | None = "0012_refresh_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "uq_source_publication_refresh",
        "fact_source_publication",
        ["source", "refresh_id"],
        unique=True,
        postgresql_where="refresh_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_source_publication_refresh", table_name="fact_source_publication")
